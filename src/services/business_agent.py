"""
The template agent for business data: writes WhatsApp templates addressed to
the scraped businesses themselves, and learns from how earlier ones did.

The audience is a set of businesses — an export from Business Data — not
people with messages already written for them. So the agent writes the
wording, with blanks for the business's own details ({{name}}, {{category}},
{{district}}, {{state}}) that a campaign fills from each business.

What it learns from is read fresh on every round, so each campaign's results
reach the next round as soon as they are recorded:
  * every template already sent, its wording and how it did per state
    (delivered, read, link visits, button taps);
  * the Campaign Insights playbook — what has worked, and how firmly;
  * the reasons reviewers gave for rejecting earlier drafts, and the reasons
    Meta gave for rejecting earlier templates.
Nothing is fine-tuned: it is all put in front of the model as evidence.

A draft waits in the Template Studio like the poster agent's. It reaches Meta
only when someone approves it (template_studio.approve). The message text
carries {{link}}: each business's own tracked link, which records the visit
and forwards to the destination the round was given.
"""
import json
import logging
import re
import uuid
from collections import Counter
from datetime import datetime, timezone
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from src.models.whatsapp import WhatsAppTemplate
from src.services import creative_brief, image_prompts, sheet_templates
from src.services.gemini_client import GeminiClient, GeminiError, ImageUnavailable
from src.services import template_studio as studio

logger = logging.getLogger("gmap_scraper.business_agent")

KIND = "business"
MAX_VARIANTS = 3
MAX_ROWS = 20000

# The business details a template may leave blank for a campaign to fill,
# keyed by placeholder, with how the agent is told about each.
FIELDS: Dict[str, str] = {
    "name": "the business's name as listed on Google Maps",
    "category": "the kind of business, as Google Maps names it (in English, e.g. 'Insurance agency')",
    "district": "the district the business is in (in English)",
    "state": "the state the business is in (in English)",
}
# A field is offered only when nearly every business has it: a recipient
# without a value cannot be sent the template at all.
MIN_COVERAGE = 0.98

TOKEN = sheet_templates.TOKEN

# The poster agent's rule that the body carries no link does not hold here:
# the tracked link is written into the message itself.
_BUTTON_LINK_RULE = "The message body carries no URL"


def _copy_rules() -> List[str]:
    return [r for r in creative_brief.COPY_RULES if not r.startswith(_BUTTON_LINK_RULE)] + [
        "Write {{link}} exactly once, where the reader is asked to apply — it becomes each "
        "business's own tracked link. Never write a web address yourself.",
        "Put {{link}} on its own line after a call to action, and keep writing after it (the "
        "contact number, a thank-you): WhatsApp refuses a message that ends with a blank.",
    ]


def blanks_in(body: str) -> List[str]:
    """The business details a body uses, in order; {{link}} is not one."""
    out = []
    for key in TOKEN.findall(body or ""):
        if key != "link" and key not in out:
            out.append(key)
    return out


# ---------------------------------------------------------------------------
# The audience
# ---------------------------------------------------------------------------

def _field_of(header: str) -> Optional[str]:
    key = sheet_templates.column_key(header)
    return key if key in FIELDS else None


def summarise(rows: List[dict]) -> dict:
    """
    What the agent needs to know about the businesses, and which of their
    details are complete enough to use as blanks.
    """
    if not rows:
        raise ValueError("The sheet has no rows.")
    columns = {h: _field_of(h) for h in rows[0].keys()}
    by_field = {f: h for h, f in columns.items() if f}
    if "name" not in by_field:
        raise ValueError("The sheet has no business name column. Upload an export from Business Data.")

    def values(field):
        h = by_field.get(field)
        return [sheet_templates.cell_text(r.get(h)) for r in rows] if h else []

    coverage = {f: (sum(1 for v in values(f) if v) / len(rows)) for f in by_field}
    usable = [f for f in FIELDS if coverage.get(f, 0) >= MIN_COVERAGE]

    states = Counter(v for v in values("state") if v)
    categories = Counter(v for v in values("category") if v)
    districts = Counter(v for v in values("district") if v)

    # Meta wants a worked example of every blank; the first business that has
    # all of them supplies it.
    example = next(
        (r for r in rows if all(sheet_templates.cell_text(r.get(by_field[f])) for f in usable)),
        rows[0],
    )
    return {
        "rows": len(rows),
        "columns": {f: by_field[f] for f in usable},
        "usable_fields": usable,
        "coverage": {f: round(c, 3) for f, c in coverage.items()},
        "states": states.most_common(8),
        "categories": categories.most_common(12),
        "districts": districts.most_common(8),
        "main_state": states.most_common(1)[0][0] if states else None,
        "examples": {f: sheet_templates.clean_parameter(
            sheet_templates.cell_text(example.get(by_field[f]))) for f in usable},
    }


def language_for(summary: dict, override: Optional[str] = None) -> str:
    """The audience's language: as asked, else the main state's, else English."""
    if override:
        return override
    return creative_brief.language_for_state(summary.get("main_state")) or "en_US"


# ---------------------------------------------------------------------------
# What it learns from
# ---------------------------------------------------------------------------

def learning(db: Session, state: Optional[str], language_code: str) -> dict:
    """Everything the agent is shown about past templates, read fresh."""
    performance = studio.template_performance(db)
    bodies = {t.template_id: t for t in db.query(WhatsAppTemplate).all()}

    sent_templates = []
    for p in performance[:10]:
        t = bodies.get(p["template_id"])
        sent_templates.append({
            "name": p["name"],
            "language": p["language"],
            "angle": p.get("angle_key") or p.get("angle"),
            "sent": p["sent"], "delivered": p["delivered"], "read": p["read"],
            "visitors": p["visitors"], "tappers": p["tappers"],
            "response_rate": p["response_rate"], "tracked": p["tracked"],
            "by_state": p["by_state"][:3],
            "body": ((t.body or "")[:600] if t else ""),
        })

    try:
        from src.services.campaign_insights import playbook
        book = playbook(db)
        lessons = [
            f"{dim}: {v['value']} (response {v['response_rate']:.1%}, "
            f"{'evidence: ' + v['confidence'] if v['confidence'] != 'too_early' else 'too early to call'})"
            for dim, v in (book.get("recipe") or {}).items() if v.get("response_rate") is not None
        ]
        overall = book.get("overall") or {}
    except Exception:
        logger.exception("business_agent event=PLAYBOOK_UNAVAILABLE")
        lessons, overall = [], {}

    history = studio._review_history(db, state) if state else {"rejected": [], "approved": [], "tried": [], "tried_keys": {}}
    meta_rejected = [
        {"name": t.name, "reason": (t.generation or {}).get("rejected_reason") or "no reason given",
         "body": (t.body or "")[:300]}
        for t in bodies.values() if (t.status or "").upper() == "REJECTED"
    ][:6]

    return {
        "templates": sent_templates,
        "lessons": lessons,
        "overall": overall,
        "history": history,
        "mistakes": studio.past_mistakes(db, language_code),
        "photos": image_prompts.lessons(db),
        "meta_rejected": meta_rejected,
        "references": studio.approved_examples(db, language_code),
        "counts": {
            "templates": len(performance),
            "sends": sum(p["sent"] for p in performance),
            "with_responses": sum(1 for p in performance if (p["visitors"] or p["tappers"])),
        },
    }


# ---------------------------------------------------------------------------
# Writing
# ---------------------------------------------------------------------------

def _language_name(code: str) -> str:
    return creative_brief.LANGUAGES[code]["name"] if code in creative_brief.LANGUAGES else "English"


def _prompt(summary: dict, language_code: str, angles: List[str], brief: Optional[str], learned: dict) -> str:
    lang = _language_name(language_code)
    script = creative_brief.LANGUAGES[language_code]["script"] if language_code in creative_brief.LANGUAGES else "Latin"
    bullets = lambda items: "\n".join(f"- {i}" for i in items) or "- (none)"
    fields = "\n".join(f"- {{{{{f}}}}}: {FIELDS[f]}" for f in summary["usable_fields"])

    perf = []
    for t in learned["templates"]:
        rate = f"{t['response_rate']:.1%}" if t["response_rate"] is not None else "unknown"
        states = "; ".join(f"{s['state']}: sent {s['sent']}, read {s['read']}, visits {s['visitors']}, taps {s['tappers']}"
                           for s in t["by_state"])
        perf.append(
            f"- \"{t['name']}\" ({t['language']}{', angle ' + str(t['angle']) if t['angle'] else ''}): sent {t['sent']}, "
            f"delivered {t['delivered']}, read {t['read']}, link visits {t['visitors']}, button taps {t['tappers']}, "
            f"response rate {rate}{'' if t['tracked'] else ' [no delivery tracking — reads unknown]'}. By state: {states}\n"
            f"  Wording: {t['body']!r}"
        )

    history = learned["history"]
    return f"""You write WhatsApp marketing templates for Eko. They go to BUSINESSES found on Google Maps — shops, agencies, offices — inviting each business to add an SBI Kiosk (Customer Service Point) and earn extra income with Eko. You are writing to the business, not to a private person.

THE BUSINESSES THIS ROUND ({summary['rows']:,} of them):
- States: {', '.join(f'{s} ({n})' for s, n in summary['states']) or 'unknown'}
- Districts: {', '.join(f'{d} ({n})' for d, n in summary['districts']) or 'unknown'}
- Kinds of business: {', '.join(f'{c} ({n})' for c, n in summary['categories']) or 'unknown'}

BLANKS YOU MAY USE — each is filled per business when the campaign is sent. Use {{{{name}}}} once, in the greeting. Use the others only where an English value reads naturally inside {lang} text; never invent any other blank:
{fields}
- {{{{link}}}}: this business's own tracked link to apply. Required, exactly once.

Write {len(angles)} variant(s) in {lang} ({script} script), one per angle below, each built entirely around its angle so the results can be compared:
{chr(10).join(f"{i}. {k}: {creative_brief.ANGLES[k]}" for i, k in enumerate(angles, 1))}

FACTS — the only claims allowed:
{bullets(creative_brief.FACTS)}

RULES:
{bullets(_copy_rules())}
- The message must not begin or end with a blank: start with a greeting word, end with fixed text.
- Speak to the business owner about their business: what an SBI Kiosk adds to a {{{{category}}}} like theirs, in their area.
- Also write the poster that heads the message, in {lang}: the same offer as the body, in its own short words. The poster is one picture for every business, so it has no blanks.

{studio.GRAMMAR_HEADING.format(lang=lang)}
{chr(10).join(chr(10) + '---' + chr(10) + r for r in learned['references']) or f'(no approved {lang} template yet)'}

WHAT PAST TEMPLATES ACHIEVED — learn from it. Response rate = (link visits + button taps) / delivered. Prefer the tone, structure and ideas of templates that drew responses; move away from ones that did not. Results marked untracked or with few sends are weak evidence.
{chr(10).join(perf) or '- no campaign has been sent yet; rely on the facts and rules'}

PLAYBOOK — what Campaign Insights has concluded so far (overall response rate {(learned['overall'].get('response_rate') or 0):.1%}):
{bullets(learned['lessons'])}

DRAFTS A REVIEWER REJECTED, AND WHY — do not repeat these mistakes:
{bullets([f"{r['angle']}: {r['reason']}" for r in history['rejected']])}
TEMPLATES META REJECTED, AND WHY:
{bullets([f"{r['name']}: {r['reason']} — {r['body']!r}" for r in learned['meta_rejected']])}
{studio.MISTAKES_HEADING}
{bullets(learned.get('mistakes') or [])}
{studio.photo_lessons(learned.get('photos'))}
ANGLES ALREADY TRIED (find a fresh way in): {'; '.join(history['tried']) or 'none'}
{f"{chr(10)}THIS ROUND'S BRIEF FROM THE TEAM: {brief}" if brief else ''}

Answer with JSON only:
{{"variants": [{{
  "angle_key": "the key of this variant's angle",
  "angle": "one English sentence: how this variant expresses its angle",
  "learned": "one or two English sentences: which past results or rejections shaped this wording, and how",
{studio.poster_spec(lang)},
  "image_phrase": "2 to 5 words copied exactly from your headline or body, in {lang}, with no blank in them — the line printed on a sign in the photo",
  "photo_scene": "in English: who is in the photo and what is happening — a kiosk operator in professional attire (a shirt or T-shirt for a man, a saree, kurti or salwar suit for a woman; never a sage or holy man) seated behind the counter of a business like these, with a laptop and a fingerprint scanner, serving one or two local customers (for example taking a thumbprint, counting cash, handing over a passbook); the setting; the mood that suits the angle. No text, signs or logos: the sign is added separately.",
  "body": "the message in {lang}, at most {studio.BODY_LIMIT} characters, with blanks as {{{{name}}}} and {{{{link}}}}, no web address of your own",
  "footer": "at most {studio.FOOTER_LIMIT} characters, e.g. the equivalent of 'Team Eko'",
  "callback_button": "button label meaning 'Call me back', at most 20 characters"
}}]}}"""


def validate(variant: dict, language_code: str, allowed: List[str]) -> List[str]:
    """Everything wrong with one variant; empty when it can be used."""
    errors = []
    body = variant.get("body") or ""
    for key in ("angle", "body", "callback_button"):
        if not (variant.get(key) or "").strip():
            errors.append(f"{key} is missing")
    if len(body) > studio.BODY_LIMIT:
        errors.append(f"body is {len(body)} characters; the limit is {studio.BODY_LIMIT}")
    if re.search(r"https?://|www\.|kiosk\.eko\.in", body):
        errors.append("body contains a web address; write {{link}} instead, which becomes the tracked link")
    links = TOKEN.findall(body).count("link")
    if links != 1:
        errors.append("body must contain {{link}} exactly once" + (f"; it has {links}" if links else ""))
    if "7291988625" not in body.replace(" ", ""):
        errors.append(f"body does not give the contact number {creative_brief.PHONE}")
    if "**" in body:
        errors.append(studio.DOUBLE_ASTERISK)

    used = TOKEN.findall(body)
    unknown = sorted(set(used) - set(allowed) - {"link"})
    if unknown:
        errors.append("body uses blanks that cannot be filled: " + ", ".join("{{%s}}" % u for u in unknown))
    if "name" not in used:
        errors.append("body does not greet the business by {{name}}")
    stray = re.sub(TOKEN, "", body)
    if "{" in stray or "}" in stray:
        errors.append("body has a malformed blank; write them exactly as {{name}}")
    try:
        sheet_templates._check_meta_rules(body)
    except sheet_templates.DerivationError as e:
        errors.append(str(e))

    if len(variant.get("footer") or "") > studio.FOOTER_LIMIT:
        errors.append(f"footer is longer than {studio.FOOTER_LIMIT} characters")
    if len(variant.get("callback_button") or "") > studio.BUTTON_TEXT_LIMIT:
        errors.append(f"callback_button is longer than {studio.BUTTON_TEXT_LIMIT} characters")

    poster = variant.get("poster") or {}
    if language_code in creative_brief.LANGUAGES:
        errors += studio.validate_poster(poster, language_code)
        poster_texts = [v for v in poster.values() if isinstance(v, str)]
        poster_texts += [b.get("text") or "" for b in poster.get("benefits") or [] if isinstance(b, dict)]
        if any(TOKEN.search(t) for t in poster_texts):
            errors.append("the poster has a blank in it; it is one picture, the same for every business")

    phrase = variant.get("image_phrase") or ""
    if phrase:
        words = len(phrase.split())
        written = " ".join([TOKEN.sub("", body)] + [str(poster.get(k) or "") for k in studio.POSTER_FIELDS])
        if "{" in phrase or "}" in phrase:
            errors.append("image_phrase has a blank in it; it is printed as it is, the same for every business")
        elif not 2 <= words <= 5:
            errors.append(f"image_phrase has {words} words; it needs 2 to 5")
        elif studio._letters(phrase) not in studio._letters(written):
            errors.append("image_phrase is not copied exactly from the headline or body")

    if language_code in creative_brief.LANGUAGES:
        # Blanks are filled with English values, so they are left out of the
        # script check rather than counted as stray Latin.
        texts = {"body": TOKEN.sub("", body), "footer": variant.get("footer"),
                 "callback_button": variant.get("callback_button")}
        if phrase:
            texts["image_phrase"] = phrase
        for name, text in texts.items():
            for problem in creative_brief.script_problems(text or "", language_code,
                                                          require_script=name != "footer"):
                errors.append(f"{name} {problem}")
    return errors


def _clean(variant: dict) -> dict:
    def fix(text):
        return text.replace("\\n", "\n").replace("\\t", " ").strip() if isinstance(text, str) else text

    for key in ("body", "footer", "callback_button", "angle", "learned", "photo_scene", "image_phrase"):
        variant[key] = fix(variant.get(key))
    studio.clean_poster(variant.get("poster"), fix)
    return variant


def _write(client: GeminiClient, prompt: str, angles: List[str], language_code: str,
           allowed: List[str]) -> List[dict]:
    data = client.generate_json(prompt)
    variants = (data.get("variants") if isinstance(data, dict) else None) or []
    if not variants:
        raise GeminiError("The agent returned no variants")

    out = []
    for angle_key, variant in zip(angles, variants):
        variant = _clean(variant)
        errors = validate(variant, language_code, allowed)
        errors += [f"unsupported claim: {c}" for c in studio._unsupported_claims(client, variant)]
        first_errors = list(errors)
        if errors:
            repair = (
                f"{prompt}\n\nYou wrote this variant:\n{json.dumps(variant, ensure_ascii=False)}\n\n"
                "It has these problems:\n" + "\n".join(f"- {e}" for e in errors) +
                f"\n\nKeep its angle ({angle_key}: {creative_brief.ANGLES[angle_key]}). Return the corrected "
                'variant in the same JSON shape, as {"variants": [ ... one item ... ]}.'
            )
            again = _clean((client.generate_json(repair, temperature=0.4).get("variants") or [{}])[0])
            errors = validate(again, language_code, allowed)
            errors += [f"unsupported claim: {c}" for c in studio._unsupported_claims(client, again)]
            variant = again
        variant["angle_key"] = angle_key
        variant["_errors"] = errors
        variant["_first_errors"] = first_errors
        out.append(variant)
    return out


# ---------------------------------------------------------------------------
# A round
# ---------------------------------------------------------------------------

def create_placeholders(db: Session, summary: dict, count: int, brief: Optional[str],
                        language_code: str, link_target: str, source_name: Optional[str]) -> List[WhatsAppTemplate]:
    """Rows the Studio shows at once, filled in by run_generation."""
    state = summary.get("main_state")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d")
    rows = []
    for _ in range(count):
        t = WhatsAppTemplate(
            template_id=uuid.uuid4().hex,
            name=f"{state or 'Businesses'} Agent {stamp} {uuid.uuid4().hex[:5]}",
            language_code=language_code,
            category="MARKETING",
            body="",
            status=studio.GENERATING,
            origin="agent",
            target_state=state,
            header_type="NONE",
            generation={
                "kind": KIND,
                "brief": brief,
                "source_name": source_name,
                "audience": {k: summary[k] for k in ("rows", "states", "categories", "districts", "coverage")},
                "columns": summary["columns"],
                "allowed_fields": summary["usable_fields"],
                "examples": summary["examples"],
                "link_target": link_target,
            },
        )
        db.add(t)
        rows.append(t)
    db.commit()
    return rows


def run_generation(template_ids: List[str]) -> None:
    """Background entry point: writes the copy for the placeholder rows."""
    from src.database import SessionLocal

    db = SessionLocal()
    try:
        rows = db.query(WhatsAppTemplate).filter(WhatsAppTemplate.template_id.in_(template_ids)).all()
        if not rows:
            return
        first = rows[0]
        gen = first.generation or {}
        language_code = first.language_code
        allowed = gen.get("allowed_fields") or ["name"]

        def fail_all(reason: str):
            for t in rows:
                if t.status == studio.GENERATING:
                    t.status = studio.GENERATION_FAILED
                    t.generation = {**(t.generation or {}), "error": reason}
            db.commit()

        try:
            client = GeminiClient()
            learned = learning(db, first.target_state, language_code)
            angles = studio.assign_angles(len(rows), learned["history"]["tried_keys"])
            summary = {**gen["audience"], "usable_fields": allowed}
            variants = _write(client, _prompt(summary, language_code, angles, gen.get("brief"), learned),
                              angles, language_code, allowed)
            model = client.text_model()
        except Exception as e:
            logger.exception("business_agent event=WRITING_FAILED")
            fail_all(str(e) if isinstance(e, GeminiError) else f"Writing failed: {e}")
            return

        for tmpl, variant in zip(rows, variants):
            errors = variant.pop("_errors", [])
            first_errors = variant.pop("_first_errors", [])
            body = (variant.get("body") or "").strip()
            used = blanks_in(body)
            tmpl.body = body
            tmpl.footer = (variant.get("footer") or "").strip() or None
            tmpl.buttons = [
                {"type": "QUICK_REPLY", "text": (variant.get("callback_button") or "").strip()},
            ]
            tmpl.generation = {
                **tmpl.generation,
                "angle": variant.get("angle"),
                "angle_key": variant.get("angle_key"),
                "learned": variant.get("learned"),
                "learned_from": learned["counts"],
                "variables": used,
                "copy_warnings": errors,
                # Read back by later rounds; see template_studio.past_mistakes.
                "first_problems": first_errors,
                "agent_body": body,
                "poster": variant.get("poster"),
                "photo_scene": variant.get("photo_scene"),
                "image_phrase": variant.get("image_phrase"),
                "models": {"text": model},
                "tracked": sheet_templates.tracking_enabled(),
            }
            tmpl.category = "UTILITY"  # Default to UTILITY as requested
            db.commit()  # The copy is kept whatever happens to the photo.

            # The image, made from the finished text the same way as the
            # poster agent's (template_studio._make_header): the phrase on a
            # sign if it reads back right, else the poster typeset around a
            # photo with no text.
            if studio.can_make_header(tmpl.generation):
                try:
                    header = studio._make_header(client, tmpl, tmpl.generation, tmpl.target_state)
                    tmpl.generation = {**tmpl.generation, **header,
                                       "models": {"text": model, "image": client.last_used_image_model}}
                except ImageUnavailable as e:
                    studio._park_for_photo(tmpl, dict(tmpl.generation), e)
                    db.commit()
                    continue
                except Exception as e:
                    # The message can be sent without a photo; the reviewer is told.
                    logger.exception(f"business_agent event=PHOTO_FAILED template_id={tmpl.template_id}")
                    tmpl.generation = {**tmpl.generation, "photo_error": str(e)}
            tmpl.status = studio.AWAITING_APPROVAL
            db.commit()
            logger.info(f"business_agent event=DRAFT_READY template_id={tmpl.template_id} "
                        f"state={tmpl.target_state} angle={variant.get('angle_key')}")
        db.commit()
        fail_all("The agent returned fewer variants than requested")
    finally:
        db.close()


def update(db: Session, tmpl: WhatsAppTemplate, body: Optional[str], footer: Optional[str],
           buttons: Optional[dict]) -> List[str]:
    """A reviewer's edit. Saved either way; the problems are returned."""
    gen = dict(tmpl.generation or {})
    if body is not None:
        tmpl.body = body.strip()
        gen["variables"] = blanks_in(tmpl.body)
    if footer is not None:
        tmpl.footer = footer.strip() or None
    if buttons:
        current = [dict(b) for b in (tmpl.buttons or [])]
        for b in current:
            if b.get("type") == "URL" and buttons.get("apply_button"):
                b["text"] = buttons["apply_button"].strip()
            if b.get("type") == "QUICK_REPLY" and buttons.get("callback_button"):
                b["text"] = buttons["callback_button"].strip()
        tmpl.buttons = current
    tmpl.generation = gen
    db.commit()
    labels = {b.get("type"): b.get("text") for b in (tmpl.buttons or [])}
    problems = validate({"angle": gen.get("angle"), "body": tmpl.body, "footer": tmpl.footer or "",
                         "callback_button": labels.get("QUICK_REPLY")},
                        tmpl.language_code, gen.get("allowed_fields") or ["name"])
    phrase = gen.get("image_phrase")
    written = " ".join([tmpl.body or ""] + [str(v) for v in (gen.get("poster") or {}).values() if isinstance(v, str)])
    if phrase and tmpl.header_content and studio._letters(phrase) not in studio._letters(written):
        problems.append(f"the image still shows “{phrase}”, which is no longer in the message; "
                        "New photo makes one without it")
    return problems


def is_business_draft(t: WhatsAppTemplate) -> bool:
    return t.origin == "agent" and (t.generation or {}).get("kind") == KIND


def list_drafts(db: Session) -> List[WhatsAppTemplate]:
    """This agent's drafts, newest first, with Meta's review kept current."""
    rows = [t for t in db.query(WhatsAppTemplate).filter(WhatsAppTemplate.origin == "agent")
            .order_by(WhatsAppTemplate.created_at.desc()).limit(200).all() if is_business_draft(t)][:60]
    sheet_templates.refresh_statuses(db, rows)
    return rows
