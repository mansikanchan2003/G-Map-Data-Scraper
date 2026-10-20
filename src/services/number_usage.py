"""
What our WhatsApp number is used for, by AutoGMap and by the other apps on it.

The number (+91 99118 44469) is shared: TARA, EPS nudges and the Eko
Customer Support Agent send from it too, and Meta sends every app on the
number the delivery updates for every message. Updates for messages that
are not AutoGMap's (no campaign recipient, no inbox message with that id)
are kept in number_activity, one row per message, with only the last four
digits of the recipient. Which app sent one is not in the update; the time,
the category and whether it was charged are.
"""
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional

from sqlalchemy.orm import Session

from src.models.inbox import WhatsAppMessage
from src.models.whatsapp import NumberActivity, WhatsAppCampaignRecipient
from src.services import inbox, pricing

IST = timezone(timedelta(hours=5, minutes=30))
_STAGE_FIELD = {"SENT": "sent_at", "DELIVERED": "delivered_at", "READ": "read_at", "FAILED": "failed_at"}


def _at(raw) -> datetime:
    try:
        return datetime.fromtimestamp(int(raw), tz=timezone.utc)
    except (TypeError, ValueError):
        return datetime.now(timezone.utc)


def record(db: Session, status: dict) -> None:
    """Note a delivery update for a message another app sent from the number."""
    msg_id, stage = status.get("id"), (status.get("status") or "").upper()
    if not msg_id or stage not in _STAGE_FIELD:
        return
    row = db.get(NumberActivity, msg_id)
    if row is None:
        row = NumberActivity(message_id=msg_id, first_seen_at=inbox.now())
        db.add(row)
        # So a second update for it in the same delivery finds it.
        db.flush()
    at = _at(status.get("timestamp"))
    field = _STAGE_FIELD[stage]
    if getattr(row, field) is None:
        setattr(row, field, at)
    # A delivered or read message was sent, whichever update came first.
    if row.sent_at is None and stage in ("DELIVERED", "READ"):
        row.sent_at = at
    pricing_ = status.get("pricing") or {}
    if pricing_.get("category"):
        row.category = str(pricing_["category"]).lower()[:30]
    if "billable" in pricing_:
        row.billable = bool(pricing_["billable"])
    origin = ((status.get("conversation") or {}).get("origin") or {}).get("type")
    if origin:
        row.origin = str(origin)[:40]
    recipient = "".join(ch for ch in str(status.get("recipient_id") or "") if ch.isdigit())
    if recipient:
        row.recipient_last4 = recipient[-4:]
    errors = status.get("errors") or []
    if errors:
        row.error_code = str(errors[0].get("code"))[:20]


def _day(at: Optional[datetime]) -> Optional[str]:
    at = inbox.aware(at)
    return at.astimezone(IST).strftime("%Y-%m-%d") if at else None


def report(db: Session, days: int = 7) -> Dict:
    """Per day (IST): what AutoGMap sent, what the other apps sent, and roughly what the others cost."""
    since = inbox.now() - timedelta(days=days)
    ours_ids = set()
    per_day: Dict[str, Dict] = defaultdict(lambda: {"autogmap": 0, "others": 0, "others_by_category": defaultdict(int),
                                                    "others_delivered": 0, "others_read": 0, "others_cost_inr": 0.0})
    for msg_id, at in (db.query(WhatsAppCampaignRecipient.provider_message_id, WhatsAppCampaignRecipient.sent_at)
                       .filter(WhatsAppCampaignRecipient.sent_at >= since)):
        per_day[_day(at)]["autogmap"] += 1
    for (at,) in db.query(WhatsAppMessage.created_at).filter(WhatsAppMessage.direction == "OUT",
                                                             WhatsAppMessage.created_at >= since):
        per_day[_day(at)]["autogmap"] += 1
    rows = db.query(NumberActivity).filter(NumberActivity.first_seen_at >= since).all()
    if rows:
        # A campaign send whose id was saved only after its first update came in is AutoGMap's after all.
        ids = [r.message_id for r in rows]
        ours_ids = {i for (i,) in db.query(WhatsAppCampaignRecipient.provider_message_id)
                    .filter(WhatsAppCampaignRecipient.provider_message_id.in_(ids))}
        ours_ids |= {i for (i,) in db.query(WhatsAppMessage.provider_message_id)
                     .filter(WhatsAppMessage.provider_message_id.in_(ids))}
    last_other = None
    for r in rows:
        if r.message_id in ours_ids:
            continue
        at = r.sent_at or r.delivered_at or r.first_seen_at
        d = per_day[_day(at)]
        d["others"] += 1
        d["others_by_category"][r.category or "unknown"] += 1
        d["others_delivered"] += bool(r.delivered_at)
        d["others_read"] += bool(r.read_at)
        if r.billable:
            d["others_cost_inr"] += float(pricing.rate_for(r.category))
        if last_other is None or inbox.aware(at) > last_other:
            last_other = inbox.aware(at)
    out = []
    for day in sorted(k for k in per_day if k):
        d = per_day[day]
        out.append({"day": day, "autogmap": d["autogmap"], "others": d["others"],
                    "others_by_category": dict(d["others_by_category"]), "others_delivered": d["others_delivered"],
                    "others_read": d["others_read"], "others_cost_inr": round(d["others_cost_inr"], 2)})
    return {
        "days": out,
        "since": since.isoformat(),
        "others_total": sum(x["others"] for x in out),
        "others_cost_inr": round(sum(x["others_cost_inr"] for x in out), 2),
        "autogmap_total": sum(x["autogmap"] for x in out),
        "last_other_message_at": last_other.isoformat() if last_other else None,
        "note": "Messages other apps on the number sent, counted from Meta's delivery updates since this was "
                "switched on. Which app sent each is not in the update. Cost is before GST, at Meta's rate per category.",
    }
