"""
How interested someone is, read by rules from what they did (Mansi, 20 Nov 2026): no Claude.

It decides who still hears from us once WhatsApp's 24-hour window has closed: only "high" and
"medium" get the follow-up templates; the rest get nothing more from the bot (the 20-hour closure
has already gone), except the District Coordinator's visit offer where we have a DC.

The signals, strongest first:
  - documents uploaded, a yes to a DC visit, ESAF accepted                     -> high
  - said no (a negative disposition, ESAF declined, not eligible)              -> not_interested
  - said they can invest, or reached the documents step                        -> high
  - gave their PIN and education, or asked their own questions                 -> medium
  - cannot invest (and has not said yes to ESAF)                               -> low
  - only tapped Interested and went quiet                                      -> low
A rating Claude CLI made earlier (claude_answers.interest_of) is kept where there is one.
"""
from typing import Optional

from sqlalchemy.orm import Session

INTERESTED = ("high", "medium")

_HIGH_STEPS = ("SUBMITTED", "AWAIT_DOCS", "AWAIT_UPLOAD", "ESAF_INTERESTED", "ESAF_DETAILS",
               "AWAIT_DC_DAY", "DC_BOOKED", "WEBINAR_CONFIRMED")
_NO_STEPS = ("NOT_ELIGIBLE", "ESAF_DECLINED", "NOT_INVESTING")


def _their_messages(db: Session, phone: str) -> int:
    from src.models.inbox import WhatsAppMessage
    return db.query(WhatsAppMessage).filter(WhatsAppMessage.phone == phone, WhatsAppMessage.direction == "IN").count()


def rate(db: Session, conv) -> dict:
    """{"level", "reason", "by": "rules"} for this conversation."""
    from src.services import dispositions as dz
    data = conv.bot_data or {}
    step = conv.bot_step or ""

    def out(level, reason):
        return {"level": level, "reason": reason, "by": "rules"}

    if conv.documents_submitted_at:
        return out("high", "Uploaded their documents")
    if ((data.get("dc_offer") or {}).get("answer") == "yes") or step in ("AWAIT_DC_DAY", "DC_BOOKED"):
        return out("high", "Wants the District Coordinator's visit")
    if step in ("ESAF_INTERESTED", "ESAF_DETAILS"):
        return out("high", "Interested in ESAF's banking agent")
    if conv.disposition and dz.group(conv.disposition) == "negative":
        return out("not_interested", "Said they are not interested")
    if step in _NO_STEPS:
        return out("not_interested", {"NOT_ELIGIBLE": "Not eligible (below 12th)",
                                      "ESAF_DECLINED": "Declined ESAF too"}.get(step, "Not going ahead"))
    if data.get("can_invest") is True or step in _HIGH_STEPS:
        return out("high", "Can invest and reached the documents step")
    if data.get("can_invest") is False:
        return out("low", "Cannot invest ₹3–5 lakh")
    said = _their_messages(db, conv.phone)
    if data.get("education") or data.get("coverage"):
        return out("medium", "Gave their PIN and education")
    if said >= 3:
        return out("medium", "Wrote to us several times")
    return out("low", "Only tapped Interested, then went quiet")


def of(db: Session, conv) -> Optional[dict]:
    """Claude's earlier rating where there is one, else the rules'."""
    if conv is None:
        return None
    from src.services import claude_answers
    return claude_answers.interest_of(conv) or rate(db, conv)


def interested(db: Session, conv) -> bool:
    r = of(db, conv)
    return bool(r and r["level"] in INTERESTED)
