"""
For the team's call-recorder app (Kavya Ma'am's phone, 11 Nov 2026): which
numbers' call recordings to keep. Only the people on the Applications tab, so
no other call is recorded.

The app sends the key in the X-API-Key header; the key is CALL_RECORDER_API_KEY
on the server. With none set, every request is refused.
"""
import hmac
import logging
import os
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy.orm import Session

from src.database import get_db
from src.services import applications

logger = logging.getLogger("gmap_scraper.call_recorder")

router = APIRouter(prefix="/api/v1/call-recorder", tags=["Call recorder"])


def key_ok(given: Optional[str]) -> bool:
    expected = (os.environ.get("CALL_RECORDER_API_KEY") or "").strip()
    return len(expected) >= 24 and hmac.compare_digest(expected, (given or "").strip())


@router.get("/numbers")
def numbers(request: Request, x_api_key: Optional[str] = Header(None), db: Session = Depends(get_db)):
    """
    Everyone on the Applications tab: phone (+91…), the last 10 digits, their
    WhatsApp name, and when they first wrote. New applications appear here as
    they come in, so the app should fetch again regularly (every 15 minutes is plenty).
    """
    from src.services import audit
    ok = key_ok(x_api_key)
    audit.write(SimpleNamespace(email="call-recorder-app", role=None), "GET", "/api/v1/call-recorder/numbers",
                200 if ok else 401, None)
    if not ok:
        raise HTTPException(status_code=401, detail="Missing or wrong API key.")
    contacts = applications.recorder_contacts(db)
    logger.info(f"call_recorder event=NUMBERS count={len(contacts)}")
    return {"as_of": datetime.now(timezone.utc).isoformat(), "count": len(contacts), "numbers": contacts}
