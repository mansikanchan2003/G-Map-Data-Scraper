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
from urllib.parse import parse_qsl, urlencode, urlparse, urlsplit, urlunsplit

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


def _with_campaign_source(url: str, campaign_name: str = "") -> str:
    """
    Tag the destination so analytics can say the visit came from WhatsApp.

    The parameters go into the query, never the fragment: everything after
    "#" stays in the browser and is not sent to the destination's server, so
    a utm written there would be invisible to analytics and would also break
    the anchor it was appended to.

    Anything the configured URL already sets is left alone — a target that
    names its own source means it on purpose.
    """
    parts = urlsplit(url)
    existing = dict(parse_qsl(parts.query, keep_blank_values=True))

    defaults = {
        "utm_source": os.environ.get("CAMPAIGN_UTM_SOURCE", "WhatsApp Campaign"),
        "utm_medium": os.environ.get("CAMPAIGN_UTM_MEDIUM", "whatsapp"),
    }
    # The campaign's own name, so two campaigns to the same page stay apart.
    if campaign_name:
        defaults["utm_campaign"] = campaign_name

    for key, value in defaults.items():
        if value and key not in existing:
            existing[key] = value

    # quote_via leaves the fragment untouched, which is what carries #apply-now.
    return urlunsplit((
        parts.scheme, parts.netloc, parts.path,
        urlencode(existing), parts.fragment,
    ))


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

    target = os.environ.get("CAMPAIGN_LINK_TARGET_URL") or FALLBACK_URL
    if not _is_safe_target(target):
        target = FALLBACK_URL

    if not recipient:
        # An unknown token still belongs to someone who tapped a campaign
        # button: a deleted recipient, an old link, or the template's own
        # "{{1}}" opened by hand. Sending them to a bare home page loses both
        # the page they were promised and the fact that they came from
        # WhatsApp. Only the campaign name is unknown, so only that is left
        # out.
        logger.warning(f"link_tracking event=UNKNOWN_TOKEN token={token[:8]}...")
        return RedirectResponse(_with_campaign_source(target), status_code=302)

    campaign = recipient.campaign
    target = _with_campaign_source(target, campaign.name if campaign else "")

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
