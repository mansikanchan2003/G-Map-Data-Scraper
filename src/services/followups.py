"""
Carrying out what each disposition calls for (dispositions.py): the
contacts, at the right time, and the tasks for the team and the District
Coordinator.

Recording a disposition plans its steps: a nudge now, a callback at the time
asked, a check-in on the follow-up date, a visit task for the DC. A new
disposition replaces the bot's pending contacts; one that closes the lead
(wrong number, duplicate, not interested) cancels everything.

Every few minutes `tick`:
- sends what is due, by the channel it wants or a nudge (contact_channels);
- cancels a pending contact made unnecessary by the person replying;
- for a contact that expected an answer: a reply marks it answered; none in
  a day records RNR and tries again the next day, as the sheet says for
  calls; a message WhatsApp could not deliver records Unreachable and tries
  again the next day. After MAX_ATTEMPTS it stops and leaves it to the team.

Times are India's: "this evening" is 6 PM IST, "tomorrow" 11 AM IST.
"""
import logging
import threading
import uuid
from datetime import date, datetime, time, timedelta, timezone
from typing import List, Optional

from sqlalchemy.orm import Session

from src.models.inbox import ChatActivity, FollowUp, WhatsAppConversation, WhatsAppMessage
from src.services import contact_channels, dispositions as dz, inbox

logger = logging.getLogger("gmap_scraper.followups")

IST = timezone(timedelta(hours=5, minutes=30))
MORNING, EVENING = time(11, 0), time(18, 0)
NO_ANSWER_AFTER = timedelta(hours=24)
MAX_ATTEMPTS = 3
HOLD_DEFAULT = timedelta(days=30)
CHECK_EVERY_SECONDS = 300

PENDING = ("scheduled", "waiting")


def _at(day: date, t: time) -> datetime:
    return datetime.combine(day, t, tzinfo=IST).astimezone(timezone.utc)


def due_time(when: str, now: datetime, at: Optional[datetime] = None) -> datetime:
    """When a step falls due, from its rule and the time or date the team set."""
    today = now.astimezone(IST).date()
    if when == dz.NOW:
        return now
    if when == dz.EOD:
        evening = _at(today, EVENING)
        return evening if now < evening - timedelta(minutes=30) else _at(today + timedelta(days=1), MORNING)
    if when == dz.NEXT_DAY:
        return _at(today + timedelta(days=1), MORNING)
    if when == dz.IN_2_DAYS:
        return _at(today + timedelta(days=2), MORNING)
    if when == dz.AT_TIME:
        return inbox.aware(at) if at else due_time(dz.EOD, now)
    if when == dz.ON_DATE:
        if at:
            day = inbox.aware(at).astimezone(IST).date()
            return _at(day, MORNING)
        return _at(today + HOLD_DEFAULT, MORNING)
    raise ValueError(f"Unknown time rule: {when}")


def _cancel(db: Session, phone: str, why: str, tasks_too: bool) -> int:
    q = db.query(FollowUp).filter(FollowUp.phone == phone, FollowUp.status.in_(PENDING))
    if not tasks_too:
        q = q.filter(FollowUp.wants != dz.TASK)
    n = 0
    for f in q.all():
        f.status, f.note, f.done_at = "cancelled", why, inbox.now()
        n += 1
    return n


def plan(db: Session, conv: WhatsAppConversation, key: str, by: str, at: Optional[datetime] = None,
         attempt: int = 1, run_now: bool = True) -> List[FollowUp]:
    """Schedule what a disposition calls for, replacing the bot's pending contacts."""
    s = dz.sub(key)
    if s is None:
        return []
    now = inbox.now()
    _cancel(db, conv.phone, f"Replaced by a new disposition: {s.label}", tasks_too=s.closes)
    if s.stage:
        data = dict(conv.bot_data or {})
        if data.get("stage") != s.stage:
            data["stage"] = s.stage
            conv.bot_data = data
            db.add(ChatActivity(activity_id=uuid.uuid4().hex, phone=conv.phone, kind="stage", value=s.stage,
                                by=by, at=now))
    made = []
    for st in s.steps:
        f = FollowUp(followup_id=uuid.uuid4().hex, phone=conv.phone, disposition=s.key, purpose=st.purpose,
                     owner=st.owner, wants=st.wants, due_at=due_time(st.when, now, at), status="scheduled",
                     attempt=attempt, expects_reply=st.expects_reply, cancel_on_reply=st.cancel_on_reply,
                     task=st.task, created_by=by, created_at=now)
        db.add(f)
        made.append(f)
    db.flush()
    if run_now:
        for f in made:
            if f.wants != dz.TASK and inbox.aware(f.due_at) <= now:
                _send(db, conv, f, now)
    return made


def _send(db: Session, conv: WhatsAppConversation, f: FollowUp, now: datetime) -> None:
    channel, skipped = contact_channels.pick(db, conv, f.wants)
    out = channel.reach(db, conv, f)
    f.channel, f.language = channel.name, out.language
    notes = list(skipped)
    if out.ok:
        f.status, f.sent_at, f.message_id = "sent", now, out.message_id
    elif out.waiting:
        f.status = "waiting"
        notes.append(out.error or "Waiting")
    else:
        f.status, f.sent_at, f.message_id = "failed", now, out.message_id
        notes.append(out.error or "Could not be sent")
    f.note = "; ".join(notes)[:500] or None
    logger.info(f"followups event=REACH phone=...{conv.phone[-4:]} purpose={f.purpose} channel={channel.name} "
                f"status={f.status}")
    if f.status == "failed":
        _retry(db, conv, f, "unr_not_reachable")


def _retry(db: Session, conv: WhatsAppConversation, f: FollowUp, key: str) -> None:
    """Record RNR or Unreachable for the bot and plan the next day's attempt, up to MAX_ATTEMPTS."""
    from src.services import handover

    if f.attempt >= MAX_ATTEMPTS:
        f.note = ((f.note + "; ") if f.note else "") + f"Stopped after {MAX_ATTEMPTS} attempts: over to the team"
        return
    handover.record(db, conv, key, "bot", note=f"After the {f.purpose.replace('_', ' ')} nudge", attempt=f.attempt + 1,
                    run_now=False)


def _replied_since(db: Session, phone: str, since: datetime) -> bool:
    # Compared here rather than in SQL: SQLite keeps times as text, without their zone.
    last = (db.query(WhatsAppMessage).filter(WhatsAppMessage.phone == phone, WhatsAppMessage.direction == "IN")
            .order_by(WhatsAppMessage.created_at.desc()).first())
    return last is not None and inbox.aware(last.created_at) > since


def tick(db: Session, now: Optional[datetime] = None) -> int:
    """Do everything due. Returns how many contacts were tried."""
    from src.services import onboarding_bot as bot

    now = now or inbox.now()
    if not bot.get_settings(db)["enabled"]:
        return 0
    convs = {}

    def conv_of(phone):
        if phone not in convs:
            convs[phone] = db.query(WhatsAppConversation).filter(WhatsAppConversation.phone == phone).first()
        return convs[phone]

    # Answered, unanswered or undelivered.
    for f in db.query(FollowUp).filter(FollowUp.status == "sent", FollowUp.expects_reply.is_(True)).all():
        conv, sent = conv_of(f.phone), inbox.aware(f.sent_at)
        if conv is None or sent is None:
            continue
        msg = db.query(WhatsAppMessage).filter(WhatsAppMessage.message_id == f.message_id).first() if f.message_id else None
        if _replied_since(db, f.phone, sent):
            f.status, f.done_at = "replied", now
        elif msg is not None and msg.status == "FAILED":
            f.status, f.done_at = "failed", now
            f.note = ((f.note + "; ") if f.note else "") + (msg.error_reason or "Not delivered")
            _retry(db, conv, f, "unr_not_reachable")
        elif now - sent >= NO_ANSWER_AFTER:
            f.status, f.done_at = "no_answer", now
            _retry(db, conv, f, "rnr_no_answer")
    db.commit()

    tried = 0
    pending = (db.query(FollowUp).filter(FollowUp.status.in_(PENDING), FollowUp.wants != dz.TASK)
               .order_by(FollowUp.due_at).all())
    for f in pending:
        conv = conv_of(f.phone)
        # Cancelled by a retry planned earlier in this pass.
        if conv is None or f.status not in PENDING:
            continue
        try:
            if f.cancel_on_reply and _replied_since(db, f.phone, inbox.aware(f.created_at)):
                f.status, f.note, f.done_at = "cancelled", "They replied before it was due", now
            elif inbox.aware(f.due_at) <= now:
                _send(db, conv, f, now)
                tried += 1
            db.commit()
        except Exception:
            db.rollback()
            logger.exception(f"followups event=SEND_FAILED phone=...{f.phone[-4:]} purpose={f.purpose}")
    return tried


def complete_task(db: Session, followup_id: str, by: str, note: Optional[str] = None) -> Optional[FollowUp]:
    """A person or the DC has done their task."""
    f = db.query(FollowUp).filter(FollowUp.followup_id == followup_id).first()
    if f is None:
        return None
    f.status, f.done_at, f.done_by = "done", inbox.now(), by
    if note:
        f.note = note.strip()[:500]
    return f


def as_dict(f: FollowUp, conv: Optional[WhatsAppConversation] = None) -> dict:
    return {"id": f.followup_id, "phone": f.phone, "name": conv.profile_name if conv else None,
            "disposition": f.disposition, "disposition_label": dz.label(f.disposition),
            "purpose": f.purpose, "owner": f.owner, "wants": f.wants, "channel": f.channel,
            "due_at": inbox.aware(f.due_at).isoformat(), "status": f.status, "attempt": f.attempt,
            "expects_reply": f.expects_reply, "task": f.task, "language": f.language, "note": f.note,
            "created_by": f.created_by,
            "sent_at": inbox.aware(f.sent_at).isoformat() if f.sent_at else None,
            "done_at": inbox.aware(f.done_at).isoformat() if f.done_at else None, "done_by": f.done_by}


def for_chat(db: Session, phone: str) -> List[dict]:
    rows = db.query(FollowUp).filter(FollowUp.phone == phone).order_by(FollowUp.due_at.desc()).limit(30).all()
    return [as_dict(f) for f in rows]


def board(db: Session, days: int = 7) -> dict:
    """The follow-ups for the Dispositions tab: what is coming, the team's tasks, and how recent ones went."""
    from collections import Counter

    since = inbox.now() - timedelta(days=days)
    rows = (db.query(FollowUp, WhatsAppConversation)
            .join(WhatsAppConversation, WhatsAppConversation.phone == FollowUp.phone)
            .filter((FollowUp.status.in_(PENDING)) | (FollowUp.created_at >= since)).all())
    coming = sorted([(f, c) for f, c in rows if f.status in PENDING and f.wants != dz.TASK],
                    key=lambda r: inbox.aware(r[0].due_at))
    tasks = sorted([(f, c) for f, c in rows if f.status in PENDING and f.wants == dz.TASK],
                   key=lambda r: inbox.aware(r[0].due_at))
    recent = sorted([(f, c) for f, c in rows if f.status not in PENDING and f.wants != dz.TASK],
                    key=lambda r: inbox.aware(r[0].sent_at or r[0].done_at or r[0].created_at), reverse=True)
    outcomes = Counter(f.status for f, _ in recent)
    return {
        "channels": contact_channels.status(),
        "counts": {"scheduled": sum(f.status == "scheduled" for f, _ in coming),
                   "waiting": sum(f.status == "waiting" for f, _ in coming),
                   "tasks": len(tasks), **{k: outcomes.get(k, 0) for k in ("sent", "replied", "no_answer", "failed", "cancelled")}},
        "coming": [as_dict(f, c) for f, c in coming[:40]],
        "tasks": [as_dict(f, c) for f, c in tasks[:40]],
        "recent": [as_dict(f, c) for f, c in recent[:40]],
    }


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
            logger.exception("followups event=TICK_FAILED")
        finally:
            db.close()
        _stop.wait(CHECK_EVERY_SECONDS)


def start() -> None:
    global _thread
    if _thread and _thread.is_alive():
        return
    _stop.clear()
    _thread = threading.Thread(target=_loop, name="follow-ups", daemon=True)
    _thread.start()
    logger.info("followups event=THREAD_STARTED")


def stop() -> None:
    _stop.set()
