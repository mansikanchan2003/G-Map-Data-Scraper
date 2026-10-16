"""
Handing a chat between the bot and a person, and recording how it ended.

Agent to Human: a person takes a chat over by pressing "Take over" or simply
by replying in the inbox. The bot then stays quiet in that chat, and the
inbox shows who is handling it and since when.

Human to Agent: "Hand back to the bot" lets the bot carry on. The person
records the chat's disposition as they hand it back, any open ticket is
solved, and the bot asks again, in the person's language and with its
buttons, the question it was waiting on, so the applicant carries on where
they left off.

A disposition is the chat's outcome: Interested, Call back later, Not
reachable and so on. Every chat always has one: the one the team last
recorded, or, when the bot has moved the chat on since, the one its step
says (documents submitted, not eligible, outside our area...). Each one
recorded is kept in chat_activity with who and when, for the Dispositions tab.
"""
import uuid
from collections import Counter
from datetime import timedelta
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from src.models.inbox import ChatActivity, WhatsAppConversation
from src.services import inbox, tickets
from src.services import onboarding_bot as bot

# Key: (label, group). Groups order the Dispositions tab and colour it.
DISPOSITIONS: Dict[str, tuple] = {
    "interested": ("Interested", "positive"),
    "docs_pending": ("Documents pending", "positive"),
    "submitted": ("Documents submitted", "positive"),
    "guidance": ("Wants personal guidance", "positive"),
    "call_back": ("Call back later", "follow_up"),
    "not_reachable": ("Not reachable", "follow_up"),
    "query_answered": ("Question answered", "follow_up"),
    "enquiry": ("Enquiry, not from a campaign", "follow_up"),
    "existing_csp": ("Existing CSP (support)", "other"),
    "not_interested": ("Not interested", "negative"),
    "cannot_invest": ("Cannot invest", "negative"),
    "not_eligible": ("Not eligible", "negative"),
    "outside_area": ("Outside our area", "negative"),
    "wrong_number": ("Wrong number", "negative"),
    "other": ("Other", "other"),
}

# The outcome the bot's own step stands for.
_FROM_STEP = {
    bot.SUBMITTED: "submitted",
    bot.AWAIT_UPLOAD: "docs_pending",
    bot.AWAIT_DOCS: "docs_pending",
    bot.NOT_ELIGIBLE: "not_eligible",
    bot.NOT_SERVED: "outside_area",
    bot.NOT_INVESTING: "cannot_invest",
    bot.AWAIT_WEBINAR: "guidance",
    bot.AWAIT_AVAILABILITY: "guidance",
    bot.WEBINAR_CONFIRMED: "guidance",
    bot.WEBINAR_AVAILABILITY: "guidance",
    bot.HANDOVER: "call_back",
}


def label(key: Optional[str]) -> Optional[str]:
    return DISPOSITIONS[key][0] if key in DISPOSITIONS else None


def options() -> List[dict]:
    return [{"key": k, "label": v[0], "group": v[1]} for k, v in DISPOSITIONS.items()]


def bot_disposition(conv: WhatsAppConversation) -> str:
    """What the chat's state says, without the team: from the bot's step, or an enquiry."""
    if conv.documents_submitted_at:
        return "submitted"
    if conv.bot_step in _FROM_STEP:
        return _FROM_STEP[conv.bot_step]
    if conv.bot_step:
        return "interested"
    return "enquiry"


def current(conv: WhatsAppConversation) -> dict:
    """
    The chat's disposition now: the team's, unless the bot has moved the chat
    on since it was recorded (or the documents came in), then the bot's.
    """
    team_at = inbox.aware(conv.disposition_at)
    moved = max(filter(None, [inbox.aware(conv.bot_updated_at), inbox.aware(conv.documents_submitted_at)]), default=None)
    if conv.disposition and team_at and not (moved and moved > team_at):
        return {"key": conv.disposition, "label": label(conv.disposition), "note": conv.disposition_note,
                "by": conv.disposition_by, "at": team_at.isoformat(), "source": "team"}
    key = bot_disposition(conv)
    return {"key": key, "label": label(key), "note": None, "by": "bot",
            "at": (moved or inbox.aware(conv.last_message_at) or inbox.aware(conv.created_at) or inbox.now()).isoformat(),
            "source": "bot"}


def _log(db: Session, conv: WhatsAppConversation, kind: str, by: str, value: str = None, note: str = None) -> ChatActivity:
    row = ChatActivity(activity_id=uuid.uuid4().hex, phone=conv.phone, kind=kind, value=value,
                       note=(note or "").strip()[:500] or None, by=by, at=inbox.now())
    db.add(row)
    return row


def record(db: Session, conv: WhatsAppConversation, key: str, by: str, note: Optional[str] = None) -> dict:
    """Record the chat's disposition."""
    if key not in DISPOSITIONS:
        raise ValueError(f"Unknown disposition: {key}")
    conv.disposition, conv.disposition_by, conv.disposition_at = key, by, inbox.now()
    conv.disposition_note = (note or "").strip()[:500] or None
    _log(db, conv, "disposition", by, key, note)
    return current(conv)


def take_over(db: Session, conv: WhatsAppConversation, by: str) -> None:
    """Agent to Human: the bot stops answering here and the chat shows who is handling it."""
    if conv.bot_paused and conv.handled_by == by:
        return
    conv.bot_paused = True
    conv.handled_by, conv.handled_since = by, inbox.now()
    _log(db, conv, "to_person", by)


def hand_back(db: Session, conv: WhatsAppConversation, by: str, disposition: Optional[str] = None,
              note: Optional[str] = None, resume: bool = True) -> Optional[str]:
    """
    Human to Agent: the bot carries on. Records the disposition, solves an open
    ticket, and asks again the question the bot was waiting on. Returns what
    the bot sent, or None when there was nothing to ask or the window is shut.
    """
    if disposition:
        record(db, conv, disposition, by, note)
    conv.bot_paused = False
    conv.handled_by = conv.handled_since = None
    _log(db, conv, "to_bot", by, disposition, note if not disposition else None)
    if conv.needs_attention:
        conv.needs_attention = False
        conv.attention_resolved_by, conv.attention_resolved_at = by, inbox.now()
        tickets.resolve(db, conv.phone, by)
    if not resume or not inbox.window_open(conv):
        return None
    asked = bot.pending_question(db, conv)
    if not asked:
        return None
    question, opts = asked
    body = f"{bot._t(db, conv, 'resume')}\n\n{question}"
    inbox.send(db, conv.phone, body, sent_by="bot", **opts)
    return body


def activity(db: Session, phone: str) -> List[dict]:
    rows = db.query(ChatActivity).filter(ChatActivity.phone == phone).order_by(ChatActivity.at).all()
    return [as_dict(r) for r in rows]


def as_dict(r: ChatActivity) -> dict:
    return {"kind": r.kind, "value": r.value, "label": label(r.value), "note": r.note, "by": r.by,
            "at": inbox.aware(r.at).isoformat() if r.at else None}


def who(email: Optional[str]) -> str:
    """kavya.shukla@eko.co.in -> Kavya Shukla."""
    if not email or "@" not in email:
        return email or "the team"
    return email.split("@")[0].replace(".", " ").replace("_", " ").title()


def dashboard(db: Session, days: int = 7) -> dict:
    """Every chat's disposition now, the team's recent ones, and who is handling what."""
    convs = db.query(WhatsAppConversation).all()
    now = [current(c) for c in convs]
    by_key = Counter(d["key"] for d in now)
    since = inbox.now() - timedelta(days=days)
    recent = (db.query(ChatActivity, WhatsAppConversation)
              .join(WhatsAppConversation, WhatsAppConversation.phone == ChatActivity.phone)
              .filter(ChatActivity.kind == "disposition", ChatActivity.at >= since)
              .order_by(ChatActivity.at.desc()).all())
    team_counts = Counter(a.value for a, _ in recent)
    handled = [c for c in convs if c.bot_paused and c.handled_by]
    return {
        "total": len(convs),
        "by_team": sum(d["source"] == "team" for d in now),
        "groups": [{"key": k, "label": v[0], "group": v[1], "count": by_key.get(k, 0)}
                   for k, v in DISPOSITIONS.items()],
        "recent_days": days,
        "recent_count": len(recent),
        "recent_by_disposition": [{"key": k, "label": label(k), "count": n} for k, n in team_counts.most_common()],
        "recent": [{"phone": c.phone, "name": c.profile_name, "key": a.value, "label": label(a.value), "note": a.note,
                    "by": a.by, "at": inbox.aware(a.at).isoformat()} for a, c in recent[:25]],
        "with_people": [{"phone": c.phone, "name": c.profile_name, "by": c.handled_by,
                         "since": inbox.aware(c.handled_since).isoformat() if c.handled_since else None}
                        for c in sorted(handled, key=lambda c: inbox.aware(c.handled_since) or inbox.now())],
    }
