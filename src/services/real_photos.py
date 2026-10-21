"""
Real photographs of SBI Customer Service Points, for the Template Studio's posters.

The free AI photos looked AI-made and showed nothing of a CSP (2026-10-21),
so the team uploads real ones and a poster is set on one of those first; the
AI photo is made only when no real photo is left for the state.

A photo is for one state, or for any state when none is given. The least
used is picked, so a state's photos take turns, and one for its own state
comes before one for any state. Each upload records that the people in it
agreed to its use; without that it is refused.
"""
import io
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy import or_
from sqlalchemy.orm import Session

from src.models.studio import StudioRealPhoto

EXTENSIONS = {"JPEG": ".jpg", "PNG": ".png", "WEBP": ".webp"}
MAX_BYTES = 15 * 1024 * 1024
# Smaller than this, the photo is blurred once it fills the poster.
MIN_WIDTH, MIN_HEIGHT = 800, 600


class PhotoRefused(ValueError):
    """The upload cannot be used; the message says why."""


def check_image(data: bytes) -> str:
    """The file extension for an uploaded photo, or PhotoRefused if it is not one."""
    from PIL import Image

    if len(data) > MAX_BYTES:
        raise PhotoRefused(f"The photo is {len(data) / 1024 / 1024:.1f} MB; at most {MAX_BYTES // 1024 // 1024} MB.")
    try:
        with Image.open(io.BytesIO(data)) as im:
            im.verify()
        with Image.open(io.BytesIO(data)) as im:
            kind, (w, h) = im.format, im.size
    except Exception:
        raise PhotoRefused("That file is not a photo (JPG, PNG or WebP).")
    if kind not in EXTENSIONS:
        raise PhotoRefused("Only JPG, PNG or WebP photos can be used.")
    if w < MIN_WIDTH or h < MIN_HEIGHT:
        raise PhotoRefused(f"The photo is {w}×{h}; at least {MIN_WIDTH}×{MIN_HEIGHT} is needed so it is sharp on the poster.")
    return EXTENSIONS[kind]


def add(db: Session, media_id: str, *, state: Optional[str], note: Optional[str],
        uploaded_by: Optional[str], consent: bool) -> StudioRealPhoto:
    if not consent:
        raise PhotoRefused("Confirm that the people in the photo agreed to it being used in Eko's posters.")
    row = StudioRealPhoto(photo_id=uuid.uuid4().hex, media_id=media_id, state=(state or "").strip() or None,
                          note=(note or "").strip()[:300] or None, uploaded_by=uploaded_by, consent=True,
                          active=True, times_used=0)
    db.add(row)
    db.commit()
    return row


def listing(db: Session) -> List[StudioRealPhoto]:
    return (db.query(StudioRealPhoto)
            .order_by(StudioRealPhoto.active.desc(), StudioRealPhoto.created_at.desc()).all())


def set_active(db: Session, photo_id: str, active: bool) -> Optional[StudioRealPhoto]:
    row = db.get(StudioRealPhoto, photo_id)
    if row:
        row.active = active
        db.commit()
    return row


def pick(db: Session, state: Optional[str], avoid: Optional[str] = None) -> Optional[StudioRealPhoto]:
    """
    The photo for the next poster in `state`, marked as used; None when there
    is none. `avoid` is the media the draft has now, so "New photo" moves on.
    """
    q = db.query(StudioRealPhoto).filter(StudioRealPhoto.active.is_(True), StudioRealPhoto.consent.is_(True))
    q = q.filter(or_(StudioRealPhoto.state.is_(None), StudioRealPhoto.state == state)) if state else \
        q.filter(StudioRealPhoto.state.is_(None))
    rows = [r for r in q.all() if r.media_id != avoid]
    if not rows:
        return None
    oldest = datetime.min.replace(tzinfo=timezone.utc)
    row = min(rows, key=lambda r: (r.state is None, r.times_used,
                                   _utc(r.last_used_at) or oldest, r.photo_id))
    row.times_used += 1
    row.last_used_at = datetime.now(timezone.utc)
    db.commit()
    return row


def _utc(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is not None and dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt
