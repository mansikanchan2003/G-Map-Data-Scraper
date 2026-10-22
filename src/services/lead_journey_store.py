"""
Every lead's journey kept in the database (lead_journeys, lead_journey_steps),
so the team can query it with SQL (the user, 2026-10-21).

The journey itself is read from the chats (lead_journey.py); this writes what
it reads into the two tables. A lead's steps are replaced as a whole on each
refresh: they are a copy, and the chats stay the record. Refreshed every
SYNC_EVERY by the follow-up thread, and once when the backend starts.
"""
import hashlib
import logging
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from src.models.inbox import LeadJourney, LeadJourneyStep
from src.services import inbox, lead_journey

logger = logging.getLogger("gmap_scraper.lead_journey_store")

SYNC_EVERY = timedelta(minutes=15)
_last_sync: Optional[datetime] = None


def _dt(iso: Optional[str]) -> Optional[datetime]:
    return datetime.fromisoformat(iso) if iso else None


def _cut(text: Optional[str], n: int) -> Optional[str]:
    return text[:n] if isinstance(text, str) else text


def _store(db: Session, j: dict, now: datetime) -> None:
    phone = j["phone"]
    stages = {f["key"]: _dt(f["at"]) for f in j["funnel"]}
    row = db.get(LeadJourney, phone) or LeadJourney(phone=phone)
    row.name = j["name"]
    row.outcome = j["outcome"]
    row.furthest_index = j["furthest"]
    row.furthest_stage = lead_journey.FUNNEL[j["furthest"]] if j["furthest"] >= 0 else None
    row.disposition, row.disposition_label = j["now"]["key"], _cut(j["now"]["label"], 120)
    for stage in lead_journey.FUNNEL:
        setattr(row, f"{stage}_at", stages.get(stage))
    row.last_step = _cut(j["last"]["what"], 300) if j["last"] else None
    row.last_activity_at = _dt(j["last_activity"])
    row.steps_count = len(j["steps"])
    row.updated_at = now
    db.merge(row)

    db.query(LeadJourneyStep).filter(LeadJourneyStep.phone == phone).delete(synchronize_session=False)
    for i, s in enumerate(j["steps"]):
        sid = hashlib.sha1(f"{phone}|{i}|{s['key']}|{s['at']}".encode()).hexdigest()
        db.add(LeadJourneyStep(step_id=sid, phone=phone, seq=i, kind=s["kind"], key=_cut(s["key"], 60),
                               at=_dt(s["at"]), what=_cut(s["what"], 500), action=_cut(s["action"], 500),
                               action_at=_dt(s["action_at"]), by=_cut(s["by"], 200), tone=s["tone"],
                               detail=_cut(s["detail"], 500)))


def sync_all(db: Session) -> int:
    """Write every lead's journey into the tables. Returns how many leads."""
    global _last_sync
    now = inbox.now()
    rows = lead_journey.board(db, limit=100000)
    stored = 0
    from src.models.inbox import WhatsAppConversation
    for r in rows:
        conv = db.query(WhatsAppConversation).filter(WhatsAppConversation.phone == r["phone"]).first()
        if conv is None:
            continue
        _store(db, lead_journey.build(db, conv), now)
        stored += 1
    db.commit()
    _last_sync = now
    logger.info(f"lead_journey_store event=SYNCED leads={stored}")
    return stored


def sync_if_due(db: Session) -> Optional[int]:
    if _last_sync and inbox.now() - _last_sync < SYNC_EVERY:
        return None
    stored = sync_all(db)
    # The other calculated views go into their tables on the same beat (report_store.py).
    from src.services import report_store
    report_store.refresh(db)
    return stored
