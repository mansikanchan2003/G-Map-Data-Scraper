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

The dispositions themselves, and what each one sets in motion, are the
team's sheet (dispositions.py); recording one plans its follow-ups
(followups.py).
"""
import uuid
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from src.models.inbox import ChatActivity, WhatsAppConversation
from src.services import dispositions as dz, inbox, tickets
from src.services import onboarding_bot as bot

# Key: (label, group), every sub-category of the sheet. Groups colour them.
DISPOSITIONS: Dict[str, tuple] = {k: (v.label, dz.CATEGORY[v.category].group) for k, v in dz.SUBS.items()}

# The outcome the bot's own step stands for.
_FROM_STEP = {
    bot.SUBMITTED: "int_visit",
    bot.AWAIT_UPLOAD: "int_docs_pending",
    bot.AWAIT_DOCS: "int_docs_pending",
    bot.NOT_ELIGIBLE: "rej_eligibility",
    bot.NOT_SERVED: "int_not_sbi",
    bot.NOT_INVESTING: "ni_investment",
    bot.GUIDANCE_QA: "int_more_info",
    bot.AWAIT_WEBINAR: "int_more_info",
    bot.AWAIT_AVAILABILITY: "int_more_info",
    bot.WEBINAR_CONFIRMED: "int_more_info",
    bot.WEBINAR_AVAILABILITY: "int_more_info",
    bot.HANDOVER: "busy_later",
}


def label(key: Optional[str]) -> Optional[str]:
    return dz.label(key)


def options() -> List[dict]:
    return dz.options()


def bot_disposition(conv: WhatsAppConversation) -> str:
    """What the chat's state says, without the team: from the bot's step, or an enquiry."""
    if conv.documents_submitted_at:
        # Documents in: AutoGMap's part is done and Eko Acquisition takes over.
        return "int_visit"
    if conv.bot_step in _FROM_STEP:
        return _FROM_STEP[conv.bot_step]
    if conv.bot_step and ((conv.bot_data or {}).get("coverage") or {}).get("served") is False:
        return "int_not_sbi"
    if conv.bot_step:
        return "int_in_bot_flow"
    return "enquiry"


def current(conv: WhatsAppConversation) -> dict:
    """
    The chat's disposition now: the team's, unless the bot has moved the chat
    on since it was recorded (or the documents came in), then the bot's.
    """
    team_at = inbox.aware(conv.disposition_at)
    moved = max(filter(None, [inbox.aware(conv.bot_updated_at), inbox.aware(conv.documents_submitted_at)]), default=None)
    if conv.disposition and team_at and not (moved and moved > team_at):
        key = dz.normalise(conv.disposition)
        return {"key": key, "label": label(key), "category": dz.category_of(key).key if dz.category_of(key) else None,
                "note": conv.disposition_note,
                "by": conv.disposition_by, "at": team_at.isoformat(), "source": "team"}
    key = bot_disposition(conv)
    return {"key": key, "label": label(key), "category": dz.category_of(key).key, "note": None, "by": "bot",
            "at": (moved or inbox.aware(conv.last_message_at) or inbox.aware(conv.created_at) or inbox.now()).isoformat(),
            "source": "bot"}


def _log(db: Session, conv: WhatsAppConversation, kind: str, by: str, value: str = None, note: str = None) -> ChatActivity:
    row = ChatActivity(activity_id=uuid.uuid4().hex, phone=conv.phone, kind=kind, value=value,
                       note=(note or "").strip()[:500] or None, by=by, at=inbox.now())
    db.add(row)
    return row


def record(db: Session, conv: WhatsAppConversation, key: str, by: str, note: Optional[str] = None,
           at: Optional[datetime] = None, attempt: int = 1, run_now: bool = True, ticket: bool = True,
           tell: bool = True) -> dict:
    """
    Record the chat's disposition and plan what it calls for. `at` is the
    time to call back or the date to follow up on, for those that ask.
    `tell=False` when the team has already been told (the bot's own
    escalation email), so they are not emailed twice.
    """
    from src.services import followups

    key = dz.normalise(key)
    if key not in DISPOSITIONS:
        raise ValueError(f"Unknown disposition: {key}")
    conv.disposition, conv.disposition_by, conv.disposition_at = key, by, inbox.now()
    conv.disposition_note = (note or "").strip()[:500] or None
    _log(db, conv, "disposition", by, key, note)
    followups.plan(db, conv, key, by, at=at, attempt=attempt, run_now=run_now, note=note, ticket=ticket, tell=tell)
    return current(conv)


def take_over(db: Session, conv: WhatsAppConversation, by: str) -> None:
    """Agent to Human: the bot stops answering here and the chat shows who is handling it."""
    if conv.bot_paused and conv.handled_by == by:
        return
    conv.bot_paused = True
    conv.handled_by, conv.handled_since = by, inbox.now()
    _log(db, conv, "to_person", by)


def hand_back(db: Session, conv: WhatsAppConversation, by: str, disposition: Optional[str] = None,
              note: Optional[str] = None, resume: bool = True, at: Optional[datetime] = None) -> Optional[str]:
    """
    Human to Agent: the bot carries on. Records the disposition, solves an open
    ticket, and asks again the question the bot was waiting on. Returns what
    the bot sent, or None when there was nothing to ask or the window is shut.
    """
    if disposition:
        # The bot carrying on asks its question; a nudge due now would be a second message.
        carries_on = resume and inbox.window_open(conv) and bot.pending_question(db, conv) is not None
        # The person handing back is the one handling it: the team is emailed, no new ticket opens.
        record(db, conv, disposition, by, note, at=at, run_now=not carries_on, ticket=False)
        if carries_on:
            _bot_carries_on(db, conv)
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


def _bot_carries_on(db: Session, conv: WhatsAppConversation) -> None:
    """The bot asks its own question instead of a nudge due now: one message, not two."""
    from src.models.inbox import FollowUp

    for f in db.query(FollowUp).filter(FollowUp.phone == conv.phone, FollowUp.status.in_(("scheduled", "waiting")),
                                       FollowUp.wants != dz.TASK, FollowUp.due_at <= inbox.now()).all():
        f.status, f.note, f.done_at = "cancelled", "The bot carried on with the chat instead", inbox.now()


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
    team_counts = Counter(dz.normalise(a.value) for a, _ in recent)
    handled = [c for c in convs if c.bot_paused and c.handled_by]
    # Outcomes the team recorded each day (IST), every day of the range shown, and by whom.
    ist = timezone(timedelta(hours=5, minutes=30))
    per_day = Counter(inbox.aware(a.at).astimezone(ist).date().isoformat() for a, _ in recent)
    today = inbox.now().astimezone(ist).date()
    groups_now = Counter(DISPOSITIONS[d["key"]][1] for d in now if d["key"] in DISPOSITIONS)
    return {
        "group_totals": {g: groups_now.get(g, 0) for g in ("positive", "follow_up", "negative", "other")},
        "by_day": [{"date": (today - timedelta(days=i)).isoformat(),
                    "count": per_day.get((today - timedelta(days=i)).isoformat(), 0)} for i in range(days - 1, -1, -1)],
        "by_person": [{"by": who_, "count": n} for who_, n in Counter(a.by for a, _ in recent).most_common()],
        "total": len(convs),
        "by_team": sum(d["source"] == "team" for d in now),
        "groups": [{"key": k, "label": v[0], "group": v[1], "count": by_key.get(k, 0)}
                   for k, v in DISPOSITIONS.items()],
        # The sheet's eleven categories (and Other), each with its sub-categories.
        "categories": [{"key": c.key, "label": c.label, "group": c.group, "icon": c.icon,
                        "count": sum(by_key.get(s.key, 0) for s in c.subs),
                        "subs": [{"key": s.key, "label": s.label, "count": by_key.get(s.key, 0), "action": s.action,
                                  "owner": s.owner} for s in c.subs]} for c in dz.CATEGORIES],
        # Documents uploaded, or marked Physical visit required: over to Eko Acquisition.
        "handed_over": sum(1 for c, d in zip(convs, now) if d["key"] == "int_visit"),
        "recent_days": days,
        "recent_count": len(recent),
        "recent_by_disposition": [{"key": k, "label": label(k), "count": n} for k, n in team_counts.most_common()],
        "recent": [{"phone": c.phone, "name": c.profile_name, "key": dz.normalise(a.value), "label": label(a.value), "note": a.note,
                    "by": a.by, "at": inbox.aware(a.at).isoformat()} for a, c in recent[:25]],
        "with_people": [{"phone": c.phone, "name": c.profile_name, "by": c.handled_by,
                         "since": inbox.aware(c.handled_since).isoformat() if c.handled_since else None}
                        for c in sorted(handled, key=lambda c: inbox.aware(c.handled_since) or inbox.now())],
    }
