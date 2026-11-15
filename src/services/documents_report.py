"""
The email the team gets when someone submits their documents (15 Nov 2026):
who they are, what they uploaded, whether their PIN is within our SBI branch
area (and if not, how far our nearest branch is), and what to do next. It goes
to the admin and NOTIFY_ALSO (Kavya), so the next step is not left to one
inbox. Identity documents stay in AutoGMap, never attached.
"""
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from src.models.inbox import OnboardingDocument, WhatsAppConversation, WhatsAppMessage
from src.services import applications, inbox, pincode_coverage
from src.services import onboarding_bot as bot
from src.services.geo_validator import haversine_distance

EDUCATION = {"12": "12th / Diploma", "grad": "Graduate / Post-graduate", "other": "Below 12th"}


def recipients() -> str:
    """The admin and NOTIFY_ALSO (Kavya), as one To line: the team that makes the call."""
    from src.services import auth_service, notifier
    return notifier.team(auth_service.BOOTSTRAP_ADMIN)


def nearest_branch(db: Session, coords: Optional[List[float]]) -> Optional[Dict]:
    """Our SBI branch nearest these coordinates, however far: name, code, PIN and km."""
    branches = applications._branches(db)
    if not coords or not branches:
        return None
    km, b = min(((haversine_distance(coords[0], coords[1], *x["coords"]), x) for x in branches), key=lambda p: p[0])
    return {"name": (b["branch_name"] or "").title(), "code": b["branch_code"], "pincode": b["pincode"],
            "km": round(km, 1)}


def build(db: Session, conv: WhatsAppConversation) -> Dict:
    data = conv.bot_data or {}
    cov = data.get("coverage") or {}
    pin = cov.get("pincode") or (data.get("typed_pin") or {}).get("pincode")
    coords = cov.get("coords") or (applications._pin_coords(db, pin) if pin else None)
    near = nearest_branch(db, coords)
    radius = pincode_coverage.RADIUS_KM
    q = applications.qualify(conv)
    esaf = bot.is_esaf(conv)
    keys = [d.doc_type for d in db.query(OnboardingDocument).filter(OnboardingDocument.phone == conv.phone)]
    labels = [bot.DOCUMENT_LABELS.get(k, k) for k in keys]
    chat_files = (db.query(WhatsAppMessage)
                  .filter(WhatsAppMessage.phone == conv.phone, WhatsAppMessage.direction == "IN",
                          WhatsAppMessage.kind.in_(("image", "document"))).count())
    invest = data.get("can_invest")
    # Aadhaar fetched from DigiLocker (or, before 30 Oct 2026, verified there) vs only a file.
    dl = data.get("digilocker") or {}
    if "aadhaar_digilocker" in keys or "aadhaar" in (dl.get("got") or {}) or dl.get("verified"):
        aadhaar = "Verified through DigiLocker"
    elif "aadhaar" in keys:
        aadhaar = "Not verified through DigiLocker (uploaded as a file)"
    else:
        aadhaar = "Not given yet"
    in_area = near is not None and near["km"] <= radius if cov.get("served") is None else bool(cov.get("served"))

    steps: List[str] = []
    keen = (f"They are keen: {len(keys)} documents on the upload form"
            + (f" and {chat_files} files in the chat" if chat_files else "") + ".")
    if data.get("education") == "other":
        steps.append("Below 12th: not eligible for SBI or ESAF. Thank them and close politely.")
    elif esaf:
        steps += ["ESAF Small Finance Bank: call them to take the ₹1,999 registration "
                  "(and ₹1,300 + GST if they want a Micro ATM device).",
                  "Arrange Aceware's shop verification and the agent agreement on ₹100 stamp paper."]
    elif not in_area:
        where = f"PIN {pin}" + (f" ({cov.get('place')})" if cov.get("place") else "")
        if near:
            steps.append(f"Not qualified for our SBI branch codes: {where} is {near['km']:g} km from our nearest "
                         f"branch, {near['name']} (code {near['code']}, PIN {near['pincode']}); our SBI area is "
                         f"within {radius:g} km of a branch.")
        else:
            steps.append(f"Not qualified for our SBI branch codes: {where} could not be placed near any branch of ours.")
        steps.append("Call them and pitch ESAF Small Finance Bank's banking agent: no big investment, only the "
                     "₹1,999 registration. " + keen)
    elif invest is False:
        steps.append("Cannot invest ₹3–5 lakh for SBI: call them and pitch ESAF Small Finance Bank's banking agent "
                     "(no big investment, ₹1,999 registration). " + keen)
    elif q["strongly_qualified"]:
        branch = f"{near['name']} (code {near['code']}), {near['km']:g} km away" if near else "our SBI branch"
        steps += [f"Strongly qualified for SBI: {branch}.",
                  "Hand over to Eko Acquisition: assign a DC and schedule the visit."]
    else:
        steps.append("Check the documents in the Inbox and call them to finish what is missing.")

    return {
        "name": conv.profile_name, "phone": conv.phone, "pincode": pin, "place": cov.get("place"),
        "education": EDUCATION.get(data.get("education"), "Not answered"),
        "investment": "ESAF (no big investment)" if esaf else
                      {True: "Can invest ₹3–5 lakh", False: "Cannot invest ₹3–5 lakh"}.get(invest, "Not answered"),
        "applied_for": "ESAF banking agent" if esaf else "SBI Customer Service Point",
        "verdict": q["verdict"], "aadhaar": aadhaar, "nearest": near, "radius_km": radius, "in_area": in_area,
        "documents": labels, "chat_files": chat_files, "steps": steps,
        "submitted_at": inbox.aware(conv.documents_submitted_at),
    }


def email(report: Dict, app_url: str) -> tuple:
    """(subject, body) of the email, in plain text."""
    who = report["name"] or report["phone"]
    digits = (report["phone"] or "").lstrip("+")
    near = report["nearest"]
    when = report["submitted_at"].astimezone(bot.IST).strftime("%d %b %Y, %I:%M %p") if report["submitted_at"] else ""
    lines = [f"{who} has completed the journey and uploaded their documents" + (f" ({when} IST)." if when else "."),
             "", "APPLICANT",
             f"  Name          {report['name'] or '-'}",
             f"  Phone         {report['phone']}",
             f"  Applied for   {report['applied_for']}",
             f"  Education     {report['education']}",
             f"  Investment    {report['investment']}",
             f"  PIN code      {report['pincode'] or '-'}" + (f" ({report['place']})" if report["place"] else ""),
             f"  Aadhaar       {report['aadhaar']}",
             f"  Verdict       {report['verdict']}"]
    if near:
        lines += ["", "NEAREST SBI BRANCH OF OURS",
                  f"  {near['name']}, code {near['code']}, PIN {near['pincode']}: {near['km']:g} km away "
                  f"({'within' if report['in_area'] else 'outside'} our {report['radius_km']:g} km area)"]
    lines += ["", f"DOCUMENTS ({len(report['documents'])} on the upload form"
              + (f", {report['chat_files']} files in the chat" if report["chat_files"] else "") + ")"]
    lines += [f"  - {d}" for d in report["documents"]] or ["  (none)"]
    lines += ["", "NEXT STEPS"] + [f"  {i}. {s}" for i, s in enumerate(report["steps"], start=1)]
    lines += ["", f"Open in AutoGMap: {app_url.rstrip('/')}/#inbox/{digits}",
              f"WhatsApp: https://wa.me/{digits}",
              "", "The documents are in AutoGMap's Inbox; they are not attached to this email."]
    tag = "ESAF" if report["applied_for"].startswith("ESAF") else ("Qualified" if report["in_area"] else "Not in our SBI area")
    return f"AutoGMap: {who} submitted documents · {tag}", "\n".join(lines) + "\n"


def send(conv_phone: str, app_url: str, session_factory=None) -> bool:
    """Build and email the report to the admin and Kavya; runs in the background."""
    from src.database import SessionLocal
    from src.services import notifier
    db = (session_factory or SessionLocal)()
    try:
        conv = db.get(WhatsAppConversation, conv_phone)
        if conv is None:
            return False
        subject, body = email(build(db, conv), app_url)
        return notifier._send(recipients(), subject, body)
    finally:
        db.close()
