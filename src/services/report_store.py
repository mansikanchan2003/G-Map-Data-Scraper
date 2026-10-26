"""
AutoGMap's calculated views written into tables, so every number the screens
show is in the database for SQL (the user, 2026-10-22: "all the data of
AUTOGMAP should be stored in the DB"). Each table is a copy of what its
screen works out from the records; the records stay the source.

- action_items: the action items queue (followups.queue), replaced whole.
- disposition_mix: leads by disposition per campaign, template and state
  (lead_journey.disposition_mix), replaced whole.
- lead_alerts: the Dashboard alerts (journey_checks.find), replaced whole.
- disposition_daily: today's (IST) count of chats at each disposition.
- number_usage_daily: the shared number's use per day (number_usage.report).
- goal_daily: today's lead goal and progress (growth_plan.goal).

The per-day tables keep each day's last figures, so the history builds up.
Refreshed with the lead journeys (lead_journey_store), every 15 minutes.
Each table is written on its own: one failing leaves the others.
"""
import hashlib
import logging
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from typing import Callable, Dict, Optional

from sqlalchemy.orm import Session

from src.models.reports import ActionItem, DispositionDaily, DispositionMix, GoalDaily, LeadAlert, NumberUsageDaily
from src.services import dispositions as dz, inbox

logger = logging.getLogger("gmap_scraper.report_store")

IST = timezone(timedelta(hours=5, minutes=30))
# The number usage screen goes back up to 90 days; each refresh rewrites those days.
USAGE_DAYS = 90


def _id(*parts) -> str:
    return hashlib.sha1("|".join(str(p) for p in parts).encode()).hexdigest()


def _dt(iso: Optional[str]) -> Optional[datetime]:
    return datetime.fromisoformat(iso) if iso else None


def _cut(text, n: int):
    return text[:n] if isinstance(text, str) else text


def _today() -> date:
    return inbox.now().astimezone(IST).date()


def store_action_items(db: Session, now: datetime) -> int:
    from src.services import followups

    q = followups.queue(db)
    db.query(ActionItem).delete(synchronize_session=False)
    n = 0
    for b in followups.BUCKETS:
        for i in q[b]:
            db.add(ActionItem(item_id=_cut(i["id"], 64), source=i["source"], phone=i["phone"], name=_cut(i["name"], 200),
                              owner=i["owner"], owner_label=_cut(i["owner_label"], 300), text=_cut(i["text"], 500),
                              result=_cut(i["result"], 300), disposition_label=_cut(i["disposition_label"], 120),
                              due_at=_dt(i["due_at"]), bucket=b, refreshed_at=now))
            n += 1
    return n


def store_disposition_mix(db: Session, now: datetime) -> int:
    from src.services import lead_journey

    mix = lead_journey.disposition_mix(db)
    db.query(DispositionMix).delete(synchronize_session=False)
    n = 0
    for dim, rows in mix.items():
        for r in rows:
            for d in r["dispositions"]:
                db.add(DispositionMix(row_id=_id(dim, r["value"], d["label"], d["group"]), dimension=dim,
                                      value=_cut(r["value"], 255), disposition_label=_cut(d["label"], 120),
                                      group=d["group"], leads=d["count"], sent=r["sent"], replied=r["replied"],
                                      refreshed_at=now))
                n += 1
    return n


def store_lead_alerts(db: Session, now: datetime) -> int:
    from src.services import journey_checks

    found = journey_checks.find(db, groups=journey_checks.ALL_GROUPS, limit=None)
    db.query(LeadAlert).delete(synchronize_session=False)
    seen = set()
    for f in found["flags"]:
        key = _id(f["check"], f["phone"], f["at"], f["detail"])
        if key in seen:
            continue
        seen.add(key)
        db.add(LeadAlert(alert_id=key, check=f["check"], label=_cut(f["label"], 200), severity=f["severity"],
                         group=f["group"], phone=f["phone"], name=_cut(f["name"], 200), at=_dt(f["at"]),
                         detail=_cut(f["detail"], 500), refreshed_at=now))
    return len(seen)


def store_disposition_daily(db: Session, now: datetime) -> int:
    from src.models.inbox import WhatsAppConversation
    from src.services.handover import current

    counts = Counter(current(c)["key"] for c in db.query(WhatsAppConversation).all())
    day = _today()
    db.query(DispositionDaily).filter(DispositionDaily.day == day).delete(synchronize_session=False)
    for key, n in counts.items():
        cat = dz.category_of(key)
        db.add(DispositionDaily(day=day, disposition=_cut(key or "none", 60), disposition_label=_cut(dz.label(key), 120),
                                category=cat.key if cat else None, group=dz.group(key), chats=n, refreshed_at=now))
    return len(counts)


def store_number_usage(db: Session, now: datetime) -> int:
    from src.services import number_usage

    days = number_usage.report(db, USAGE_DAYS)["days"]
    for d in days:
        row = db.get(NumberUsageDaily, date.fromisoformat(d["day"])) or NumberUsageDaily(day=date.fromisoformat(d["day"]))
        row.autogmap, row.others = d["autogmap"], d["others"]
        row.others_by_category = d["others_by_category"]
        row.others_delivered, row.others_read = d["others_delivered"], d["others_read"]
        row.others_cost_inr, row.refreshed_at = d["others_cost_inr"], now
        db.merge(row)
    return len(days)


def store_goal(db: Session, now: datetime) -> int:
    from src.services import growth_plan

    g = growth_plan.goal(db)
    day = _today()
    row = db.get(GoalDaily, day) or GoalDaily(day=day)
    row.target, row.leads, row.still_needed = g.get("target"), g.get("leads"), g.get("still_needed")
    row.days_left, row.on_track = g.get("days_left"), g.get("on_track")
    row.messages_sent, row.leads_per_1000 = g.get("messages_sent"), g.get("leads_per_1000")
    # Totals only: the lead list (names and phones) is in the chats already.
    row.details = {k: v for k, v in g.items() if k != "lead_list"}
    row.refreshed_at = now
    db.merge(row)
    return 1


def settle_agent_runs(db: Session, now: datetime) -> int:
    from src.services import agent_telemetry
    return agent_telemetry.settle(db, now)


STORES: Dict[str, Callable[[Session, datetime], int]] = {
    # Not a copy: the bot's agent runs are judged once their window has passed.
    "agent_runs": settle_agent_runs,
    "action_items": store_action_items,
    "disposition_mix": store_disposition_mix,
    "lead_alerts": store_lead_alerts,
    "disposition_daily": store_disposition_daily,
    "number_usage_daily": store_number_usage,
    "goal_daily": store_goal,
}


def refresh(db: Session) -> Dict[str, Optional[int]]:
    """Write every table. Returns the rows written for each, None where it failed."""
    now = inbox.now()
    out: Dict[str, Optional[int]] = {}
    for table, store in STORES.items():
        try:
            out[table] = store(db, now)
            db.commit()
        except Exception:
            db.rollback()
            out[table] = None
            logger.exception(f"report_store event=STORE_FAILED table={table}")
    logger.info("report_store event=REFRESHED " + " ".join(f"{k}={v}" for k, v in out.items()))
    return out
