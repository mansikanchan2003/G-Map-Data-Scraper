"""
A face-to-face visit by our District Coordinator, to build trust (the user, 19 Nov 2026).

Offered only to people in a district where we have a DC (dc_network), once each. Where in
the chat it goes is Claude CLI's call: it reads where our leads stop and doubt, picks one of
POINTS, and the bot keeps to that plan (kept in app_settings under dc_visit_plan). Until
Claude has planned, it goes when someone doubts we are genuine.

Whoever never reaches that point still gets it: after QUIET_AFTER without a word from them,
it goes as a reminder ("dc_visit" in nudge_messages), as a Meta template once the 24-hour
window has closed. The offer is a must in a DC's district.

A "yes" to it is the disposition "Wants a DC visit": a ticket, and an email to the team and
to Biswajit Sir, who arranges the visit (followups.DC_VISIT_NOTIFY).
"""
import json
import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from src.models.app_setting import AppSetting

PLAN_KEY = "dc_visit_plan"
PURPOSE = "dc_visit"
# Where in the chat it can go (Claude CLI picks one).
POINTS: Dict[str, str] = {
    # Mansi's choice (19 Nov 2026): someone who stops part-way gets the bot's usual reminder
    # first; the next reminder is this offer, in place of the next follow-up.
    "after_nudge": "In place of the next reminder, once the bot's first reminder went unanswered",
    "after_pin": "Right after they send a PIN code in a DC's district, before the education question",
    "trust": "When they doubt Eko is genuine or ask who we are",
    "cannot_invest": "When they say they cannot invest ₹3–5 lakh for SBI",
    "docs_not_ready": "When they say their documents are not ready",
}
DEFAULT_POINT = "after_nudge"
# How long the bot's first reminder waits for a reply before the offer goes in its place.
AFTER_NUDGE = timedelta(hours=24)
QUIET_AFTER = timedelta(days=2)
ANSWER_WITHIN = timedelta(days=7)
REPLAN_EVERY = timedelta(days=7)

_YES = re.compile(r"\b(yes|yess|yeah|yup|ok|okay|sure|haan|haa|ha|han|hanji|haanji|ji|theek|thik|aaiye|aaiyega|aao|"
                  r"visit|milna|milenge|chalega)\b|हाँ|हां|ठीक|જી|હા|ਹਾਂ|हो|হ্যাঁ|ஆம்|అవును|ಹೌದು|അതെ|ହଁ", re.I)
_NO = re.compile(r"\b(no|nahi|nhi|nahin|not now|mat|baad mein|later)\b|नहीं|ના|ਨਹੀਂ|नको|না", re.I)

THANKS = {
    "en": "Thank you 🙏 Our team will call you to fix a time for the District Coordinator's visit.",
    "hi": "धन्यवाद 🙏 हमारी टीम District Coordinator की मुलाक़ात का समय तय करने के लिए आपको कॉल करेगी।",
    "hinglish": "Dhanyavaad 🙏 Hamari team District Coordinator ki mulaqaat ka time tay karne ke liye aapko call karegi.",
    "gu": "આભાર 🙏 ડિસ્ટ્રિક્ટ કોઓર્ડિનેટરની મુલાકાતનો સમય નક્કી કરવા અમારી ટીમ તમને કૉલ કરશે.",
    "pa": "ਧੰਨਵਾਦ 🙏 ਡਿਸਟ੍ਰਿਕਟ ਕੋਆਰਡੀਨੇਟਰ ਦੀ ਮੁਲਾਕਾਤ ਦਾ ਸਮਾਂ ਤੈਅ ਕਰਨ ਲਈ ਸਾਡੀ ਟੀਮ ਤੁਹਾਨੂੰ ਕਾਲ ਕਰੇਗੀ।",
    "mr": "धन्यवाद 🙏 District Coordinatorच्या भेटीची वेळ ठरवण्यासाठी आमची टीम तुम्हाला कॉल करेल.",
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def plan(db: Session) -> dict:
    row = db.query(AppSetting).filter(AppSetting.key == PLAN_KEY).first()
    try:
        held = json.loads(row.value) if row and row.value else {}
    except ValueError:
        held = {}
    if held.get("point") not in POINTS:
        return {"point": DEFAULT_POINT, "by": "Mansi", "why": "In place of the next reminder after the first one went unanswered."}
    return held


def save_plan(db: Session, point: str, why: str, by: str) -> dict:
    if point not in POINTS:
        raise ValueError(f"Unknown point {point!r}")
    value = {"point": point, "why": (why or "")[:400], "by": by, "at": _now().isoformat()}
    row = db.query(AppSetting).filter(AppSetting.key == PLAN_KEY).first()
    if row is None:
        row = AppSetting(key=PLAN_KEY)
        db.add(row)
    row.value = json.dumps(value)
    db.commit()
    return value


def place_of(db: Session, conv) -> tuple:
    """(district, state) of their PIN, as kept on the chat; looked up once when missing."""
    from src.services import pincode_coverage
    data = conv.bot_data or {}
    for key in ("coverage", "typed_pin"):
        held = data.get(key) or {}
        geo = held.get("geo") or {}
        if geo.get("district"):
            return geo.get("district"), geo.get("state")
    pin = (data.get("coverage") or {}).get("pincode") or (data.get("typed_pin") or {}).get("pincode")
    if not pin:
        return None, None
    try:
        geo = pincode_coverage.geography(db, pin) or {}
    except Exception:
        geo = {}
    return geo.get("district"), geo.get("state")


def dc_of(db: Session, conv) -> Optional[dict]:
    from src.services import dc_network
    rows = dc_network.load(db)
    if not rows:
        return None
    district, state = place_of(db, conv)
    return dc_network.dc_for(db, district, state, rows)


def offered(conv) -> bool:
    return bool((conv.bot_data or {}).get("dc_offer"))


def _mark(conv, point: str, dc: dict) -> None:
    conv.bot_data = {**(conv.bot_data or {}), "dc_offer": {
        "at": _now().isoformat(), "point": point, "district": dc.get("district"), "dc": dc.get("dc")}}
    flag_modified(conv, "bot_data")


def offer_at(db: Session, conv, point: str) -> bool:
    """At one of POINTS in the chat: the offer, when it is the planned point and they are in a DC's district."""
    from src.services import nudge_messages, reply_language
    from src.services import onboarding_bot as bot
    if db is None or offered(conv) or point != plan(db)["point"]:
        return False
    dc = dc_of(db, conv)
    if not dc:
        return False
    lang, latin = reply_language.last_reply(db, conv)
    msg = bot._say(db, conv, nudge_messages.text(PURPOSE, nudge_messages.variant_for(lang, latin)))
    if isinstance(msg.payload, dict) or msg.payload is None:
        msg.payload = {**(msg.payload or {}), "bot": PURPOSE}
        flag_modified(msg, "payload")
    _mark(conv, point, dc)
    return True


def queue_quiet(db: Session, now: Optional[datetime] = None) -> int:
    """
    Someone in a DC's district who stopped part-way: once the bot's usual reminder has gone
    unanswered for AFTER_NUDGE, the next reminder is this offer (a template once their 24-hour
    window has closed), in place of the next follow-up in line. Returns how many were queued.
    """
    from src.models.inbox import FollowUp, WhatsAppConversation
    from src.services import applications, dispositions as dz, followups, inbox
    now = now or _now()
    from src.services import dc_network
    if not dc_network.load(db) or plan(db)["point"] != "after_nudge":
        return 0
    n = 0
    for conv in db.query(WhatsAppConversation).filter(WhatsAppConversation.bot_step.isnot(None)).all():
        data = conv.bot_data or {}
        if offered(conv) or conv.documents_submitted_at or not applications.is_application(conv):
            continue
        nudged = _iso(data.get("nudged_at"))
        last_in = inbox.aware(conv.last_inbound_at)
        # The bot's reminder went, and they have not written since.
        if not nudged or (last_in and last_in >= nudged) or now - nudged < AFTER_NUDGE:
            continue
        dc = dc_of(db, conv)
        if not dc:
            continue
        # In place of the next follow-up reminder in line.
        nxt = (db.query(FollowUp).filter(FollowUp.phone == conv.phone, FollowUp.status.in_(followups.PENDING),
                                         FollowUp.wants == dz.NUDGE, FollowUp.purpose != PURPOSE)
               .order_by(FollowUp.due_at).first())
        if nxt is not None:
            nxt.status, nxt.note, nxt.done_at = "cancelled", "Replaced by the District Coordinator visit offer", now
        db.add(FollowUp(followup_id=uuid.uuid4().hex, phone=conv.phone, disposition=conv.disposition or "int_in_bot_flow",
                        purpose=PURPOSE, owner=dz.BOT, wants=dz.NUDGE, due_at=now, status="scheduled", attempt=1,
                        expects_reply=True, cancel_on_reply=False, created_by="dc_visit", created_at=now))
        _mark(conv, "after_nudge", dc)
        n += 1
    if n:
        db.commit()
    return n


def _iso(v):
    try:
        d = datetime.fromisoformat(v) if v else None
    except ValueError:
        return None
    return d.replace(tzinfo=timezone.utc) if d and d.tzinfo is None else d


def answer(db: Session, conv, said: str) -> bool:
    """Their reply to the offer: a yes is "Wants a DC visit" (Biswajit Sir is told). True when handled."""
    from src.services import handover, nudge_messages, reply_language
    from src.services import onboarding_bot as bot
    held = (conv.bot_data or {}).get("dc_offer") or {}
    at = held.get("at")
    if not at or held.get("answer") or not said:
        return False
    try:
        when = datetime.fromisoformat(at)
    except ValueError:
        return False
    if _now() - when > ANSWER_WITHIN:
        return False
    if _NO.search(said) and not re.search(r"\b(no problem|koi baat nahi)\b", said, re.I):
        held = {**held, "answer": "no", "answered_at": _now().isoformat()}
        conv.bot_data = {**conv.bot_data, "dc_offer": held}
        flag_modified(conv, "bot_data")
        return False          # the flow carries on as it was
    if not _YES.search(said):
        return False
    held = {**held, "answer": "yes", "answered_at": _now().isoformat()}
    conv.bot_data = {**conv.bot_data, "dc_offer": held}
    flag_modified(conv, "bot_data")
    district = held.get("district") or ""
    handover.record(db, conv, "int_dc_visit", "bot",
                    note=f"Said yes to a visit by the District Coordinator ({held.get('dc') or 'DC'}, {district}).")
    lang, latin = reply_language.last_reply(db, conv)
    variant = nudge_messages.variant_for(lang, latin)
    bot._say(db, conv, THANKS.get(variant) or THANKS.get(lang) or THANKS["en"])
    return True


# --- Claude CLI plans where the offer goes ---------------------------------------------

def plan_pending(db: Session) -> List[dict]:
    """A planning task for Claude CLI when there are DCs and no recent plan of Claude's."""
    from src.services import dc_network
    if not dc_network.load(db):
        return []
    p = plan(db)
    if p.get("by") == "Claude CLI" and p.get("at"):
        try:
            if _now() - datetime.fromisoformat(p["at"]) < REPLAN_EVERY:
                return []
        except ValueError:
            pass
    return [{"id": f"dcplan:{_now().strftime('%Y%m%d')}", "prompt": _plan_prompt(db)}]


def _plan_prompt(db: Session) -> str:
    from collections import Counter
    from src.models.inbox import WhatsAppConversation
    from src.services import applications
    from src.services import onboarding_bot as bot
    convs = [c for c in db.query(WhatsAppConversation).filter(WhatsAppConversation.bot_step.isnot(None)).all()
             if applications.is_application(c)]
    steps = Counter(bot.STEP_LABELS.get(c.bot_step, c.bot_step) for c in convs)
    trust = sum(1 for c in convs if c.disposition == "int_trust")
    cannot = sum(1 for c in convs if (c.bot_data or {}).get("can_invest") is False)
    docs_no = sum(1 for c in convs if (c.bot_data or {}).get("has_documents") is False)
    lines = "\n".join(f"- {k}: {n}" for k, n in steps.most_common())
    options = "\n".join(f"- {k}: {v}" for k, v in POINTS.items())
    return f"""Eko's WhatsApp bot will offer a face-to-face visit by our District Coordinator (DC) to people in districts where we have a DC, to build trust before they apply to become a Kiosk Operator (SBI Customer Service Point or ESAF banking agent). It is offered once per person. Choose the ONE point in the chat where the offer will help most.

Where our {len(convs)} applicants are now (bot step: people):
{lines}
People who doubted Eko is genuine: {trust}. People who said they cannot invest ₹3–5 lakh: {cannot}. People who said their documents are not ready: {docs_no}.

The points you can choose:
{options}

Reply with ONLY a JSON object: {{"point": one of {list(POINTS)}, "why": "one short English line"}}"""


def plan_ingest(db: Session, claude_output: str) -> dict:
    from src.services import claude_answers
    try:
        got = claude_answers._parse(claude_output)
    except Exception:
        return {"done": False, "why": "Claude's reply was not readable"}
    point = str(got.get("point") or "").strip()
    if point not in POINTS:
        return {"done": False, "why": f"unknown point {point!r}"}
    first = plan(db).get("by") != "Claude CLI"
    saved = save_plan(db, point, str(got.get("why") or ""), "Claude CLI")
    if first:
        # The offer's templates go to Meta, so it can reach people after 24 hours (the user, 19 Nov 2026).
        try:
            from src.services import nudge_templates
            nudge_templates.submit(db, PURPOSE, "Claude CLI")
        except Exception:
            pass
    return {"done": True, **saved}
