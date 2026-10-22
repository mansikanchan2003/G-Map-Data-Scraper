"""
Leads whose recorded steps do not add up: a step with no record of the one
that must come before it (the user, 2026-10-22). Shown on the Dashboard, so
a broken record (a status update that never came, a send that was not
recorded, a question the bot skipped) is seen rather than quietly skewing
the counts.

Each check names the step that is there and the one that is missing:

- tapped a button / clicked the link / replied, but no sent message;
- delivered or read, but not sent;
- read, but not delivered (Meta's delivered update did not arrive);
- documents in, but the qualifying answers (PIN, education, ₹5 lakh) missing;
- the upload link sent without "can invest" recorded;
- an education answer with no PIN code before it;
- documents in since the hand-over began, but nothing queued for Eko Acquisition.

Nothing is changed; this only reads.
"""
from collections import Counter, defaultdict
from datetime import datetime, timezone
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from src.models.inbox import FollowUp, WhatsAppConversation, WhatsAppMessage
from src.models.whatsapp import (
    HUMAN_LINK_CLICK, WhatsAppButtonClick, WhatsAppCampaignRecipient, WhatsAppLinkClick,
)
from src.services import dispositions as dz, inbox

# The hand-over to Eko Acquisition began here; documents before it were never meant to be queued.
HANDOVER_SINCE = datetime(2026, 10, 22, tzinfo=timezone.utc)

CHECKS = {
    "tapped_not_sent": ("Tapped a button, but no sent message", "high"),
    "clicked_not_sent": ("Clicked the link, but no sent message", "high"),
    "replied_not_sent": ("Replied to a campaign, but no sent message", "high"),
    "delivered_not_sent": ("Delivered or read, but not sent", "high"),
    "read_not_delivered": ("Read, but no delivered update", "low"),
    "docs_without_answers": ("Documents in, but qualifying answers missing", "high"),
    "link_without_invest": ("Upload link sent, but “can invest” not recorded", "medium"),
    "education_without_pin": ("Answered education, but no PIN code before it", "medium"),
    "handover_not_queued": ("Documents in, but not queued for Eko Acquisition", "high"),
}


def _iso(dt) -> Optional[str]:
    dt = inbox.aware(dt)
    return dt.isoformat() if dt else None


def find(db: Session) -> Dict:
    """Every lead with a missing step, worst first, and how many of each."""
    flags: List[dict] = []

    def flag(check: str, phone: str, at, detail: str, name: Optional[str] = None):
        label, severity = CHECKS[check]
        flags.append({"check": check, "label": label, "severity": severity, "phone": phone, "name": name,
                      "at": _iso(at), "detail": detail})

    recipients = db.query(WhatsAppCampaignRecipient).all()
    by_id = {r.recipient_id: r for r in recipients}
    sent_phones = {r.phone for r in recipients if r.sent_at}
    names = {c.phone: c.profile_name for c in db.query(WhatsAppConversation.phone, WhatsAppConversation.profile_name)}

    # Campaign side: what Meta and the person did with each message.
    for r in recipients:
        nm = r.name or names.get(r.phone)
        if not r.sent_at and (r.delivered_at or r.read_at):
            flag("delivered_not_sent", r.phone, r.delivered_at or r.read_at,
                 f"Status {r.status}; Meta reported it {'read' if r.read_at else 'delivered'}, but no send time", nm)
        if r.read_at and not r.delivered_at and r.sent_at:
            flag("read_not_delivered", r.phone, r.read_at, "Read update arrived; the delivered one never did", nm)
    for rid, at in db.query(WhatsAppButtonClick.recipient_id, WhatsAppButtonClick.clicked_at).all():
        r = by_id.get(rid)
        if r is not None and not r.sent_at:
            flag("tapped_not_sent", r.phone, at, f"Recipient status {r.status}", r.name or names.get(r.phone))
    for rid, at in db.query(WhatsAppLinkClick.recipient_id, WhatsAppLinkClick.clicked_at).filter(HUMAN_LINK_CLICK).all():
        r = by_id.get(rid)
        if r is not None and not r.sent_at:
            flag("clicked_not_sent", r.phone, at, f"Recipient status {r.status}", r.name or names.get(r.phone))

    # Someone a campaign was meant for wrote back, yet no message to them was ever sent.
    unsent = {r.phone for r in recipients} - sent_phones
    if unsent:
        first_in = {}
        for phone, at in (db.query(WhatsAppMessage.phone, WhatsAppMessage.created_at)
                          .filter(WhatsAppMessage.direction == "IN", WhatsAppMessage.phone.in_(unsent)).all()):
            if phone not in first_in or inbox.aware(at) < inbox.aware(first_in[phone]):
                first_in[phone] = at
        for phone, at in first_in.items():
            flag("replied_not_sent", phone, at, "Their reply is in the inbox; the campaign row has no send time",
                 names.get(phone))

    # The bot's side: the questions must come in order.
    queued = {p for (p,) in db.query(FollowUp.phone).filter(FollowUp.wants == dz.API).distinct()}
    for c in db.query(WhatsAppConversation).all():
        data = c.bot_data or {}
        pin = (data.get("coverage") or {}).get("pincode")
        if c.documents_submitted_at:
            missing = [w for w, ok in (("PIN code", pin), ("education", data.get("education")),
                                       ("can invest", data.get("can_invest") is True)) if not ok]
            if missing:
                flag("docs_without_answers", c.phone, c.documents_submitted_at, "Missing: " + ", ".join(missing),
                     c.profile_name)
            if inbox.aware(c.documents_submitted_at) >= HANDOVER_SINCE and c.phone not in queued:
                flag("handover_not_queued", c.phone, c.documents_submitted_at,
                     "No hand-over row in follow_ups", c.profile_name)
        elif c.upload_token and data.get("can_invest") is not True:
            flag("link_without_invest", c.phone, c.bot_updated_at, f"Bot step {c.bot_step}", c.profile_name)
        if data.get("education") and not pin:
            flag("education_without_pin", c.phone, c.bot_updated_at, f"Education {data.get('education')}", c.profile_name)

    rank = {"high": 0, "medium": 1, "low": 2}
    flags.sort(key=lambda f: (rank[f["severity"]], f["at"] or ""), reverse=False)
    counts = Counter(f["check"] for f in flags)
    leads = defaultdict(list)
    for f in flags:
        leads[f["phone"]].append(f["check"])
    return {
        "total": len(flags),
        "leads": len(leads),
        "by_check": [{"check": k, "label": CHECKS[k][0], "severity": CHECKS[k][1], "count": counts.get(k, 0)}
                     for k in CHECKS if counts.get(k)],
        "flags": flags[:300],
    }
