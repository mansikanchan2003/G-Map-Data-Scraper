"""
Google Drive, as an adapter: folders, uploads and the trash in a shared drive, with the
service account in GOOGLE_CREDENTIALS_BASE64 (Phase 2, 22 Nov 2026: split out of
drive_uploads, which keeps what is AutoGMap's own: whose documents, which folder, what
is recorded). Knows nothing of conversations or documents.

A service account has no Drive storage of its own, so it cannot put a file in
someone's personal "My Drive" even when a folder there is shared with it;
Google refuses with storageQuotaExceeded. The folder therefore has to be in a
shared drive, with the service account added to it as a Content manager.
"""
import base64
import json
import os
from typing import Optional

SCOPES = ["https://www.googleapis.com/auth/drive"]
FILES_URL = "https://www.googleapis.com/drive/v3/files"
UPLOAD_URL = "https://www.googleapis.com/upload/drive/v3/files"
FOLDER_MIME = "application/vnd.google-apps.folder"


def folder_id() -> str:
    """The shared-drive folder everything goes in (GOOGLE_DRIVE_FOLDER_ID)."""
    return (os.environ.get("GOOGLE_DRIVE_FOLDER_ID") or "").strip()


def configured() -> bool:
    return bool(folder_id() and (os.environ.get("GOOGLE_CREDENTIALS_BASE64") or "").strip())


def service_account_email() -> Optional[str]:
    """The address the Drive folder has to be shared with."""
    raw = os.environ.get("GOOGLE_CREDENTIALS_BASE64")
    if not raw:
        return None
    try:
        return json.loads(base64.b64decode(raw).decode("utf-8")).get("client_email")
    except Exception:
        return None


def session():
    from google.auth.transport.requests import AuthorizedSession
    from google.oauth2.service_account import Credentials

    info = json.loads(base64.b64decode(os.environ["GOOGLE_CREDENTIALS_BASE64"]).decode("utf-8"))
    return AuthorizedSession(Credentials.from_service_account_info(info, scopes=SCOPES))


def check(resp) -> dict:
    """The answer's JSON, or an error saying in plain words why Drive refused."""
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


def create_folder(session_, name: str, parent: str) -> dict:
    return check(session_.post(
        FILES_URL,
        params={"supportsAllDrives": "true", "fields": "id,webViewLink"},
        json={"name": name, "mimeType": FOLDER_MIME, "parents": [parent]},
        timeout=30,
    ))


def upload(session_, path: str, name: str, content_type: str, parent: str) -> dict:
    boundary = "autogmap-onboarding-upload"
    meta = json.dumps({"name": name, "parents": [parent]})
    with open(path, "rb") as fh:
        data = fh.read()
    body = (
        f"--{boundary}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n{meta}\r\n"
        f"--{boundary}\r\nContent-Type: {content_type}\r\n\r\n"
    ).encode("utf-8") + data + f"\r\n--{boundary}--\r\n".encode("utf-8")
    return check(session_.post(
        UPLOAD_URL,
        params={"uploadType": "multipart", "supportsAllDrives": "true", "fields": "id,webViewLink"},
        data=body,
        headers={"Content-Type": f"multipart/related; boundary={boundary}"},
        timeout=120,
    ))


def trash(file_id: str) -> None:
    """Move a file or folder to Drive's trash: recoverable there for 30 days, not deleted."""
    if not configured():
        raise RuntimeError("Google Drive is not set up, so the Drive copy was left as it is.")
    check(session().patch(f"{FILES_URL}/{file_id}", params={"supportsAllDrives": "true", "fields": "id"},
                          json={"trashed": True}, timeout=30))
