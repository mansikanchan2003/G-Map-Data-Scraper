"""
Copies submitted onboarding documents into Google Drive.

Each person gets a folder, named for them, inside GOOGLE_DRIVE_FOLDER_ID, and
their files go into it. It uses the same service account as the live Google
Sheet (GOOGLE_CREDENTIALS_BASE64).

A service account has no Drive storage of its own, so it cannot put a file in
someone's personal "My Drive" even when a folder there is shared with it;
Google refuses with storageQuotaExceeded. The folder therefore has to be in a
shared drive, with the service account added to it as a Content manager.

A file is deleted locally only once Drive holds it. If the upload fails, the
local file stays, the reason is recorded, and the inbox offers to try again.
"""
import base64
import json
import logging
import os
from typing import Optional

from sqlalchemy.orm import Session

from src.models.inbox import OnboardingDocument, WhatsAppConversation
from src.services import onboarding_bot

logger = logging.getLogger("gmap_scraper.drive")

SCOPES = ["https://www.googleapis.com/auth/drive"]
FILES_URL = "https://www.googleapis.com/drive/v3/files"
UPLOAD_URL = "https://www.googleapis.com/upload/drive/v3/files"
FOLDER_MIME = "application/vnd.google-apps.folder"


def folder_id() -> str:
    return (os.environ.get("GOOGLE_DRIVE_FOLDER_ID") or "").strip()


def configured() -> bool:
    return bool(folder_id() and (os.environ.get("GOOGLE_CREDENTIALS_BASE64") or "").strip())


def service_account_email() -> Optional[str]:
    """The address the Drive folder has to be shared with, for the inbox to show."""
    raw = os.environ.get("GOOGLE_CREDENTIALS_BASE64")
    if not raw:
        return None
    try:
        return json.loads(base64.b64decode(raw).decode("utf-8")).get("client_email")
    except Exception:
        return None


def _session():
    from google.auth.transport.requests import AuthorizedSession
    from google.oauth2.service_account import Credentials

    info = json.loads(base64.b64decode(os.environ["GOOGLE_CREDENTIALS_BASE64"]).decode("utf-8"))
    return AuthorizedSession(Credentials.from_service_account_info(info, scopes=SCOPES))


def _check(resp) -> dict:
    if resp.status_code >= 400:
        try:
            err = resp.json().get("error", {})
            reason = (err.get("errors") or [{}])[0].get("reason") or err.get("status")
            message = err.get("message") or resp.text
        except ValueError:
            reason, message = None, resp.text
        if reason == "storageQuotaExceeded":
            message = ("The Drive folder is not in a shared drive. A service account has no "
                       "storage of its own, so the folder must be in a shared drive with "
                       "the service account added as Content manager.")
        raise RuntimeError(f"Google Drive refused ({resp.status_code}): {message}"[:500])
    return resp.json()


def _create_folder(session, name: str, parent: str) -> dict:
    return _check(session.post(
        FILES_URL,
        params={"supportsAllDrives": "true", "fields": "id,webViewLink"},
        json={"name": name, "mimeType": FOLDER_MIME, "parents": [parent]},
        timeout=30,
    ))


def _upload(session, path: str, name: str, content_type: str, parent: str) -> dict:
    boundary = "autogmap-onboarding-upload"
    meta = json.dumps({"name": name, "parents": [parent]})
    with open(path, "rb") as fh:
        data = fh.read()
    body = (
        f"--{boundary}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n{meta}\r\n"
        f"--{boundary}\r\nContent-Type: {content_type}\r\n\r\n"
    ).encode("utf-8") + data + f"\r\n--{boundary}--\r\n".encode("utf-8")
    return _check(session.post(
        UPLOAD_URL,
        params={"uploadType": "multipart", "supportsAllDrives": "true", "fields": "id,webViewLink"},
        data=body,
        headers={"Content-Type": f"multipart/related; boundary={boundary}"},
        timeout=120,
    ))


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
