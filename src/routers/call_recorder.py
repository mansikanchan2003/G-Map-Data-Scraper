"""
For the team's call-recorder app (Kavya Ma'am's phone, 11 Nov 2026): which
numbers' call recordings to keep. Only the people on the Applications tab, so
no other call is recorded.

The app sends the key in the X-API-Key header, or as "Authorization: Bearer <key>"
(12 Nov 2026: the app's first calls were all refused); the key is CALL_RECORDER_API_KEY
on the server. With none set, every request is refused. A refusal is audited with
why (no key, or a wrong one, and in which header), never with the key itself.
"""
import hmac
import logging
import os
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from src.database import get_db
from src.models import User
from src.routers.auth import current_user
from src.services import applications

logger = logging.getLogger("gmap_scraper.call_recorder")

router = APIRouter(prefix="/api/v1/call-recorder", tags=["Call recorder"])


def _clean(value: Optional[str]) -> str:
    """A key as sent, without the spaces, line breaks or quotes it is often pasted with."""
    return (value or "").strip().strip('"').strip("'").strip()


def key_ok(given: Optional[str]) -> bool:
    expected = (os.environ.get("CALL_RECORDER_API_KEY") or "").strip()
    return len(expected) >= 24 and hmac.compare_digest(expected, _clean(given))


def check_key(request: Request) -> tuple:
    """
    (allowed, why): the key from X-API-Key, else from "Authorization: Bearer <key>".
    `why` says what was wrong, for the audit log, and names no part of the key.
    """
    if not (os.environ.get("CALL_RECORDER_API_KEY") or "").strip():
        return False, "no key set on the server"
    header = request.headers.get("x-api-key")
    auth = request.headers.get("authorization") or ""
    bearer = auth[7:] if auth[:7].lower() == "bearer " else None
    if header is None and bearer is None:
        return False, ("Authorization header is not 'Bearer <key>'" if auth else "no key sent")
    for name, value in (("X-API-Key", header), ("Bearer", bearer)):
        if value is not None and key_ok(value):
            return True, None
    sent = " and ".join(n for n, v in (("X-API-Key", header), ("Bearer", bearer)) if v is not None)
    return False, f"wrong key in {sent}"


def _audit(method: str, path: str, status: int, why: Optional[str]) -> None:
    from src.services import audit
    audit.write(SimpleNamespace(email="call-recorder-app", role=None), method, path, status,
                {"refused": why} if why else None)


@router.get("/numbers")
def numbers(request: Request, db: Session = Depends(get_db)):
    """
    Everyone on the Applications tab: phone (+91…), the last 10 digits, their
    WhatsApp name, and when they first wrote. New applications appear here as
    they come in, so the app should fetch again regularly (every 15 minutes is plenty).
    """
    ok, why = check_key(request)
    _audit("GET", "/api/v1/call-recorder/numbers", 200 if ok else 401, why)
    if not ok:
        raise HTTPException(status_code=401, detail=f"Missing or wrong API key ({why}).")
    contacts = applications.recorder_contacts(db)
    logger.info(f"call_recorder event=NUMBERS count={len(contacts)}")
    return {"as_of": datetime.now(timezone.utc).isoformat(), "count": len(contacts), "numbers": contacts}


@router.post("/recordings", status_code=201)
async def upload_recording(
    request: Request,
    file: UploadFile = File(...),
    phone: str = Form(..., max_length=40),
    recording_id: Optional[str] = Form(None, max_length=200),
    direction: Optional[str] = Form(None, max_length=20),
    started_at: Optional[str] = Form(None, max_length=40),
    duration_seconds: Optional[str] = Form(None, max_length=20),
    device: Optional[str] = Form(None, max_length=100),
    db: Session = Depends(get_db),
):
    """
    The app uploads one call's recording (multipart form): the audio file, the
    other person's number, and if it has them the app's id for the recording,
    direction (in/out), when it started and how long it was. Only calls with
    people on the Applications tab are kept; others are refused with 422.
    """
    from src.services import call_recordings
    ok, why = check_key(request)
    _audit("POST", "/api/v1/call-recorder/recordings", 201 if ok else 401, why)
    if not ok:
        raise HTTPException(status_code=401, detail=f"Missing or wrong API key ({why}).")
    data = await file.read(call_recordings.MAX_BYTES + 1)
    try:
        rec = call_recordings.save(db, phone=phone, data=data, content_type=file.content_type, filename=file.filename,
                                   external_id=recording_id, direction=direction, started_at=started_at,
                                   duration_seconds=duration_seconds, device=device, source="push")
    except call_recordings.Refused as e:
        raise HTTPException(status_code=422, detail=str(e))
    return {"status": "kept", "recording_id": rec.recording_id}


# --- For the team, signed in --------------------------------------------------------------------

team = APIRouter(prefix="/api/v1/call-recordings", tags=["Call recorder"])
LISTENERS = ("admin", "manager", "operator")


def _listener(user: User = Depends(current_user)) -> User:
    if user.role not in LISTENERS:
        raise HTTPException(status_code=403, detail="Call recordings are for managers and operators.")
    return user


@team.get("/summary")
def recordings_summary(db: Session = Depends(get_db), _: User = Depends(_listener)):
    from src.services import call_recordings
    return call_recordings.summary(db)


@team.get("/{recording_id}/audio")
def recording_audio(recording_id: str, db: Session = Depends(get_db), _: User = Depends(_listener)):
    from src.models.inbox import CallRecording
    rec = db.get(CallRecording, recording_id)
    if not rec or not os.path.exists(rec.stored_path):
        raise HTTPException(status_code=404, detail="Recording not found.")
    return FileResponse(rec.stored_path, media_type=rec.content_type or "application/octet-stream")


@team.get("/export")
def export_recordings(since: Optional[str] = None, db: Session = Depends(get_db), user: User = Depends(_listener)):
    """Every recording as one zip, for Sumit's AI calling agent; the CSV inside keeps only the number's last 4 digits."""
    from src.services import call_recordings
    when = call_recordings._aware(since) if since else None
    data = call_recordings.export_zip(db, when)
    logger.info(f"call_recorder event=EXPORT by={user.email} bytes={len(data)}")
    name = f"autogmap_call_recordings_{datetime.now(timezone.utc):%Y%m%d}.zip"
    return Response(content=data, media_type="application/zip",
                    headers={"Content-Disposition": f'attachment; filename="{name}"'})


@team.get("/numbers.xlsx")
def numbers_excel(db: Session = Depends(get_db), user: User = Depends(_listener)):
    """
    The call-recorder app's list as Excel (Phone | Name | Description | Active), for
    uploading through the app's own admin panel. The API stays the live list; this is
    its backup copy. Managers and operators only: it holds every applicant's number.
    """
    from io import BytesIO
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.worksheet.table import Table, TableStyleInfo
    from src.services import audit

    rows = applications.recorder_contacts(db, with_place=True, with_tests=False)
    wb = Workbook()
    ws = wb.active
    ws.title = "Applicant numbers"
    ws.append(["Phone", "Name", "Description", "Active"])
    for r in rows:
        ws.append([r["local"], r["name"] or "", r.get("place") or "AutoGMap applicant", "Yes"])
    head = PatternFill("solid", fgColor="0B4A5A")
    for c in ws[1]:
        c.font, c.fill, c.alignment = Font(bold=True, color="FFFFFF"), head, Alignment(vertical="center")
    for row in ws.iter_rows(min_row=2, max_col=1):
        row[0].number_format = "@"          # keep the leading digits as typed, never 9.87E+09
    for col, width in zip("ABCD", (16, 28, 30, 10)):
        ws.column_dimensions[col].width = width
    ws.freeze_panes = "A2"
    if rows:
        t = Table(displayName="ApplicantNumbers", ref=f"A1:D{len(rows) + 1}")
        t.tableStyleInfo = TableStyleInfo(name="TableStyleMedium2", showRowStripes=True)
        ws.add_table(t)
    buf = BytesIO()
    wb.save(buf)
    audit.write(user, "GET", "/api/v1/call-recordings/numbers.xlsx", 200, {"rows": len(rows)})
    logger.info(f"call_recorder event=NUMBERS_EXCEL by={user.email} rows={len(rows)}")
    name = f"autogmap_applicant_numbers_{datetime.now(timezone.utc):%Y%m%d}.xlsx"
    return Response(content=buf.getvalue(),
                    media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f'attachment; filename="{name}"'})


@team.post("/fetch")
def fetch_now(db: Session = Depends(get_db), _: User = Depends(_listener)):
    """Fetches new recordings from the app's endpoint now, instead of at the next 15-minute round."""
    from src.services import call_recordings
    if not call_recordings.source_url():
        raise HTTPException(status_code=400, detail="The app's recordings endpoint is not set (CALL_RECORDINGS_SOURCE_URL).")
    try:
        return call_recordings.fetch(db)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"The app's endpoint did not answer properly ({type(e).__name__}).")
