"""
Handing a lead to Eko Acquisition, the project that takes over once
AutoGMap's part is done: documents uploaded, "Physical visit required:
assign to DC, schedule visit, DC will give report to Eko" (the user,
2026-10-21). It goes to their API (the user's choice).

Their API is not known yet: until EKO_ACQUISITION_API_URL (and
EKO_ACQUISITION_API_KEY, sent as a Bearer token) are set, a lead waits,
marked "not set up yet", and goes once they are. The lead is POSTed as JSON
(`payload`), one request per lead; the field names are ours and are to be
agreed with that team: change them here, in one place.

Identity documents are not sent: their Drive links are, so access stays with
Drive's own sharing.
"""
import logging
import os
from typing import Optional, Tuple

from sqlalchemy.orm import Session

from src.models.inbox import OnboardingDocument, WhatsAppConversation
from src.services import dispositions as dz, inbox

logger = logging.getLogger("gmap_scraper.acquisition_handover")

TIMEOUT_SECONDS = 20


def configured() -> bool:
    return bool(os.environ.get("EKO_ACQUISITION_API_URL"))


def payload(db: Session, conv: WhatsAppConversation) -> dict:
    """Everything Eko Acquisition needs to take the lead over."""
    from src.models.application import QualifiedLead
    from src.services import lead_journey, onboarding_bot as bot

    data = conv.bot_data or {}
    cov = data.get("coverage") or {}
    q = db.get(QualifiedLead, conv.phone)
    docs = db.query(OnboardingDocument).filter(OnboardingDocument.phone == conv.phone).all()
    labels = {d["key"]: d["label"] for d in bot.DOCUMENTS}
    journey = lead_journey.build(db, conv)
    visit = dz.SUBS["int_visit"]
    return {
        "source": "AutoGMap",
        "lead_id": conv.phone.lstrip("+"),
        "name": conv.profile_name,
        "phone": conv.phone,
        "language": data.get("lang"),
        "location": {"pincode": cov.get("pincode") or (q.pincode if q else None),
                     "district": cov.get("district") or (q.district if q else None),
                     "state": cov.get("state") or (q.state if q else None),
                     "tehsil": q.tehsil if q else None},
        "education": data.get("education"),
        "can_invest": data.get("can_invest"),
        "qualification": q.level if q else None,
        "nearest_sbi_branch": {"code": q.branch_code, "name": q.branch_name, "ao": q.branch_ao,
                               "distance_km": q.branch_distance_km} if q and q.branch_code else None,
        "documents_submitted_at": inbox.aware(conv.documents_submitted_at).isoformat() if conv.documents_submitted_at else None,
        "documents": [{"type": d.doc_type, "label": labels.get(d.doc_type, d.doc_type), "drive_url": d.drive_url}
                      for d in docs],
        "requested_action": visit.action,
        "journey": [{"stage": s["key"], "what": s["what"], "at": s["at"], "our_action": s["action"],
                     "action_at": s["action_at"]} for s in journey["steps"] if s["kind"] == "stage"],
        "whatsapp": f"https://wa.me/{conv.phone.lstrip('+')}",
    }


def send(db: Session, conv: WhatsAppConversation) -> Tuple[bool, bool, Optional[str]]:
    """
    Send the lead. Returns (sent, waiting, why not): waiting when the API is
    not set up yet or did not answer, so it is tried again.
    """
    if not configured():
        return False, True, "Eko Acquisition's API is not set up yet (its address and key are needed)"
    import requests

    url = os.environ["EKO_ACQUISITION_API_URL"]
    headers = {"Content-Type": "application/json"}
    key = os.environ.get("EKO_ACQUISITION_API_KEY")
    if key:
        headers["Authorization"] = f"Bearer {key}"
    try:
        r = requests.post(url, json=payload(db, conv), headers=headers, timeout=TIMEOUT_SECONDS)
    except Exception as e:
        logger.warning(f"acquisition_handover event=SEND_FAILED phone=...{conv.phone[-4:]} error={e}")
        return False, True, f"Eko Acquisition's API did not answer: {str(e)[:200]}"
    if 200 <= r.status_code < 300:
        logger.info(f"acquisition_handover event=SENT phone=...{conv.phone[-4:]} status={r.status_code}")
        return True, False, None
    # A refusal of the lead itself (4xx) will not change by retrying; a server error may.
    waiting = r.status_code >= 500 or r.status_code == 429
    logger.warning(f"acquisition_handover event=REFUSED phone=...{conv.phone[-4:]} status={r.status_code}")
    return False, waiting, f"Eko Acquisition's API answered {r.status_code}: {r.text[:200]}"
