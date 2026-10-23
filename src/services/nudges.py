"""
Gentle reminders for people who stopped answering the bot part-way.

Someone may tap Interested, answer a question or two and then get called
away. An hour after the bot's last unanswered question (the user's choice,
2026-10-14) they get one short, kind message, in their language, that says
it understands they were busy and asks the same question again, with its
buttons, so they can carry on with a tap.

One reminder per pause: when they reply and later go quiet again, the next
one is due an hour after that. Never while the conversation is waiting for
a person (attention needed or the bot paused), never to people no AutoGMap
campaign reached, and never once Meta's 24-hour window is closing, since a
free-form message cannot be sent after it.

A daemon thread in the backend process, like the photo queue; it relies on
there being one backend process.
"""
import logging
import threading
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy.orm import Session

from src.models.inbox import WhatsAppConversation, WhatsAppMessage
from src.services import inbox
from src.services import onboarding_bot as bot

logger = logging.getLogger("gmap_scraper.nudges")

AFTER = timedelta(hours=1)
# Left before the 24-hour window closes, so the reminder is still accepted.
WINDOW_MARGIN = timedelta(minutes=10)
CHECK_EVERY_SECONDS = 300


def _last_message(db: Session, phone: str) -> Optional[WhatsAppMessage]:
    return (db.query(WhatsAppMessage).filter(WhatsAppMessage.phone == phone)
            .order_by(WhatsAppMessage.created_at.desc()).first())


def due(db: Session, conv: WhatsAppConversation, now: datetime) -> bool:
    """Whether this conversation should get its reminder now."""
    if conv.bot_step not in bot.NUDGE_STEPS or conv.bot_paused or conv.needs_attention:
        return False
    last_in = inbox.aware(conv.last_inbound_at)
    if not last_in or now >= last_in + inbox.REPLY_WINDOW - WINDOW_MARGIN:
        return False
    # Their last reply said where they stand ("busy, call at 5", "not interested"): that
    # disposition's own follow-ups take it from here, not the bot's question again.
    from src.services import dispositions as dz
    told = inbox.aware(conv.disposition_at)
    if conv.disposition and told and told >= last_in and dz.group(conv.disposition) != "positive":
        return False
    last = _last_message(db, conv.phone)
    # The bot spoke last and nobody has answered for an hour.
    if not last or last.direction != "OUT" or last.sent_by != "bot":
        return False
    # One per pause: if the bot's last word is already the reminder, wait for
    # them. Recognised by the message itself rather than by times, which Meta
    # gives only to the second.
    if last.message_id == (conv.bot_data or {}).get("nudge_message_id"):
        return False
    return now - inbox.aware(last.created_at) >= AFTER


def nudge(db: Session, conv: WhatsAppConversation, now: datetime) -> bool:
    asked = bot.pending_question(db, conv)
    if not asked:
        return False
    question, options = asked
    body = f"{bot._t(db, conv, 'nudge')}\n\n{question}"
    msg = inbox.send(db, conv.phone, body, sent_by="bot", **options)
    data = dict(conv.bot_data or {})
    data["nudged_at"] = now.isoformat()
    data["nudge_message_id"] = msg.message_id
    data["nudges"] = data.get("nudges", 0) + 1
    conv.bot_data = data
    logger.info(f"nudges event=NUDGED phone=...{conv.phone[-4:]} step={conv.bot_step} status={msg.status}")
    return True


def tick(db: Session, now: Optional[datetime] = None) -> int:
    """Send every reminder that is due. Returns how many were sent."""
    now = now or datetime.now(timezone.utc)
    if not bot.get_settings(db)["enabled"]:
        return 0
    sent = 0
    candidates = (db.query(WhatsAppConversation)
                  .filter(WhatsAppConversation.bot_step.in_(bot.NUDGE_STEPS)).all())
    for conv in candidates:
        try:
            if due(db, conv, now) and inbox.from_campaign(db, conv.phone) and nudge(db, conv, now):
                sent += 1
            db.commit()
        except Exception:
            db.rollback()
            logger.exception(f"nudges event=NUDGE_FAILED phone=...{conv.phone[-4:]}")
    return sent


_thread: Optional[threading.Thread] = None
_stop = threading.Event()


def _loop() -> None:
    from src.database import SessionLocal

    while not _stop.is_set():
        db = SessionLocal()
        try:
            tick(db)
        except Exception:
            db.rollback()
            logger.exception("nudges event=TICK_FAILED")
        finally:
            db.close()
        _stop.wait(CHECK_EVERY_SECONDS)


def start() -> None:
    global _thread
    if _thread and _thread.is_alive():
        return
    _stop.clear()
    _thread = threading.Thread(target=_loop, name="bot-nudges", daemon=True)
    _thread.start()
    logger.info("nudges event=THREAD_STARTED")


def stop() -> None:
    _stop.set()
