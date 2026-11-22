"""
Copies submitted onboarding documents into Google Drive.

Each person gets a folder, named for them, inside GOOGLE_DRIVE_FOLDER_ID, and
their files go into it. Talking to Drive is the google_drive adapter's (Phase 2,
22 Nov 2026); this module decides whose documents go, into which folder, and what
is recorded about them.

A file is deleted locally only once Drive holds it. If the upload fails, the
local file stays, the reason is recorded, and the inbox offers to try again.
"""
import logging
import os

from sqlalchemy.orm import Session

from src.models.inbox import OnboardingDocument, WhatsAppConversation
from src.services import google_drive as gd
from src.services import onboarding_bot

logger = logging.getLogger("gmap_scraper.drive")

# The adapter's, under the names the Inbox and the tests already use.
FILES_URL = gd.FILES_URL
folder_id = gd.folder_id
configured = gd.configured
service_account_email = gd.service_account_email
_session = gd.session
_create_folder = gd.create_folder
_upload = gd.upload


def trash(file_id: str) -> None:
    """Move a file or folder to Drive's trash (services/retention): recoverable there for 30 days."""
    gd.trash(file_id)


def _folder_name(conv: WhatsAppConversation) -> str:
    who = conv.profile_name or "WhatsApp"
    pin = ((conv.bot_data or {}).get("coverage") or {}).get("pincode")
    parts = [who, conv.phone] + ([f"PIN {pin}"] if pin else [])
    # Drive allows most characters, but a slash reads as a path to people.
    return " · ".join(parts).replace("/", "-")[:200]


def save_conversation(db: Session, conv: WhatsAppConversation) -> int:
    """
    Copy this person's documents not yet in Drive. Returns how many were copied.

    Raises if Drive is not configured; records each file's own failure and
    carries on with the rest.
    """
    if not configured():
        raise RuntimeError("Google Drive is not set up: GOOGLE_DRIVE_FOLDER_ID and "
                           "GOOGLE_CREDENTIALS_BASE64 are both needed.")

    pending = (db.query(OnboardingDocument)
               .filter(OnboardingDocument.phone == conv.phone, OnboardingDocument.drive_file_id.is_(None))
               .all())
    if not pending:
        return 0

    session = _session()
    folder = (conv.bot_data or {}).get("drive_folder_id")
    if not folder:
        created = _create_folder(session, _folder_name(conv), folder_id())
        folder = created["id"]
        conv.bot_data = {**(conv.bot_data or {}), "drive_folder_id": folder}
        conv.drive_folder_url = created.get("webViewLink")
        db.commit()

    labels = onboarding_bot.DOCUMENT_LABELS
    copied = 0
    for doc in pending:
        name = f"{labels.get(doc.doc_type, doc.doc_type)} - {doc.original_name or doc.doc_type}"
        try:
            out = _upload(session, doc.stored_path, name, doc.content_type, folder)
        except Exception as exc:
            doc.drive_error = str(exc)[:500]
            db.commit()
            logger.warning(f"drive event=UPLOAD_FAILED doc={doc.document_id} error={exc}")
            continue
        doc.drive_file_id = out["id"]
        doc.drive_url = out.get("webViewLink")
        doc.drive_error = None
        db.commit()
        copied += 1
        # Drive holds it now; one copy of an identity document is enough.
        try:
            os.remove(doc.stored_path)
        except OSError:
            pass
    logger.info(f"drive event=SAVED phone=...{conv.phone[-4:]} files={copied}/{len(pending)}")
    return copied


def save_in_background(phone: str) -> None:
    """Runs after the upload page has answered, in its own session."""
    from src.database import SessionLocal

    db = SessionLocal()
    try:
        conv = db.query(WhatsAppConversation).filter(WhatsAppConversation.phone == phone).first()
        if conv is None:
            return
        try:
            save_conversation(db, conv)
        except Exception as exc:
            db.rollback()
            reason = str(exc)[:500]
            for doc in db.query(OnboardingDocument).filter(
                OnboardingDocument.phone == phone, OnboardingDocument.drive_file_id.is_(None)
            ).all():
                doc.drive_error = reason
            db.commit()
            logger.warning(f"drive event=NOT_SAVED phone=...{phone[-4:]} reason={reason}")
    finally:
        db.close()
