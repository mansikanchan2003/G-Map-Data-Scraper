"""
Finishes Studio drafts that are waiting for a photo.

The free FLUX allowance is a few images a day, so a round often writes its
copy and then finds no image model will take the request. Those drafts wait
as PHOTO_PENDING with a time to try again (see template_studio._park_for_photo).
This loop checks every few minutes and finishes them one at a time, oldest
first, so nobody has to come back and press "Retry photo".

It is a daemon thread in the backend process, like the scraping autopilot,
and relies on there being one backend process.
"""
import logging
import threading
from datetime import datetime, timezone
from typing import Optional

from src.models.whatsapp import WhatsAppTemplate
from src.services import template_studio as studio

logger = logging.getLogger("gmap_scraper.photo_queue")

CHECK_EVERY_SECONDS = 300


def _due(t: WhatsAppTemplate, now: datetime) -> bool:
    at = (t.generation or {}).get("photo_retry_at")
    if not at:
        return True
    when = datetime.fromisoformat(at)
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    return when <= now


def _claim(db, template_id: str) -> bool:
    """Takes a waiting draft for this process, unless something else just did."""
    taken = (
        db.query(WhatsAppTemplate)
        .filter(WhatsAppTemplate.template_id == template_id, WhatsAppTemplate.status == studio.PHOTO_PENDING)
        .update({WhatsAppTemplate.status: studio.GENERATING}, synchronize_session=False)
    )
    db.commit()
    return taken == 1


def tick(db, now: Optional[datetime] = None) -> int:
    """Finishes the drafts that are due, oldest first. Returns how many were tried."""
    now = now or datetime.now(timezone.utc)
    waiting = (
        db.query(WhatsAppTemplate)
        .filter(WhatsAppTemplate.status == studio.PHOTO_PENDING)
        .order_by(WhatsAppTemplate.created_at)
        .all()
    )
    tried = 0
    for t in [t for t in waiting if _due(t, now)]:
        if not _claim(db, t.template_id):
            continue
        tried += 1
        studio.run_new_photo(t.template_id, fresh=False)
        db.expire_all()
        if db.get(WhatsAppTemplate, t.template_id).status == studio.PHOTO_PENDING:
            # Still no allowance; the rest would only spend requests finding that out.
            break
    return tried


def recover_after_restart(db) -> int:
    """
    Settles Studio drafts left GENERATING by a restart, whose background task
    died with the process; otherwise they would show a spinner for ever.

    - copy written, no poster yet: queued for its photo;
    - already has a poster (a "New photo" was under way): back to review;
    - no copy yet: failed, saying why, since the writing cannot be resumed.
    """
    n = 0
    for t in db.query(WhatsAppTemplate).filter(WhatsAppTemplate.status == studio.GENERATING,
                                               WhatsAppTemplate.origin == "agent"):
        gen = dict(t.generation or {})
        if t.header_content:
            t.status = studio.AWAITING_APPROVAL
        elif gen.get("poster") and gen.get("photo_scene"):
            gen.pop("photo_retry_at", None)
            t.status = studio.PHOTO_PENDING
        else:
            gen["error"] = "Interrupted by a server restart before the text was written. Generate again."
            t.status = studio.GENERATION_FAILED
        t.generation = gen
        n += 1
    db.commit()
    return n


_thread: Optional[threading.Thread] = None
_stop = threading.Event()


def _loop() -> None:
    from src.database import SessionLocal

    db = SessionLocal()
    try:
        recovered = recover_after_restart(db)
        if recovered:
            logger.info(f"photo_queue event=RECOVERED drafts={recovered}")
    except Exception:
        db.rollback()
        logger.exception("photo_queue event=RECOVERY_FAILED")
    finally:
        db.close()

    while not _stop.is_set():
        db = SessionLocal()
        try:
            tick(db)
        except Exception:
            db.rollback()
            logger.exception("photo_queue event=TICK_FAILED")
        finally:
            db.close()
        _stop.wait(CHECK_EVERY_SECONDS)


def start() -> None:
    global _thread
    if _thread and _thread.is_alive():
        return
    _stop.clear()
    _thread = threading.Thread(target=_loop, name="studio-photo-queue", daemon=True)
    _thread.start()
    logger.info("photo_queue event=THREAD_STARTED")


def stop() -> None:
    _stop.set()
