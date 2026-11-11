"""
Recordings of phone calls with applicants, from the team's call-recorder app
on Kavya Ma'am's phone (11 Nov 2026), kept so they can go to Sumit for training
his AI calling agent.

Two ways in, whichever the app offers:
  - push: the app uploads each recording to POST /api/v1/call-recorder/recordings;
  - pull: the app's own endpoint lists its recordings (CALL_RECORDINGS_SOURCE_URL,
    key in CALL_RECORDINGS_SOURCE_KEY) and AutoGMap fetches the new ones every
    15 minutes.

Either way only calls with people on the Applications tab are kept (the app
reads that list from GET /api/v1/call-recorder/numbers; it is checked again
here). The audio is on disk under CALL_RECORDINGS_DIR; the database row says
whose call it was, which way, when and how long.
"""
import io
import logging
import os
import re
import threading
import uuid
import zipfile
from datetime import datetime, timezone
from typing import Dict, List, Optional
from urllib.parse import urljoin
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from src.models.inbox import CallRecording
from src.services import applications, inbox

logger = logging.getLogger("gmap_scraper.call_recordings")

RECORDINGS_DIR = os.environ.get("CALL_RECORDINGS_DIR", os.path.join("data", "call_recordings"))
MAX_BYTES = 60 * 1024 * 1024
FETCH_EVERY_SECONDS = 15 * 60
AUDIO_TYPES = {
    "audio/mpeg": ".mp3", "audio/mp3": ".mp3", "audio/mp4": ".m4a", "audio/x-m4a": ".m4a", "audio/aac": ".aac",
    "audio/amr": ".amr", "audio/3gpp": ".3gp", "audio/ogg": ".ogg", "audio/opus": ".opus", "audio/wav": ".wav",
    "audio/x-wav": ".wav", "audio/webm": ".webm", "video/3gpp": ".3gp", "video/mp4": ".m4a",
}
EXTS = {v: k for k, v in AUDIO_TYPES.items()}
# A time sent without a zone is the phone's own, India.
IST = ZoneInfo("Asia/Kolkata")


# The source of a recording with one of the team's test phones (CALL_RECORDER_TEST_NUMBERS).
TEST = "test"


class Refused(ValueError):
    """A recording that is not kept, and why."""


def _aware(v) -> Optional[datetime]:
    if v in (None, ""):
        return None
    if isinstance(v, datetime):
        return v if v.tzinfo else v.replace(tzinfo=timezone.utc)
    if isinstance(v, (int, float)) or (isinstance(v, str) and v.strip().isdigit()):
        n = float(v)
        return datetime.fromtimestamp(n / 1000 if n > 1e11 else n, tz=timezone.utc)   # ms or s since 1970
    try:
        d = datetime.fromisoformat(str(v).strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    return d if d.tzinfo else d.replace(tzinfo=IST)


def _utc(v) -> Optional[datetime]:
    d = _aware(v)
    return d.astimezone(timezone.utc) if d else None


def _direction(v) -> Optional[str]:
    s = str(v or "").strip().lower()
    if s in ("in", "incoming", "inbound", "received", "1"):
        return "in"
    if s in ("out", "outgoing", "outbound", "dialled", "dialed", "2"):
        return "out"
    return None


def application_phones(db: Session) -> Dict[str, str]:
    """Last 10 digits -> the applicant's phone, for everyone on the Applications tab."""
    return {c["local"]: c["phone"] for c in applications.recorder_contacts(db)}


def match(db: Session, raw_phone: str, phones: Optional[Dict[str, str]] = None) -> Optional[str]:
    """The applicant a number from the phone's call log belongs to (any +91/0 form), or None."""
    digits = re.sub(r"\D", "", raw_phone or "")
    if len(digits) < 10:
        return None
    return (phones if phones is not None else application_phones(db)).get(digits[-10:])


def _kind(content_type: Optional[str], filename: Optional[str]) -> tuple:
    ct = (content_type or "").split(";")[0].strip().lower()
    ext = os.path.splitext(filename or "")[1].lower()
    if ct in AUDIO_TYPES:
        return ct, AUDIO_TYPES[ct]
    # The file name decides only when the type says nothing (phones often send octet-stream).
    if ext in EXTS and ct in ("", "application/octet-stream", "binary/octet-stream"):
        return EXTS[ext], ext
    raise Refused(f"Not an audio file ({ct or ext or 'unknown type'}).")


def save(db: Session, *, phone: str, data: bytes, content_type: Optional[str] = None, filename: Optional[str] = None,
         external_id: Optional[str] = None, direction=None, started_at=None, duration_seconds=None,
         device: Optional[str] = None, source: str = "phone_recorder",
         phones: Optional[Dict[str, str]] = None) -> CallRecording:
    """Keeps one recording, if it is a call with an applicant; the same external id twice is kept once."""
    external_id = (str(external_id).strip()[:200] or None) if external_id not in (None, "") else None
    if external_id:
        have = db.query(CallRecording).filter(CallRecording.external_id == external_id).first()
        if have:
            return have
    who = match(db, phone, phones)
    if not who:
        raise Refused("This number is not on the Applications tab, so its call is not kept.")
    # A call with one of the team's test phones: kept, marked as a test, never in Sumit's zip.
    if who[-10:] in applications.test_locals() and who not in {
            c["phone"] for c in applications.recorder_contacts(db, with_tests=False)}:
        source = TEST
    if not data:
        raise Refused("The recording is empty.")
    if len(data) > MAX_BYTES:
        raise Refused(f"The recording is larger than {MAX_BYTES // (1024 * 1024)} MB.")
    ct, ext = _kind(content_type, filename)

    rid = uuid.uuid4().hex
    folder = os.path.join(RECORDINGS_DIR, re.sub(r"\D", "", who))
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, rid + ext)
    with open(path, "wb") as f:
        f.write(data)
    try:
        duration = int(float(duration_seconds)) if duration_seconds not in (None, "") else None
    except (TypeError, ValueError):
        duration = None
    rec = CallRecording(recording_id=rid, phone=who, source=source, external_id=external_id,
                        direction=_direction(direction), started_at=_utc(started_at), duration_seconds=duration,
                        stored_path=path, content_type=ct, size_bytes=len(data),
                        device=(device or "").strip()[:100] or None)
    db.add(rec)
    db.commit()
    logger.info(f"call_recordings event=SAVED id={rid} source={source} bytes={len(data)}")
    return rec


def as_dict(r: CallRecording) -> dict:
    iso = lambda d: inbox.aware(d).isoformat() if d else None   # noqa: E731
    return {"recording_id": r.recording_id, "phone": r.phone, "direction": r.direction,
            "started_at": iso(r.started_at), "duration_seconds": r.duration_seconds,
            "content_type": r.content_type, "size_bytes": r.size_bytes, "device": r.device,
            "source": r.source, "received_at": iso(r.received_at)}


def for_phone(db: Session, phone: str) -> List[dict]:
    rows = (db.query(CallRecording).filter(CallRecording.phone == phone)
            .order_by(CallRecording.started_at.desc().nullslast(), CallRecording.received_at.desc()).all())
    return [as_dict(r) for r in rows]


def summary(db: Session) -> dict:
    every = db.query(CallRecording).all()
    rows = [r for r in every if r.source != TEST]
    return {"recordings": len(rows), "tests": len(every) - len(rows), "people": len({r.phone for r in rows}),
            "seconds": sum(r.duration_seconds or 0 for r in rows),
            "pull": bool(source_url()), "last_received_at": max(
                (inbox.aware(r.received_at).isoformat() for r in rows if r.received_at), default=None)}


def export_zip(db: Session, since: Optional[datetime] = None) -> bytes:
    """Every recording (or those received since a time) as one zip for Sumit, with a CSV of what each is.
    The CSV names each call by the last 4 digits of the number only."""
    q = db.query(CallRecording).filter(CallRecording.source != TEST)
    if since:
        q = q.filter(CallRecording.received_at >= since)
    buf = io.BytesIO()
    lines = ["file,direction,started_at,duration_seconds,number_ends"]
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for r in q.order_by(CallRecording.started_at).all():
            if not os.path.exists(r.stored_path):
                continue
            name = os.path.basename(r.stored_path)
            z.write(r.stored_path, f"recordings/{name}")
            started = inbox.aware(r.started_at).isoformat() if r.started_at else ""
            lines.append(f"recordings/{name},{r.direction or ''},{started},{r.duration_seconds or ''},{r.phone[-4:]}")
        z.writestr("recordings.csv", "\n".join(lines) + "\n")
    return buf.getvalue()


# --- Pull: the app's own endpoint lists its recordings ----------------------------------------

def source_url() -> str:
    return (os.environ.get("CALL_RECORDINGS_SOURCE_URL") or "").strip()


def _headers() -> dict:
    key = (os.environ.get("CALL_RECORDINGS_SOURCE_KEY") or "").strip()
    return {"X-API-Key": key, "Authorization": f"Bearer {key}"} if key else {}


def _pick(item: dict, *names):
    for n in names:
        if item.get(n) not in (None, ""):
            return item[n]
    return None


def fetch(db: Session, http=None) -> dict:
    """
    Fetches the new recordings from the app's endpoint. The listing may be a
    list or {"recordings"|"data"|"items": [...]}; each item names its id, the
    number, the audio's URL and, if it has them, direction, time and length.
    Recordings of numbers not on the Applications tab are skipped unfetched.
    """
    import requests
    url = source_url()
    if not url:
        return {"enabled": False}
    http = http or requests
    since = db.query(CallRecording.started_at).filter(CallRecording.source == "pull") \
        .order_by(CallRecording.started_at.desc().nullslast()).limit(1).scalar()
    params = {"since": inbox.aware(since).isoformat()} if since else {}
    r = http.get(url, headers=_headers(), params=params, timeout=30)
    r.raise_for_status()
    body = r.json()
    items = body if isinstance(body, list) else next(
        (body[k] for k in ("recordings", "data", "items", "results") if isinstance(body.get(k), list)), [])
    phones = application_phones(db)
    kept = skipped = failed = 0
    for it in items:
        if not isinstance(it, dict):
            continue
        ext_id = _pick(it, "id", "recording_id", "uuid", "file_name", "filename")
        number = _pick(it, "phone", "number", "phone_number", "mobile", "caller", "contact")
        audio = _pick(it, "url", "audio_url", "file_url", "recording_url", "download_url")
        if not number or not match(db, str(number), phones) or not audio:
            skipped += 1
            continue
        ext = f"pull:{ext_id}" if ext_id else None
        if ext and db.query(CallRecording.recording_id).filter(CallRecording.external_id == ext).first():
            continue
        try:
            a = http.get(urljoin(url, str(audio)), headers=_headers(), timeout=120)
            a.raise_for_status()
            save(db, phone=str(number), data=a.content, content_type=a.headers.get("content-type"),
                 filename=str(_pick(it, "file_name", "filename") or audio), external_id=ext,
                 direction=_pick(it, "direction", "type", "call_type"),
                 started_at=_pick(it, "started_at", "start_time", "timestamp", "date", "created_at"),
                 duration_seconds=_pick(it, "duration_seconds", "duration"),
                 device=_pick(it, "device", "device_name"), source="pull", phones=phones)
            kept += 1
        except Exception as e:
            db.rollback()
            failed += 1
            logger.warning(f"call_recordings event=FETCH_ONE_FAILED reason={type(e).__name__}")
    logger.info(f"call_recordings event=FETCHED listed={len(items)} kept={kept} skipped={skipped} failed={failed}")
    return {"enabled": True, "listed": len(items), "kept": kept, "skipped": skipped, "failed": failed}


_thread: Optional[threading.Thread] = None
_stop = threading.Event()


def _loop() -> None:
    from src.database import SessionLocal
    while not _stop.is_set():
        if source_url():
            db = SessionLocal()
            try:
                fetch(db)
            except Exception as e:
                db.rollback()
                logger.warning(f"call_recordings event=FETCH_FAILED reason={type(e).__name__}")
            finally:
                db.close()
        _stop.wait(FETCH_EVERY_SECONDS)


def start() -> None:
    global _thread
    if _thread and _thread.is_alive():
        return
    _stop.clear()
    _thread = threading.Thread(target=_loop, name="call-recordings", daemon=True)
    _thread.start()


def stop() -> None:
    _stop.set()
