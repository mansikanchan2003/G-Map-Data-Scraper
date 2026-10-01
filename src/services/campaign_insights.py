"""
What made campaigns work: per-campaign reports, the standing playbook, and the
history of what the playbook has concluded over time.

Everything is computed from one row per recipient (a "fact") carrying what the
recipient saw (template, its format and language), who they were (category,
state, district, tehsil), when it was sent (IST time of day, weekday) and what
happened (sent, delivered, read, responded). Any dimension, or any combination
of them, is then just a grouping of those facts.

The measure of success is the RESPONSE RATE: recipients who visited the
tracked link or tapped a button, per message sent. It is the one outcome
recorded for every campaign — delivered and read only exist once the webhook
is live — so it is the only one comparable across all of them.

Small samples lie, and most segments are small, so every rate carries a 95%
Wilson interval and a confidence label. A segment is called better or worse
than the rest only when the intervals say so; otherwise the page says the data
is not there yet, rather than dressing up noise as a finding.
"""
import itertools
import logging
import math
import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Dict, Iterable, List, Optional, Tuple

from sqlalchemy.orm import Session

from src.models import Business
from src.services import creative_brief
from src.models.whatsapp import (
    WhatsAppButtonClick, WhatsAppCampaign, WhatsAppCampaignRecipient,
    WhatsAppLinkClick, WhatsAppTemplate, HUMAN_LINK_CLICK,
)

logger = logging.getLogger("gmap_scraper.campaign_insights")

IST = timezone(timedelta(hours=5, minutes=30))

# Below this many sends a segment is reported but never ranked or concluded on.
MIN_SENT = 30
# No verdict on fewer responses than this across a comparison, or fewer than
# MIN_SEGMENT_RESPONSES inside the segment: one reply in 306 is noise, and
# was being reported as "likely best" before this existed.
MIN_RESPONSES = 10
MIN_SEGMENT_RESPONSES = 3
# A campaign to fewer recipients than this is the team testing on its own
# phones. Their taps ("It Worked!") are not customer behaviour and made
# "Unknown" the best state and category on real data, so tests are kept out
# of the learning — each still gets its own report.
TEST_CAMPAIGN_MAX = 10
# A lift smaller than this is not worth a suggestion even when significant.
MIN_LIFT = 0.2

# Meta language code -> Unicode block, for judging the language a template is
# actually written in. Registered codes cannot be trusted: every Hindi
# template so far went to Meta as en_US.
_SCRIPTS = {
    "pa": "਀-੿", "gu": "઀-૿", "bn": "ঀ-৿",
    "ta": "஀-௿", "te": "ఀ-౿", "kn": "ಀ-೿",
    "ml": "ഀ-ൿ", "hi": "ऀ-ॣ०-ॿ",
}
_LANG_NAMES = {"hi": "Hindi", "pa": "Punjabi", "gu": "Gujarati", "mr": "Marathi", "bn": "Bengali",
               "ta": "Tamil", "te": "Telugu", "kn": "Kannada", "ml": "Malayalam", "en": "English"}

# The language people in each state read, from the one table the template
# agent writes by too, so the two can never disagree. Devanagari is shared by
# Hindi and Marathi, so a Hindi-script body counts as a match in Maharashtra.
STATE_LANGUAGE = creative_brief.STATE_LANGUAGES


def body_language(body: str) -> str:
    counts = {code: len(re.findall(f"[{block}]", body or "")) for code, block in _SCRIPTS.items()}
    code, n = max(counts.items(), key=lambda kv: kv[1])
    return code if n else "en"


def _time_of_day(hour: int) -> str:
    if 6 <= hour < 9:
        return "Early morning (6–9)"
    if 9 <= hour < 12:
        return "Morning (9–12)"
    if 12 <= hour < 15:
        return "Afternoon (12–15)"
    if 15 <= hour < 18:
        return "Late afternoon (15–18)"
    if 18 <= hour < 21:
        return "Evening (18–21)"
    return "Night (21–6)"


def _buttons_label(buttons) -> str:
    kinds = sorted({b.get("type") for b in (buttons or []) if b.get("type")})
    names = {"URL": "Link button", "QUICK_REPLY": "Quick reply", "PHONE_NUMBER": "Call button"}
    return " + ".join(names.get(k, k) for k in kinds) or "No buttons"


def _body_length(body: str) -> str:
    n = len(body or "")
    return "Short (<400 chars)" if n < 400 else "Medium (400–800)" if n <= 800 else "Long (>800)"


# ---------------------------------------------------------------------------
# Dimensions. Each is a key on a fact; the label is what the page shows.
# ---------------------------------------------------------------------------

DIMENSIONS: Dict[str, dict] = {
    "template": {"label": "Template", "group": "Template"},
    "header": {"label": "Header media", "group": "Template"},
    "buttons": {"label": "Buttons", "group": "Template"},
    "body_length": {"label": "Message length", "group": "Template"},
    "language": {"label": "Message language", "group": "Template"},
    "language_match": {"label": "Language vs recipient's state", "group": "Template"},
    "state": {"label": "State", "group": "Location"},
    "district": {"label": "District", "group": "Location"},
    "tehsil": {"label": "Tehsil", "group": "Location"},
    "category": {"label": "Business category", "group": "Category"},
    "time_of_day": {"label": "Time of day (IST)", "group": "Timing"},
    "weekday": {"label": "Day of week", "group": "Timing"},
}

# The groups the user asked about, in the order the page shows them.
GROUPS = ["Template", "Location", "Category", "Timing"]


# ---------------------------------------------------------------------------
# Facts
# ---------------------------------------------------------------------------

def _aware(value: Optional[datetime]) -> Optional[datetime]:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def is_unknown(value) -> bool:
    return str(value).startswith("Unknown") or str(value).startswith("(deleted")


def test_campaign_ids(db: Session) -> set:
    return {c.campaign_id for c in db.query(WhatsAppCampaign).all()
            if (c.total_contacts or 0) < TEST_CAMPAIGN_MAX}


def load_facts(db: Session, campaign_ids: Optional[Iterable[str]] = None,
               include_tests: bool = False) -> List[dict]:
    """
    One fact per recipient a message was actually sent to.

    Test campaigns are left out unless asked for by id or include_tests.
    """
    q = db.query(WhatsAppCampaignRecipient).filter(WhatsAppCampaignRecipient.sent_at.isnot(None))
    if campaign_ids is not None:
        q = q.filter(WhatsAppCampaignRecipient.campaign_id.in_(list(campaign_ids)))
    elif not include_tests:
        tests = test_campaign_ids(db)
        if tests:
            q = q.filter(~WhatsAppCampaignRecipient.campaign_id.in_(tests))
    recipients = q.all()
    if not recipients:
        return []

    ids = [r.recipient_id for r in recipients]
    responded = set()
    visited, tapped = set(), set()
    for chunk in _chunks(ids, 500):
        visited |= {rid for (rid,) in db.query(WhatsAppLinkClick.recipient_id)
                    .filter(WhatsAppLinkClick.recipient_id.in_(chunk), HUMAN_LINK_CLICK).distinct()}
        tapped |= {rid for (rid,) in db.query(WhatsAppButtonClick.recipient_id)
                   .filter(WhatsAppButtonClick.recipient_id.in_(chunk)).distinct()}
    responded = visited | tapped

    campaigns = {c.campaign_id: c for c in db.query(WhatsAppCampaign).filter(
        WhatsAppCampaign.campaign_id.in_({r.campaign_id for r in recipients})).all()}
    templates = {t.template_id: t for t in db.query(WhatsAppTemplate).filter(
        WhatsAppTemplate.template_id.in_({c.template_id for c in campaigns.values() if c.template_id})).all()}

    # The business behind a recipient: by id where it was stored, otherwise by
    # phone, which is what the audience was selected by. Most recipients so
    # far carry no id.
    by_id, by_phone = {}, {}
    biz_ids = [r.business_id for r in recipients if r.business_id]
    for chunk in _chunks(biz_ids, 500):
        for b in db.query(Business).filter(Business.business_id.in_(chunk)):
            by_id[b.business_id] = b
    phones = [r.phone for r in recipients if not r.business_id and r.phone]
    for chunk in _chunks(phones, 500):
        for b in db.query(Business).filter(Business.phone.in_(chunk)):
            by_phone.setdefault(b.phone, b)

    template_info = {}
    for t in templates.values():
        lang = body_language(t.body)
        header = (t.header_type or "NONE").upper()
        template_info[t.template_id] = {
            "_tracked_link": "{{link}}" in (t.body or "") or any(
                b.get("type") == "URL" and "{{" in (b.get("url") or "") for b in (t.buttons or [])),
            "template": t.name,
            "header": {"IMAGE": "Image", "VIDEO": "Video", "TEXT": "Text header"}.get(header, "No header"),
            "buttons": _buttons_label(t.buttons),
            "body_length": _body_length(t.body),
            "language": _LANG_NAMES.get(lang, lang),
            "_lang": lang,
        }

    facts = []
    for r in recipients:
        c = campaigns.get(r.campaign_id)
        info = template_info.get(c.template_id if c else None) or {
            "template": "(deleted template)", "header": "Unknown", "buttons": "Unknown",
            "body_length": "Unknown", "language": "Unknown", "_lang": None, "_tracked_link": False,
        }
        b = by_id.get(r.business_id) if r.business_id else by_phone.get(r.phone)
        state = (b.state if b else None) or "Unknown"
        wanted = STATE_LANGUAGE.get(state.lower())
        lang = info["_lang"]
        if not wanted or not lang:
            match = "Unknown"
        elif lang == wanted or (wanted == "mr" and lang == "hi"):
            match = "In the state's language"
        else:
            match = "Different language"

        sent_ist = _aware(r.sent_at).astimezone(IST)
        facts.append({
            "campaign_id": r.campaign_id,
            "template_id": c.template_id if c else None,
            **{k: v for k, v in info.items() if not k.startswith("_")},
            "language_match": match,
            "state": state,
            "district": (b.district if b else None) or "Unknown",
            "tehsil": (b.tehsil if b else None) or "Unknown",
            "category": (b.category if b else None) or "Unknown (uploaded list)",
            "time_of_day": _time_of_day(sent_ist.hour),
            "weekday": sent_ist.strftime("%A"),
            "sent": 1,
            "delivered": int(r.delivered_at is not None),
            "read": int(r.read_at is not None),
            "failed": int(r.failed_at is not None),
            "visited": int(r.recipient_id in visited),
            "tapped": int(r.recipient_id in tapped),
            "responded": int(r.recipient_id in responded),
            "failure_code": r.failure_code,
            "tracked_link": info["_tracked_link"],
        })
    return facts


def _chunks(items: list, size: int):
    for i in range(0, len(items), size):
        yield items[i:i + size]


# ---------------------------------------------------------------------------
# Statistics
# ---------------------------------------------------------------------------

def wilson(k: int, n: int, z: float = 1.96) -> Tuple[float, float]:
    """95% Wilson score interval for k successes in n trials."""
    if n == 0:
        return 0.0, 0.0
    p = k / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return max(0.0, centre - half), min(1.0, centre + half)


def _stats(rows: List[dict]) -> dict:
    sent = len(rows)
    out = {k: sum(r[k] for r in rows) for k in ("delivered", "read", "failed", "visited", "tapped", "responded")}
    out["sent"] = sent
    out["response_rate"] = out["responded"] / sent if sent else 0.0
    out["ci_low"], out["ci_high"] = wilson(out["responded"], sent)
    # Delivery and read rates only mean something where Meta reported at all.
    reported = out["delivered"] + out["failed"]
    out["tracked"] = reported > 0
    out["delivery_rate"] = out["delivered"] / reported if reported else None
    out["read_rate"] = out["read"] / out["delivered"] if out["delivered"] else None
    return out


def _verdict(seg: dict, rest: dict) -> Tuple[str, str]:
    """
    (confidence, direction) of a segment against everything else.

    strong    — the two 95% intervals do not overlap
    likely    — a sizeable lift on enough sends, intervals overlapping
    too_early — not enough sends or responses to say anything
    """
    if (seg["sent"] < MIN_SENT or rest["sent"] < MIN_SENT
            or seg["responded"] + rest["responded"] < MIN_RESPONSES):
        return "too_early", "none"
    if seg["ci_low"] > rest["ci_high"]:
        return "strong", "better"
    if seg["ci_high"] < rest["ci_low"]:
        return "strong", "worse"
    base = rest["response_rate"]
    if seg["responded"] >= MIN_SEGMENT_RESPONSES and base and abs(seg["response_rate"] - base) / base >= 0.5:
        return "likely", "better" if seg["response_rate"] > base else "worse"
    return "no_difference", "none"


def aggregate(facts: List[dict], dims: Tuple[str, ...], min_sent: int = 1) -> List[dict]:
    """Groups facts by a combination of dimensions and scores each group."""
    overall = _stats(facts) if facts else None
    groups: Dict[tuple, List[dict]] = {}
    for f in facts:
        groups.setdefault(tuple(f[d] for d in dims), []).append(f)

    out = []
    for key, rows in groups.items():
        if len(rows) < min_sent:
            continue
        seg = _stats(rows)
        rest_rows_count = len(facts) - len(rows)
        rest = _stats_from_totals(overall, seg) if rest_rows_count else None
        confidence, direction = _verdict(seg, rest) if rest else ("too_early", "none")
        base = rest["response_rate"] if rest else 0.0
        out.append({
            "values": dict(zip(dims, key)),
            **seg,
            "lift": (seg["response_rate"] - base) / base if base else None,
            "confidence": confidence,
            "direction": direction,
        })
    # Ranked by the pessimistic end of the interval, so a lucky 1-of-2 does
    # not outrank a steady 30-of-1,000.
    out.sort(key=lambda r: (-r["ci_low"], -r["sent"]))
    return out


def _stats_from_totals(overall: dict, seg: dict) -> dict:
    rest = {k: overall[k] - seg[k] for k in ("sent", "delivered", "read", "failed", "visited", "tapped", "responded")}
    n = rest["sent"]
    rest["response_rate"] = rest["responded"] / n if n else 0.0
    rest["ci_low"], rest["ci_high"] = wilson(rest["responded"], n)
    return rest


# ---------------------------------------------------------------------------
# The playbook: what works, across every campaign so far
# ---------------------------------------------------------------------------

def playbook(db: Session, facts: Optional[List[dict]] = None) -> dict:
    facts = load_facts(db) if facts is None else facts
    overall = _stats(facts) if facts else _stats([])

    by_dimension = {}
    for dim in DIMENSIONS:
        rows = aggregate(facts, (dim,))
        # "Unknown" is shown in the tables but never recommended: it is a gap
        # in the data, not a place or a category anyone can target.
        ranked = [r for r in rows if r["sent"] >= MIN_SENT and not is_unknown(r["values"][dim])]
        best = next((r for r in ranked if r["direction"] == "better"), None)
        worst = next((r for r in reversed(ranked) if r["direction"] == "worse"), None)
        by_dimension[dim] = {
            "label": DIMENSIONS[dim]["label"],
            "group": DIMENSIONS[dim]["group"],
            "segments": len(rows),
            "best": best,
            "worst": worst,
            # The leader even without a verdict, so the page can say what is
            # ahead so far while making clear it is not yet a conclusion.
            "leader": ranked[0] if ranked else None,
        }

    # Every pair of dimensions, keeping the combinations that stand out.
    combos = []
    for a, b in itertools.combinations(DIMENSIONS, 2):
        if {a, b} <= {"state", "district", "tehsil"}:
            continue  # a district already names its state
        for row in aggregate(facts, (a, b), min_sent=MIN_SENT):
            if row["direction"] == "better" and not any(is_unknown(v) for v in row["values"].values()):
                combos.append(row)
    combos.sort(key=lambda r: (0 if r["confidence"] == "strong" else 1, -r["ci_low"]))

    # The templates people responded to most, with their creative, so the
    # next ones can be modelled on them.
    winners = []
    for row in [r for r in aggregate(facts, ("template",)) if not is_unknown(r["values"]["template"])][:6]:
        tid = next((f["template_id"] for f in facts if f["template"] == row["values"]["template"]), None)
        t = db.query(WhatsAppTemplate).filter(WhatsAppTemplate.template_id == tid).first() if tid else None
        winners.append({**row, "template_id": tid,
                        "header_content": t.header_content if t else None,
                        "body": t.body if t else None})

    recipe = {}
    for dim in ("template", "state", "category", "time_of_day", "weekday", "language_match"):
        entry = by_dimension[dim]
        pick = entry["best"] or entry["leader"]
        if pick:
            recipe[dim] = {"value": pick["values"][dim], "confidence": pick["confidence"]
                           if entry["best"] else "too_early", "response_rate": pick["response_rate"]}

    return {
        "computed_at": datetime.now(timezone.utc).isoformat(),
        "overall": overall,
        "campaigns": len({f["campaign_id"] for f in facts}),
        "test_campaigns_excluded": len(test_campaign_ids(db)),
        "thresholds": {"min_sent": MIN_SENT, "min_responses": MIN_RESPONSES,
                       "test_campaign_max": TEST_CAMPAIGN_MAX},
        "coverage": _coverage(facts),
        "by_dimension": by_dimension,
        "combinations": combos[:25],
        "winning_templates": winners,
        "recipe": recipe,
    }


def _coverage(facts: List[dict]) -> dict:
    """How much of the data can support a conclusion at all."""
    n = len(facts) or 1
    return {
        "sent": len(facts),
        "with_delivery_report": sum(1 for f in facts if f["delivered"] or f["failed"]) / n,
        "with_known_state": sum(1 for f in facts if f["state"] != "Unknown") / n,
        "with_known_category": sum(1 for f in facts if not f["category"].startswith("Unknown")) / n,
        "responses": sum(f["responded"] for f in facts),
    }


# ---------------------------------------------------------------------------
# One campaign: how it did, and what might have made the difference
# ---------------------------------------------------------------------------

def _pct(x: Optional[float]) -> str:
    return "—" if x is None else f"{x * 100:.1f}%"


def campaign_report(db: Session, campaign_id: str, history: Optional[dict] = None) -> dict:
    campaign = db.query(WhatsAppCampaign).filter(WhatsAppCampaign.campaign_id == campaign_id).first()
    if not campaign:
        raise KeyError(campaign_id)

    facts = load_facts(db, [campaign_id])
    metrics = _stats(facts)
    is_test = (campaign.total_contacts or 0) < TEST_CAMPAIGN_MAX
    metrics.update({
        "total_contacts": campaign.total_contacts,
        "skipped": campaign.skipped_count,
        "failed_to_send": campaign.failed_count,
    })
    history = history or playbook(db)

    breakdowns = {}
    for dim in ("state", "district", "category", "time_of_day", "language_match"):
        breakdowns[dim] = aggregate(facts, (dim,))[:15]

    return {
        "campaign_id": campaign_id,
        "name": campaign.name,
        "is_test": is_test,
        "status": campaign.status,
        "started_at": campaign.started_at.isoformat() if campaign.started_at else None,
        "template_id": campaign.template_id,
        "template": facts[0]["template"] if facts else None,
        "metrics": metrics,
        "vs_all_campaigns": None if is_test else _vs(metrics, history["overall"]),
        "breakdowns": breakdowns,
        "suggestions": suggestions(facts, metrics, history),
    }


def _vs(metrics: dict, overall: dict) -> Optional[float]:
    """
    This campaign's response rate against all campaigns — only once both sides
    carry enough evidence. Against one response in two thousand, any campaign
    reads as -100% or +300%, which is arithmetic, not a finding.
    """
    base = overall.get("response_rate")
    if not base or metrics["sent"] < MIN_SENT or overall.get("responded", 0) < MIN_RESPONSES:
        return None
    return (metrics["response_rate"] - base) / base


def suggestions(facts: List[dict], metrics: dict, history: dict) -> List[dict]:
    """
    What might have worked — or held this campaign back — per factor.

    Each suggestion names its evidence and confidence. Where the data cannot
    support a conclusion the suggestion says so, instead of guessing; the
    early campaigns will produce mostly those, and that is the honest answer.
    """
    out: List[dict] = []

    def add(factor, kind, message, confidence, evidence=None):
        out.append({"factor": factor, "kind": kind, "message": message,
                    "confidence": confidence, "evidence": evidence})

    if not facts:
        add("Data", "warning", "Nothing was sent in this campaign, so there is nothing to learn from yet.", "strong")
        return out
    if len(facts) < TEST_CAMPAIGN_MAX:
        add("Data", "info",
            f"Sent to {len(facts)} recipient(s), so it is treated as a test and kept out of the playbook.",
            "strong")
        return out

    # Tracking gaps come first: without them nothing below can be trusted.
    if not metrics["tracked"]:
        add("Data", "warning",
            "Meta never reported delivery or reads for this campaign — the webhook was not live when it ran. "
            "Only link visits and button taps are known.", "strong")
    # Judged from the template as it is now, which may have been edited since
    # the campaign ran — so a recorded visit overrides it.
    if not facts[0]["tracked_link"] and metrics["visited"] == 0:
        add("Data", "warning",
            "This template's link is not tracked — it is written into the body as a plain URL — so nobody's "
            "visit could be counted. Use {{link}} in the body, or an Apply button pointing at /r/{{1}}, "
            "so the next campaign can be measured.", "strong")
    elif metrics["responded"] == 0 and metrics["sent"] >= MIN_SENT:
        add("Data", "warning",
            f"No one visited the link or tapped a button out of {metrics['sent']} sent.", "strong")

    # Delivery problems Meta named.
    codes: Dict[str, int] = {}
    for f in facts:
        if f["failure_code"]:
            codes[f["failure_code"]] = codes.get(f["failure_code"], 0) + 1
    if codes.get("131049"):
        add("Delivery", "warning",
            f"Meta held back {codes['131049']} message(s) (131049) to protect engagement — recipients who get many "
            "marketing messages without responding. Fewer, better-targeted sends recover this.", "strong")

    # Template: this one against the best template on record.
    tmpl_best = history["by_dimension"]["template"]
    this_template = facts[0]["template"]
    best = tmpl_best["best"] or tmpl_best["leader"]
    confirmed = bool(tmpl_best["best"])
    if best and best["values"]["template"] != this_template:
        lead = "has the best response on record" if confirmed else "leads so far"
        tail = "." if confirmed else " — too few responses yet to call it."
        add("Template", "opportunity",
            f"“{best['values']['template']}” {lead} ({_pct(best['response_rate'])} of {best['sent']} sent) "
            f"against this campaign's {_pct(metrics['response_rate'])}{tail}",
            best["confidence"] if confirmed else "too_early",
            {"template": best["values"]["template"], "response_rate": best["response_rate"]})
    elif best:
        add("Template", "strength",
            "This is the best-performing template on record." if confirmed else
            "This template leads so far, but there are too few responses yet to call it.",
            best["confidence"] if confirmed else "too_early")

    # Language: sent in a language the recipients do not read.
    mismatch = [f for f in facts if f["language_match"] == "Different language"]
    if mismatch:
        share = len(mismatch) / len(facts)
        states = sorted({f["state"] for f in mismatch})
        add("Template", "warning",
            f"{len(mismatch)} of {len(facts)} recipients ({share * 100:.1f}%, in {', '.join(states[:4])}) "
            f"received the message in {mismatch[0]['language']}, which is not their state's language. "
            "Send each state its own language's template.", "strong")

    # Within the campaign: which states, districts and categories pulled their weight.
    for dim, factor in (("state", "Location"), ("district", "Location"), ("category", "Category"),
                        ("time_of_day", "Timing")):
        rows = aggregate(facts, (dim,))
        for r in rows:
            if r["direction"] == "better" and (r["lift"] or 0) >= MIN_LIFT:
                add(factor, "strength",
                    f"{DIMENSIONS[dim]['label']} “{r['values'][dim]}” responded at {_pct(r['response_rate'])} "
                    f"vs {_pct(metrics['response_rate'])} overall — target more of it.", r["confidence"], r["values"])
                break
        for r in reversed(rows):
            if r["direction"] == "worse":
                add(factor, "weakness",
                    f"{DIMENSIONS[dim]['label']} “{r['values'][dim]}” lagged ({_pct(r['response_rate'])} of "
                    f"{r['sent']} sent) — consider leaving it out or trying a different template there.",
                    r["confidence"], r["values"])
                break

    # Against history: was this sent at a good time, to good categories?
    for dim, factor in (("time_of_day", "Timing"), ("weekday", "Timing"), ("category", "Category"),
                        ("state", "Location")):
        hist = history["by_dimension"][dim]["best"]
        if not hist:
            continue
        used = {f[dim] for f in facts}
        if hist["values"][dim] not in used:
            add(factor, "opportunity",
                f"Across all campaigns, {DIMENSIONS[dim]['label'].lower()} “{hist['values'][dim]}” responds best "
                f"({_pct(hist['response_rate'])}); this campaign did not use it.", hist["confidence"], hist["values"])

    if not any(s["kind"] in ("strength", "weakness", "opportunity") and s["confidence"] in ("strong", "likely")
               for s in out):
        add("Data", "info",
            f"With {metrics['responded']} response(s) from {metrics['sent']} sent, no factor stands out yet. "
            "Each campaign adds to the record; conclusions firm up as responses accumulate.", "too_early")
    return out


# ---------------------------------------------------------------------------
# Saving it: per-campaign reports and playbook snapshots
# ---------------------------------------------------------------------------

def refresh_campaign(db: Session, campaign_id: str, history: Optional[dict] = None):
    from src.models.insights import CampaignInsight

    report = campaign_report(db, campaign_id, history)
    row = db.query(CampaignInsight).filter(CampaignInsight.campaign_id == campaign_id).first()
    if row is None:
        row = CampaignInsight(campaign_id=campaign_id)
        db.add(row)
    row.metrics = report["metrics"]
    row.breakdowns = report["breakdowns"]
    row.suggestions = report["suggestions"]
    row.vs_all_campaigns = report["vs_all_campaigns"]
    row.computed_at = datetime.now(timezone.utc)
    db.commit()
    return row, report


def record_snapshot(db: Session, trigger: str, campaign_id: Optional[str] = None,
                    book: Optional[dict] = None):
    """
    Saves what the playbook concludes right now, so the page can show how the
    conclusions have moved as campaigns accumulate.
    """
    from src.models.insights import InsightSnapshot

    book = book or playbook(db)
    compact = {
        "overall": book["overall"],
        "coverage": book["coverage"],
        "recipe": book["recipe"],
        "best": {dim: (entry["best"] or entry["leader"] or {}).get("values", {}).get(dim)
                 for dim, entry in book["by_dimension"].items()},
        "confident": {dim: bool(entry["best"]) for dim, entry in book["by_dimension"].items()},
    }
    snap = InsightSnapshot(
        snapshot_id=uuid.uuid4().hex,
        trigger=trigger,
        campaign_id=campaign_id,
        campaigns=book["campaigns"],
        recipients=book["overall"]["sent"],
        responses=book["overall"]["responded"],
        playbook=compact,
    )
    db.add(snap)
    db.commit()
    return snap


def on_campaign_finished(campaign_id: str) -> None:
    """
    Called when a campaign finishes. Saves its report and a new playbook
    snapshot. Never raises: a failed insight must not fail a campaign.
    """
    from src.database import SessionLocal

    db = SessionLocal()
    try:
        book = playbook(db)
        refresh_campaign(db, campaign_id, book)
        record_snapshot(db, "campaign_finished", campaign_id, book)
    except Exception:
        db.rollback()
        logger.exception(f"campaign_insights event=REFRESH_FAILED campaign_id={campaign_id}")
    finally:
        db.close()
