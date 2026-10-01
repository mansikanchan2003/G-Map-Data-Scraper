"""
Templates made from a sheet of messages that were already written out.

Someone hands over a spreadsheet: a phone number per row, the full message
that person should receive, and the columns the message was put together from
(name, amount, date...). Meta will only deliver a bulk message through a
template it has approved, so the sheet has to be turned back into one:

1. Each row's message is compared with its own columns. A column whose value
   appears in every row's message and changes between rows is a variable;
   everything else is fixed text. Every row must then reduce to the same
   template, or the sheet is refused with the rows and words that differ —
   guessing would send someone a message that was never written for them.
2. A template with the same wording (punctuation and emoji aside) that Meta
   has already approved is used as it is.
3. Otherwise the template is submitted to Meta straight away. Calling again
   with the same sheet finds that submission instead of making another, and
   reports where Meta's review has got to: still pending, approved, or
   rejected with Meta's reason.

Nothing is sent from here. An approved template is used by a campaign, which
fills each variable from the same sheet — see WhatsAppCampaignService.
"""
import difflib
import hashlib
import logging
import re
import time
import unicodedata
import uuid
from typing import Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from src.models.whatsapp import WhatsAppTemplate

logger = logging.getLogger("gmap_scraper.sheet_templates")

ORIGIN = "sheet"

# Meta's own ceiling for a template body.
BODY_LIMIT = 1024
MAX_ROWS = 20000

# {{name}} and {{link}} mean the same in every template: the recipient's name,
# and their own tracking link. A sheet column called "link" would collide with
# the second, so it is renamed.
RESERVED = {"link": "link_value"}

# Review states after which Meta's answer will not change on its own.
FINAL_STATUSES = {"APPROVED", "REJECTED", "DISABLED"}

TOKEN = re.compile(r"\{\{([a-z][a-z0-9_]*)\}\}")

# Where the tracked link in a sheet template lands. Each recipient's button
# opens their own /r/<token>, which records the visit and forwards here; the
# redirect adds utm_campaign so visits are told apart per campaign.
DEFAULT_LINK_TARGET = "https://kiosk.eko.in/?utm_source=AutoGMap&utm_medium=whatsapp#apply-now"
DEFAULT_BUTTON_TEXT = "Apply Now"
BUTTON_TEXT_LIMIT = 25

# A link to the site written into the messages is swapped for {{link}}, each
# recipient's own tracked link, so every visit through it is recorded.
SITE_HOSTS = ("kiosk.eko.in",)


def site_link_pattern(extra_host: Optional[str] = None) -> re.Pattern:
    """Links to the kiosk site, or to the destination's own site, in a message."""
    hosts = list(SITE_HOSTS)
    if extra_host and extra_host.lower() not in hosts:
        hosts.append(extra_host.lower())
    alternatives = "|".join(re.escape(h) for h in hosts)
    # The host must end there: "kiosk.eko.in.evil.com" is someone else's site,
    # while a full stop ending the sentence is not part of the link.
    return re.compile(rf"https?://(?:www\.)?(?:{alternatives})(?![\w-]|\.\w)(?:[/?#][^\s]*)?",
                      re.IGNORECASE)


SITE_LINK = site_link_pattern()


class DerivationError(ValueError):
    """The sheet does not reduce to one template; the message says why."""


# ---------------------------------------------------------------------------
# Columns and values
# ---------------------------------------------------------------------------

def column_key(header: str) -> str:
    """
    The placeholder name a column is known by, e.g. "Due Date" -> "due_date".

    Used both when the template is derived and when a campaign reads the same
    sheet, so the two always agree. A header with no Latin letters — a Hindi
    column name — gets a stable name made from its bytes.
    """
    text = str(header or "").strip()
    key = re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")
    if not key:
        key = "col_" + hashlib.sha256(text.encode("utf-8")).hexdigest()[:8]
    elif not key[0].isalpha():
        key = "col_" + key
    key = key[:40]
    return RESERVED.get(key, key)


def cell_text(value) -> str:
    """A cell as the text a reader sees: 500.0 is "500"."""
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def clean_parameter(value: str) -> str:
    """
    A value as Meta will accept it inside a template.

    Meta rejects a parameter carrying a newline or a tab, or more than four
    spaces in a row, so those are flattened rather than failing the send.
    """
    text = re.sub(r"[\r\n\t]+", " ", str(value or ""))
    return re.sub(r" {4,}", "   ", text).strip()


# ---------------------------------------------------------------------------
# Deriving the template
# ---------------------------------------------------------------------------

def _find(value: str, text: str) -> Optional[re.Pattern]:
    """
    A pattern for the value as a whole word in the text, or as a plain
    substring when it only appears joined to something ("Rs500").
    """
    whole = re.compile(r"(?<!\w)" + re.escape(value) + r"(?!\w)")
    if whole.search(text):
        return whole
    if value in text:
        return re.compile(re.escape(value))
    return None


def _skeleton(message: str, values: Dict[str, str]) -> str:
    """The message with each variable's value replaced by its placeholder."""
    # Longest first, so "Ramesh Kumar" is replaced before a "Ramesh" that is
    # part of it. A marker stands in for each placeholder until the end, so a
    # later value cannot match inside one already placed.
    marks = {}
    text = message
    for i, (key, value) in enumerate(sorted(values.items(), key=lambda kv: -len(kv[1]))):
        pattern = _find(value, text)
        if pattern is None:
            continue
        mark = f"\x00{i}\x00"
        marks[mark] = "{{%s}}" % key
        text = pattern.sub(mark, text)
    for mark, token in marks.items():
        text = text.replace(mark, token)
    return text


def _difference(a: str, b: str) -> str:
    """The words that differ between two skeletons, for the error message."""
    wa, wb = a.split(), b.split()
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(a=wa, b=wb).get_opcodes():
        if op != "equal":
            left = " ".join(wa[i1:i2]) or "(nothing)"
            right = " ".join(wb[j1:j2]) or "(nothing)"
            return f"“{left}” in one, “{right}” in the other"
    return "they differ in spacing or punctuation"


def derive(rows: List[dict], message_column: str, phone_column: str,
           track_site_links: bool = True, link_host: Optional[str] = None) -> dict:
    """
    Works out the one template every row's message was written from.

    Returns {"body", "variables", "columns", "examples", "rows"}:
      body       the template with {{key}} placeholders
      variables  placeholder keys in order of first appearance
      columns    key -> the sheet header it reads from
      examples   key -> the first row's value, which Meta asks for on review

    Raises DerivationError with a reason a person can act on.
    """
    if not rows:
        raise DerivationError("The sheet has no rows.")
    if len(rows) > MAX_ROWS:
        raise DerivationError(f"The sheet has {len(rows):,} rows; at most {MAX_ROWS:,} can be read at once.")
    if message_column not in rows[0]:
        raise DerivationError(f"There is no “{message_column}” column in the sheet.")

    messages = [cell_text(r.get(message_column)) for r in rows]
    empty = [i + 2 for i, m in enumerate(messages) if not m]
    if empty:
        listed = ", ".join(str(n) for n in empty[:5]) + (" …" if len(empty) > 5 else "")
        raise DerivationError(f"Row {listed} has no message.")

    headers = [h for h in rows[0].keys() if h not in (message_column, phone_column)]
    keys: Dict[str, str] = {}
    for header in headers:
        key = column_key(header)
        if key in keys.values():
            raise DerivationError(
                f"The columns “{header}” and “{[h for h, k in keys.items() if k == key][0]}” "
                f"read the same once tidied up. Rename one of them."
            )
        keys[header] = key

    # A column is a variable when its value is in every row's message and is
    # not the same for everyone. With one row nothing can be seen to vary, so
    # every column the message contains is taken as that person's data.
    variables: List[str] = []
    for header in headers:
        values = [cell_text(r.get(header)) for r in rows]
        if not all(values):
            continue
        if not all(_find(v, m) for v, m in zip(values, messages)):
            continue
        if len(rows) > 1 and len(set(values)) == 1:
            continue
        variables.append(header)

    skeletons = [
        _skeleton(m, {keys[h]: cell_text(r.get(h)) for h in variables})
        for r, m in zip(rows, messages)
    ]

    first = skeletons[0]
    for index, other in enumerate(skeletons[1:], start=1):
        if other != first:
            raise DerivationError(
                f"Rows 2 and {index + 2} do not follow the same wording once the "
                f"per-person columns are taken out: {_difference(first, other)}. "
                f"Every row must be the same message with only its own column "
                f"values changed; send messages worded differently as separate sheets."
            )

    body = first
    if track_site_links:
        body = site_link_pattern(link_host).sub(
            lambda m: "{{link}}" + _trailing_punctuation(m.group(0)), body)
    order = []
    for key in TOKEN.findall(body):
        if key not in order:
            order.append(key)

    _check_meta_rules(body)

    by_key = {keys[h]: h for h in variables}
    # {{link}} is each recipient's tracking link, not a sheet column.
    columns_used = [k for k in order if k != "link"]
    return {
        "body": body,
        "variables": columns_used,
        "columns": {k: by_key[k] for k in columns_used},
        "examples": {k: clean_parameter(cell_text(rows[0].get(by_key[k]))) for k in columns_used},
        "tracked_link_in_body": "link" in order,
        "rows": len(rows),
    }


def _trailing_punctuation(url: str) -> str:
    """A full stop or bracket that ends a sentence is not part of the link."""
    tail = re.search(r"[.,;:!?)\]]+$", url)
    return tail.group(0) if tail else ""


def _check_meta_rules(body: str) -> None:
    """What Meta refuses outright, caught before submitting rather than after."""
    if "{{" in TOKEN.sub("", body) or "}}" in TOKEN.sub("", body):
        raise DerivationError("The message itself contains “{{” or “}}”, which WhatsApp templates cannot carry.")
    if len(body) > BODY_LIMIT:
        raise DerivationError(f"The message is {len(body)} characters; WhatsApp allows at most {BODY_LIMIT}.")
    stripped = body.strip()
    starts = TOKEN.match(stripped)
    if starts:
        raise DerivationError(
            f"Every message starts with the {{{{{starts.group(1)}}}}} value. WhatsApp "
            f"refuses a template that begins with a variable: put some fixed text first, "
            f"such as “Hi {{{{{starts.group(1)}}}}}”."
        )
    ends = re.search(r"\{\{([a-z][a-z0-9_]*)\}\}$", stripped)
    if ends:
        raise DerivationError(
            f"Every message ends with the {{{{{ends.group(1)}}}}} value. WhatsApp refuses a "
            f"template that ends with a variable: add fixed text after it, even a full stop "
            f"after a word, such as “… {{{{{ends.group(1)}}}}} today.”"
        )


# ---------------------------------------------------------------------------
# Recognising a template that already exists
# ---------------------------------------------------------------------------

def normalise(body: str) -> str:
    """
    The wording with punctuation, emoji and spacing taken out, so two
    messages that differ only in those count as the same template.
    Placeholders survive by name: "Hi {{name}}" never matches "Hi {{amount}}".
    """
    text = unicodedata.normalize("NFC", body or "")
    text = TOKEN.sub(lambda m: f" \x01{m.group(1)}\x01 ", text)
    kept = []
    for ch in text.lower():
        category = unicodedata.category(ch)
        if category[0] in ("P", "S") or category in ("Cf",):
            kept.append(" ")
        else:
            kept.append(ch)
    return " ".join("".join(kept).split())


def button_signature(buttons) -> str:
    """The buttons, as far as matching is concerned: their kinds and labels."""
    return "|".join(f"{(b.get('type') or '').upper()}:{normalise(b.get('text') or '')}"
                    for b in (buttons or []))


def fingerprint(body: str, language: str, buttons=None) -> str:
    return hashlib.sha256(
        f"{language}|{normalise(body)}|{button_signature(buttons)}".encode("utf-8")
    ).hexdigest()


def tracking_enabled() -> bool:
    """Whether a link can be tracked at all: the redirect must be reachable."""
    import os
    return bool((os.environ.get("PUBLIC_BASE_URL") or "").strip())


def link_button(text: str, target: str = DEFAULT_LINK_TARGET) -> dict:
    """
    The call-to-action every sheet template carries.

    With a public base URL each recipient's button opens their own
    /r/<token> — Meta appends the token sent at send time to the URL it
    approved — so each visit is recorded against that person. Without one,
    nothing could receive the visit, so the button opens the page directly.
    """
    import os
    base = (os.environ.get("PUBLIC_BASE_URL") or "").strip().rstrip("/")
    url = f"{base}/r/{{{{1}}}}" if base else target
    return {"type": "URL", "text": text, "url": url}


def _meta_name(print_: str, attempt: int) -> str:
    return f"auto_{print_[:12]}" + (f"_{attempt}" if attempt else "")


# ---------------------------------------------------------------------------
# Meta's review state
# ---------------------------------------------------------------------------

# Meta is asked at most this often while Studio pages poll, so an open tab
# cannot spend the account's API budget.
REFRESH_EVERY_SECONDS = 60
_last_refresh = 0.0


def refresh_statuses(db: Session, templates: List[WhatsAppTemplate], force: bool = False) -> None:
    """Brings submitted templates up to date with Meta's review, in one call."""
    global _last_refresh
    waiting = [t for t in templates if t.meta_template_name and (t.status or "").upper() not in FINAL_STATUSES]
    if not waiting:
        return
    if not force and time.monotonic() - _last_refresh < REFRESH_EVERY_SECONDS:
        return
    _last_refresh = time.monotonic()

    from src.services.meta_whatsapp_service import MetaWhatsAppService

    listing = MetaWhatsAppService().list_message_templates()
    if listing["status"] != "success":
        logger.warning(f"sheet_templates event=REFRESH_FAILED error={listing.get('error')}")
        return
    remote = {(t.get("name"), t.get("language")): t for t in listing["templates"]}

    for t in waiting:
        entry = remote.get((t.meta_template_name, t.language_code))
        if entry is None:
            continue
        status = (entry.get("status") or "PENDING").upper()
        if status != t.status:
            logger.info(f"sheet_templates event=STATUS_CHANGED template_id={t.template_id} "
                        f"from={t.status} to={status}")
        t.status = status
        t.category = entry.get("category") or t.category
        reason = entry.get("rejected_reason")
        if status == "REJECTED" and reason and reason != "NONE":
            gen = dict(t.generation or {})
            gen["rejected_reason"] = reason
            t.generation = gen
    db.commit()


def _outcome(t: WhatsAppTemplate) -> Tuple[str, Optional[str]]:
    """What a template's state means for the caller: an action and a reason."""
    status = (t.status or "").upper()
    gen = t.generation or {}
    if status == "APPROVED":
        return "ready", None
    if status == "REJECTED":
        reason = gen.get("rejected_reason")
        return "rejected", (
            f"Meta rejected the wording ({reason.replace('_', ' ').lower()})." if reason
            else "Meta rejected the wording."
        ) + " Change the message text in the sheet and try again."
    if status in ("DISABLED", "PAUSED"):
        return "rejected", f"Meta has {status.lower()} this template."
    if not t.meta_template_name:
        return "failed", gen.get("submit_error") or "The template has not reached Meta."
    return "pending", None


# ---------------------------------------------------------------------------
# The whole round
# ---------------------------------------------------------------------------

def _human_name(source_name: Optional[str], body: str) -> str:
    base = (source_name or "").strip()
    if base:
        base = re.sub(r"\.(xlsx|xls|csv)$", "", base, flags=re.IGNORECASE)
        return f"From {base}"[:200]
    return ("From sheet: " + " ".join(body.split()[:6]))[:200]


def template_from_messages(
    db: Session,
    rows: List[dict],
    message_column: str,
    phone_column: str,
    category: str = "MARKETING",
    language: str = "en_US",
    source_name: Optional[str] = None,
    link_target: Optional[str] = None,
    button_text: Optional[str] = None,
    add_button: bool = False,
) -> dict:
    """
    Derives the sheet's template and makes sure Meta has it.

    A link to the kiosk site (or to link_target's site) written in the
    messages becomes each recipient's own tracked link, forwarding to
    link_target. With add_button the template also carries a button opening each
    recipient's tracked link, which forwards to link_target.

    Safe to call again with the same sheet as often as needed: it finds what
    the first call submitted rather than submitting again. Returns
    {"action": ready | pending | created | rejected | failed, "template",
     "derived", "reason"}.

    Raises DerivationError when the sheet does not reduce to one template.
    """
    from src.services.whatsapp_service import WhatsAppTemplateSubmissionService

    category = (category or "MARKETING").upper()
    language = (language or "en_US").strip()
    link_target = (link_target or DEFAULT_LINK_TARGET).strip()
    host = re.match(r"^https?://(?:www\.)?([^\s/?#:]+)", link_target)
    if not host:
        raise DerivationError("The link must be a full web address starting with https://.")
    derived = derive(rows, message_column, phone_column, link_host=host.group(1))
    body = derived["body"]
    button_text = (button_text or DEFAULT_BUTTON_TEXT).strip()
    if add_button and not (0 < len(button_text) <= BUTTON_TEXT_LIMIT):
        raise DerivationError(f"The button label must be 1–{BUTTON_TEXT_LIMIT} characters.")
    buttons = [link_button(button_text, link_target)] if add_button else []

    print_ = fingerprint(body, language, buttons)
    wording = normalise(body)
    signature = button_signature(buttons)

    def result(action, tmpl, reason=None):
        logger.info(f"sheet_templates event={action.upper()} template_id={tmpl.template_id if tmpl else '-'} "
                    f"fingerprint={print_[:12]} rows={derived['rows']}")
        return {"action": action, "template": tmpl, "derived": derived, "reason": reason}

    # Anything already registered with the same wording and language, by
    # whichever route it was made.
    known = [
        t for t in db.query(WhatsAppTemplate).filter(
            WhatsAppTemplate.language_code == language,
            WhatsAppTemplate.meta_template_name.isnot(None),
        ).all()
        if normalise(t.body) == wording and button_signature(t.buttons) == signature
        # A template made from a sheet sends its visitors to its own page,
        # so one pointing somewhere else is not the same template.
        and (t.origin != ORIGIN or (t.generation or {}).get("link_target", link_target) == link_target)
    ]
    ours = [
        t for t in db.query(WhatsAppTemplate).filter(WhatsAppTemplate.origin == ORIGIN).all()
        if (t.generation or {}).get("fingerprint") == print_
    ]
    refresh_statuses(db, known + ours, force=True)

    approved = next((t for t in known if (t.status or "").upper() == "APPROVED"), None)
    if approved:
        return result("ready", approved)

    # "Draft" is what a status sync records for a template deleted on Meta's
    # side, so it is not waiting for anything.
    waiting = next((t for t in known
                    if (t.status or "").upper() not in FINAL_STATUSES | {"DRAFT"}), None)
    if waiting:
        return result("pending", waiting)

    # Our own earlier submission of this wording, newest first.
    ours.sort(key=lambda t: t.created_at, reverse=True)
    latest = ours[0] if ours else None
    if latest and (latest.status or "").upper() in ("REJECTED", "DISABLED", "PAUSED"):
        action, reason = _outcome(latest)
        return result(action, latest, reason)

    if latest and (latest.status or "").upper() == "DRAFT":
        # Never reached Meta, or was deleted there: submit it again rather
        # than leave a second row with the same wording.
        tmpl = latest
    else:
        tmpl = WhatsAppTemplate(
            template_id=uuid.uuid4().hex,
            name=_human_name(source_name, body),
            origin=ORIGIN,
            status="Draft",
            language_code=language,
            category=category,
            header_type="NONE",
            body=body,
            buttons=buttons,
        )
        db.add(tmpl)
    tmpl.buttons = buttons

    # Each submission gets a name Meta has not seen, since a deleted
    # template's name cannot be registered again straight away.
    attempt = sum((t.generation or {}).get("attempts", 0) for t in ours)
    tmpl.generation = {
        "source": "messages_sheet",
        "attempts": (tmpl.generation or {}).get("attempts", 0) + 1,
        "source_name": source_name,
        "fingerprint": print_,
        "variables": derived["variables"],
        "columns": derived["columns"],
        "examples": derived["examples"],
        "message_column": message_column,
        "phone_column": phone_column,
        "rows": derived["rows"],
        "link_target": link_target,
        "tracked": tracking_enabled() and (add_button or derived["tracked_link_in_body"]),
    }
    tmpl.meta_template_name = _meta_name(print_, attempt)
    db.commit()

    submission = WhatsAppTemplateSubmissionService(db).submit(tmpl, category=category)
    db.refresh(tmpl)

    if submission["status"] != "success":
        tmpl.meta_template_name = None
        tmpl.status = "Draft"
        gen = dict(tmpl.generation)
        gen["submit_error"] = submission.get("error")
        tmpl.generation = gen
        db.commit()
        return result("failed", tmpl, submission.get("error"))

    status = (tmpl.status or "").upper()
    if status == "APPROVED":
        return result("ready", tmpl)
    if status == "REJECTED":
        action, reason = _outcome(tmpl)
        return result(action, tmpl, reason)
    return result("created", tmpl)


def list_sheet_templates(db: Session) -> List[WhatsAppTemplate]:
    """Templates made from sheets, newest first, with Meta's review refreshed."""
    rows = (db.query(WhatsAppTemplate).filter(WhatsAppTemplate.origin == ORIGIN)
            .order_by(WhatsAppTemplate.created_at.desc()).limit(50).all())
    refresh_statuses(db, rows)
    return rows


def describe(t: WhatsAppTemplate) -> dict:
    """A sheet template as the Studio shows it."""
    action, reason = _outcome(t)
    gen = t.generation or {}
    return {
        "template_id": t.template_id,
        "name": t.name,
        "meta_template_name": t.meta_template_name,
        "status": t.status,
        "outcome": action,
        "reason": reason,
        "language_code": t.language_code,
        "category": t.category,
        "body": t.body,
        "variables": gen.get("variables") or [],
        "columns": gen.get("columns") or {},
        "examples": gen.get("examples") or {},
        "source_name": gen.get("source_name"),
        "rows": gen.get("rows"),
        "buttons": t.buttons or [],
        "link_target": gen.get("link_target"),
        "tracked": bool(gen.get("tracked")),
        "created_at": t.created_at,
    }
