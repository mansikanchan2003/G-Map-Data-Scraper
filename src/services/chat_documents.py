"""
Documents people send in the chat instead of on the upload page (15 Nov 2026).

Brinda Computer sent their documents in the middle of the WhatsApp chat. Each
photo or PDF a campaign contact sends is read on our own server (Tesseract OCR;
nothing leaves it: these are identity documents) and recognised from its words:
the Aadhaar number, "Income Tax Department", "Election Commission", an IFSC, a
board's marksheet... A recognised one is filed with the person's documents under
its own name ("Aadhaar Card.jpg"), copied to their Drive folder like an upload,
and counts towards the upload page. Once every required document is in, the
person is thanked and the bot stops asking (onboarding_bot.documents_submitted),
and the admin and Kavya get the documents report. A file it cannot place is left
for a person to look at.
"""
import logging
import os
import re
import shutil
import subprocess
import tempfile
import uuid
from typing import Optional

from sqlalchemy.orm import Session

from src.models.inbox import OnboardingDocument, WhatsAppConversation, WhatsAppMessage
from src.services import onboarding_bot as bot

logger = logging.getLogger("gmap_scraper.chat_documents")

# What each recognised document is called in the person's folder and in Drive.
NAMES = {
    "aadhaar": "Aadhaar Card", "pan": "PAN Card", "voter_dl": "Voter ID or Driving Licence",
    "bank": "Bank Proof", "edu_12": "12th Certificate", "edu_higher": "Graduation Certificate",
    "edu_other": "Education Certificate", "police": "Police Verification", "cibil": "CIBIL Report",
    "photo": "Photo", "esaf_bank": "Bank Proof", "esaf_edu": "Education Certificate",
    "esaf_shop_photo": "Photo at the Shop",
}
OCR_SECONDS = 60
PAN_RE = re.compile(r"\b[A-Z]{5}[0-9]{4}[A-Z]\b")
AADHAAR_RE = re.compile(r"\b[2-9][0-9]{3}\s?[0-9]{4}\s?[0-9]{4}\b")


def _has(t: str, *words) -> bool:
    return any(w in t for w in words)


def classify(text: str, hint: str = "", is_image: bool = True) -> Optional[str]:
    """
    Which document this is, from its words (OCR text, plus the file name and the
    caption as a hint); None when it cannot tell. Most specific first: a PAN card
    also says "Govt. of India", an Aadhaar letter may carry a PAN-like code.
    """
    raw = f"{text or ''}\n{hint or ''}"
    t = raw.lower()
    if _has(t, "income tax", "permanent account number", "pan card") or PAN_RE.search(raw.upper()):
        if not _has(t, "aadhaar", "aadhar", "uidai", "unique identification", "आधार"):
            return "pan"
    if _has(t, "aadhaar", "aadhar", "uidai", "unique identification", "आधार", "enrolment no") or AADHAAR_RE.search(raw):
        return "aadhaar"
    if _has(t, "election commission", "elector", "epic no", "voter", "driving licen", "driving license",
            "transport department", "licence no", "dl no"):
        return "voter_dl"
    if _has(t, "ifsc", "passbook", "pass book", "statement of account", "account statement", "a/c no",
            "account no", "account number", "cheque", "micr"):
        return "bank"
    if _has(t, "cibil", "credit score", "transunion", "credit report", "credit information"):
        return "cibil"
    if _has(t, "police") and _has(t, "verification", "clearance", "character", "certificate", "station"):
        return "police"
    if _has(t, "university", "bachelor", "degree", "b.com", "b.a.", "b.sc", "bca", "master of", "graduat",
            "convocation"):
        return "edu_higher"
    if _has(t, "higher secondary", "senior secondary", "h.s.c", "hsc", "class xii", "class 12", "12th",
            "std 12", "std. xii", "intermediate"):
        return "edu_12"
    if _has(t, "marksheet", "mark sheet", "statement of marks", "board of", "secondary", "examination", "diploma",
            "certificate"):
        return "edu_other"
    # A photo with almost no words on it: the passport-size photo, or one at the shop.
    if is_image and len(re.sub(r"[^A-Za-z0-9]", "", text or "")) < 25:
        return "photo"
    return None


def for_conversation(conv: WhatsAppConversation, key: str) -> str:
    """The key in this person's own document list: ESAF has its own bank, education and photo rows."""
    if bot.is_esaf(conv):
        return {"bank": "esaf_bank", "edu_12": "esaf_edu", "edu_higher": "esaf_edu", "edu_other": "esaf_edu",
                "photo": "esaf_shop_photo"}.get(key, key)
    return key


def _run(args: list) -> str:
    out = subprocess.run(args, capture_output=True, timeout=OCR_SECONDS, check=False)
    return out.stdout.decode("utf-8", "ignore")


def ocr(path: str, mime: str) -> str:
    """The words in an image or a PDF's first page, read here on the server."""
    if not shutil.which("tesseract"):
        raise RuntimeError("Tesseract is not installed on this server")
    if mime == "application/pdf" or path.lower().endswith(".pdf"):
        text = _run(["pdftotext", "-l", "2", path, "-"]) if shutil.which("pdftotext") else ""
        if len(text.strip()) > 40:
            return text
        with tempfile.TemporaryDirectory() as tmp:
            _run(["pdftoppm", "-png", "-r", "200", "-f", "1", "-l", "1", path, os.path.join(tmp, "p")])
            pages = sorted(f for f in os.listdir(tmp) if f.endswith(".png"))
            return _run(["tesseract", os.path.join(tmp, pages[0]), "stdout", "-l", "eng+hin"]) if pages else ""
    return _run(["tesseract", path, "stdout", "-l", "eng+hin"])


def _file(db: Session, conv: WhatsAppConversation, key: str, src: str, mime: str) -> OnboardingDocument:
    """File it with the person's documents, under its own name; the caller commits."""
    from src.routers.onboarding import DOCS_DIR
    ext = os.path.splitext(src)[1].lstrip(".").lower() or "bin"
    folder = os.path.join(DOCS_DIR, re.sub(r"\D", "", conv.phone))
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, f"{key}-{uuid.uuid4().hex}.{ext}")
    shutil.copyfile(src, path)
    doc = OnboardingDocument(document_id=uuid.uuid4().hex, phone=conv.phone, doc_type=key,
                             original_name=f"{NAMES.get(key, 'Document')}.{ext}", stored_path=path,
                             content_type=mime, size_bytes=os.path.getsize(path))
    db.add(doc)
    return doc


def process(db: Session, msg: WhatsAppMessage, read=ocr) -> Optional[str]:
    """
    Recognise and file one photo or PDF from the chat. Returns the document's key
    when it was filed. Only for campaign contacts, only files we have downloaded.
    """
    payload = dict(msg.payload or {})
    path = payload.get("stored")
    if msg.direction != "IN" or msg.kind not in ("image", "document") or not path or payload.get("document"):
        return None
    conv = db.get(WhatsAppConversation, msg.phone)
    if conv is None or not (conv.bot_data or {}).get("campaign"):
        return None
    mime = (payload.get("mime_type") or "").split(";")[0].strip()
    hint = " ".join(x for x in (payload.get("filename"), payload.get("caption"), msg.body) if x)
    try:
        text = read(path, mime)
    except Exception as exc:
        logger.warning(f"chat_documents event=OCR_FAILED message_id={msg.message_id} reason={type(exc).__name__}")
        msg.payload = {**payload, "document": {"key": None, "error": "could not be read"}}
        db.commit()
        return None

    key = classify(text, hint, is_image=msg.kind == "image")
    if key is None:
        msg.payload = {**payload, "document": {"key": None}}
        bot.flag(conv, "Sent a file in the chat that the bot could not recognise as a document: please look at it.")
        db.commit()
        return None
    key = for_conversation(conv, key)
    have = {d for (d,) in db.query(OnboardingDocument.doc_type).filter(OnboardingDocument.phone == conv.phone)}
    if key in bot.rows_done(have):
        # Already in (from the upload page, or an earlier photo): the first stays.
        msg.payload = {**payload, "document": {"key": key, "label": NAMES.get(key), "kept": False}}
        db.commit()
        return None
    _file(db, conv, key, path, mime or "application/octet-stream")
    msg.payload = {**payload, "document": {"key": key, "label": NAMES.get(key), "kept": True}}
    db.commit()
    logger.info(f"chat_documents event=FILED phone=...{conv.phone[-4:]} key={key}")
    _all_in(db, conv)
    return key


def _all_in(db: Session, conv: WhatsAppConversation) -> None:
    """Every required document is in: thank them once, stop the questions, and tell the team."""
    have = bot.rows_done(d for (d,) in db.query(OnboardingDocument.doc_type)
                         .filter(OnboardingDocument.phone == conv.phone))
    complete = all(d["key"] in have for d in bot.required_for(conv))
    if complete and not conv.documents_submitted_at:
        bot.documents_submitted(db, conv)
        db.commit()
        from src.services import documents_report
        documents_report.send(conv.phone, bot.public_base_url())
    from src.services import drive_uploads
    drive_uploads.save_in_background(conv.phone)


def process_in_background(message_ids: list) -> None:
    """After the media is downloaded, in its own session."""
    from src.database import SessionLocal
    db = SessionLocal()
    try:
        for message_id in message_ids:
            msg = db.query(WhatsAppMessage).filter(WhatsAppMessage.message_id == message_id).first()
            if msg is None:
                continue
            try:
                process(db, msg)
            except Exception:
                db.rollback()
                logger.exception(f"chat_documents event=FAILED message_id={message_id}")
    finally:
        db.close()
