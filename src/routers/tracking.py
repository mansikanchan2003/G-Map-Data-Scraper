"""
Click tracking for WhatsApp campaign links.

WhatsApp reports message delivery, never clicks on a link written in the
message body. A URL that is identical for every recipient also cannot say who
opened it. So each recipient is sent their own short link into this router,
which records the visit and forwards to the real destination.

Only requests that actually arrive here are recorded; nothing is inferred.
"""
import hashlib
import logging
import os
import uuid
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from src.database import get_db
from src.models.whatsapp import WhatsAppCampaignRecipient, WhatsAppLinkClick

router = APIRouter(tags=["Link Tracking"])
logger = logging.getLogger("gmap_scraper.link_tracking")

# Where an unknown or expired token goes, so a stale link is never a dead end.
FALLBACK_URL = os.environ.get(
    "CAMPAIGN_LINK_FALLBACK_URL", "https://kiosk.eko.in/"
)


def _hash_ip(request: Request) -> str:
    """
    Hash the caller's address rather than storing it.

    Enough to recognise repeated hits from the same source, without keeping a
    visitor's IP in the database.
    """
    forwarded = request.headers.get("x-forwarded-for", "")
    ip = forwarded.split(",")[0].strip() if forwarded else (
        request.client.host if request.client else ""
    )
    if not ip:
        return ""
    salt = os.environ.get("CAMPAIGN_LINK_HASH_SALT", "gmap-campaign")
    return hashlib.sha256(f"{salt}:{ip}".encode("utf-8")).hexdigest()


def _is_safe_target(url: str) -> bool:
    """Only ever redirect to an absolute http(s) URL."""
    try:
        parsed = urlparse(url)
        return parsed.scheme in ("http", "https") and bool(parsed.netloc)
    except Exception:
        return False


@router.get("/r/{token}")
def follow_campaign_link(token: str, request: Request, db: Session = Depends(get_db)):
    """
    Records a genuine click, then forwards to the campaign's destination.

    The redirect is issued even when recording fails: a tracking problem must
    never stop someone reaching the page they tapped.
    """
    recipient = (
        db.query(WhatsAppCampaignRecipient)
        .filter(WhatsAppCampaignRecipient.tracking_token == token)
        .first()
    )

    if not recipient:
        logger.warning(f"link_tracking event=UNKNOWN_TOKEN token={token[:8]}...")
        return RedirectResponse(FALLBACK_URL, status_code=302)

    target = os.environ.get("CAMPAIGN_LINK_TARGET_URL") or FALLBACK_URL
    if not _is_safe_target(target):
        target = FALLBACK_URL

    try:
        db.add(WhatsAppLinkClick(
            click_id=uuid.uuid4().hex,
            campaign_id=recipient.campaign_id,
            recipient_id=recipient.recipient_id,
            target_url=target,
            ip_hash=_hash_ip(request),
            user_agent=(request.headers.get("user-agent") or "")[:500],
        ))
        db.commit()
        logger.info(
            f"link_tracking event=LINK_CLICKED campaign_id={recipient.campaign_id} "
            f"recipient_id={recipient.recipient_id}"
        )
    except Exception:
        db.rollback()
        logger.exception("link_tracking event=CLICK_RECORD_FAILED")

    return RedirectResponse(target, status_code=302)
