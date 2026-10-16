"""
Tickets for conversations left for a person.

A ticket is raised when a conversation is marked as needing attention (by
the bot, or by someone in the team) and solved when someone presses
"Question resolved". There is at most one open ticket per conversation: a
further question while it is open becomes its latest question, so one
person waiting is one ticket. Every ticket is kept, for the history.

A question the bot can answer from what it knows (Eko's FAQ, kiosk.eko.in)
is a ticket too, raised and solved at once by the bot, with its answer: the
bot tries first, and only what it cannot answer goes to a person.
"""
from datetime import timedelta
from typing import List, Optional

from sqlalchemy.orm import Session

from src.models.inbox import AttentionTicket, WhatsAppConversation
from src.services import inbox

# Solved tickets are announced across the app for this long.
ANNOUNCE_RESOLVED_FOR = timedelta(hours=2)


def open_ticket(db: Session, phone: str) -> Optional[AttentionTicket]:
    return (db.query(AttentionTicket)
            .filter(AttentionTicket.phone == phone, AttentionTicket.resolved_at.is_(None))
            .order_by(AttentionTicket.raised_at.desc()).first())


def raise_or_update(db: Session, conv: WhatsAppConversation, via: str = "bot") -> AttentionTicket:
    """The open ticket for this conversation, raised now if there was none."""
    question = (conv.attention_reason or "").strip()[:500] or None
    ticket = open_ticket(db, conv.phone)
    if ticket is None:
        ticket = AttentionTicket(phone=conv.phone, raised_by_name=conv.profile_name, question=question,
                                 latest_question=question, questions_count=1, raised_via=via,
                                 raised_at=inbox.now())
        db.add(ticket)
    elif question and question != ticket.latest_question:
        ticket.latest_question = question
        ticket.questions_count = (ticket.questions_count or 1) + 1
    db.flush()
    return ticket


def answered_by_bot(db: Session, conv: WhatsAppConversation, question: str, answer: str) -> AttentionTicket:
    """A question the bot answered itself: a ticket raised and solved by the bot, with its answer."""
    now = inbox.now()
    question = (question or "").strip()[:500] or None
    ticket = AttentionTicket(phone=conv.phone, raised_by_name=conv.profile_name, question=question,
                             latest_question=question, questions_count=1, raised_via="bot", raised_at=now,
                             resolved_at=now, resolved_by="bot", bot_answer=answer)
    db.add(ticket)
    db.flush()
    return ticket


def resolve(db: Session, phone: str, by: str) -> Optional[AttentionTicket]:
    """Solve the conversation's open ticket, if it has one."""
    ticket = open_ticket(db, phone)
    if ticket is not None:
        ticket.resolved_at = inbox.now()
        ticket.resolved_by = by
        db.flush()
    return ticket


def as_dict(t: AttentionTicket) -> dict:
    return {
        "ticket_id": t.ticket_id,
        "phone": t.phone,
        "raised_by": t.raised_by_name,
        "question": t.question,
        "latest_question": t.latest_question if t.latest_question != t.question else None,
        "questions_count": t.questions_count or 1,
        "raised_via": t.raised_via,
        "status": t.status,
        "raised_at": inbox.aware(t.raised_at).isoformat() if t.raised_at else None,
        "resolved_at": inbox.aware(t.resolved_at).isoformat() if t.resolved_at else None,
        "resolved_by": t.resolved_by,
        "resolved_by_bot": t.resolved_by == "bot",
        "bot_answer": t.bot_answer,
    }


def history(db: Session, status: Optional[str] = None, limit: int = 500) -> List[dict]:
    """Tickets newest first; status "open" or "resolved" narrows them."""
    q = db.query(AttentionTicket)
    if status == "open":
        q = q.filter(AttentionTicket.resolved_at.is_(None))
    elif status == "resolved":
        q = q.filter(AttentionTicket.resolved_at.isnot(None))
    order = AttentionTicket.resolved_at.desc() if status == "resolved" else AttentionTicket.raised_at.desc()
    return [as_dict(t) for t in q.order_by(order).limit(limit).all()]


def recently_resolved(db: Session) -> List[dict]:
    since = inbox.now() - ANNOUNCE_RESOLVED_FOR
    # Not the bot's own answers: nobody was waiting on those, so nothing to announce.
    rows = (db.query(AttentionTicket).filter(AttentionTicket.resolved_at >= since,
                                             AttentionTicket.resolved_by != "bot")
            .order_by(AttentionTicket.resolved_at.desc()).limit(20).all())
    return [as_dict(t) for t in rows]
