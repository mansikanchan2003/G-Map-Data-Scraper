"""
Maker-checker for large campaigns (the standards review, 1 Nov 2026).

A campaign that would message APPROVAL_MIN people or more is not sent when
it is created: it waits as AWAITING_APPROVAL until a second person approves
it. The person who launched it cannot approve it, whatever their role, so no
one can send a large campaign alone. What is approved is exactly the
campaign as created: its recipients were fixed then and cannot change.
The team is emailed when one is waiting. Smaller campaigns start at once.
"""
import logging
import os
from datetime import datetime, timezone
from typing import Optional

from src.models.whatsapp import WhatsAppCampaign

logger = logging.getLogger("gmap_scraper.campaign_approval")

AWAITING = "AWAITING_APPROVAL"
DEFAULT_MIN = 200


def approval_min() -> int:
    """Campaigns this large wait for a second person; 0 sends every campaign at once."""
    try:
        return max(0, int(os.environ.get("CAMPAIGN_APPROVAL_MIN") or DEFAULT_MIN))
    except ValueError:
        return DEFAULT_MIN


def needs_approval(campaign: WhatsAppCampaign) -> bool:
    n = approval_min()
    return bool(n) and (campaign.pending_count or 0) >= n


class NotAllowed(Exception):
    """Why this person cannot decide on this campaign, in words for them."""


def _check(campaign: WhatsAppCampaign, by: str) -> None:
    if campaign.status != AWAITING:
        raise NotAllowed(f"This campaign is {campaign.status.lower().replace('_', ' ')}, not waiting for approval.")
    if campaign.created_by and campaign.created_by.lower() == (by or "").lower():
        raise NotAllowed("You launched this campaign, so someone else has to approve it.")


def hold(campaign: WhatsAppCampaign, by: str) -> None:
    campaign.status = AWAITING
    logger.info(f"campaign_approval event=AWAITING campaign_id={campaign.campaign_id} by={by} "
                f"recipients={campaign.pending_count}")


def approve(campaign: WhatsAppCampaign, by: str, note: Optional[str] = None) -> None:
    _check(campaign, by)
    campaign.status = "PENDING"
    campaign.approved_by, campaign.approved_at = by, datetime.now(timezone.utc)
    campaign.review_note = (note or "").strip()[:500] or None
    logger.info(f"campaign_approval event=APPROVED campaign_id={campaign.campaign_id} by={by}")


def reject(campaign: WhatsAppCampaign, by: str, reason: str) -> None:
    _check(campaign, by)
    campaign.status = "CANCELLED"
    campaign.approved_by, campaign.approved_at = by, datetime.now(timezone.utc)
    campaign.review_note = f"Rejected: {reason.strip()}"[:500]
    campaign.completed_at = datetime.now(timezone.utc)
    logger.info(f"campaign_approval event=REJECTED campaign_id={campaign.campaign_id} by={by}")


def email_team(campaign_name: str, recipients: int, by: str, url: str) -> None:
    """Tell the admin and the team a campaign is waiting for a second person."""
    from src.services import auth_service, notifier
    notifier.notify_team(
        auth_service.BOOTSTRAP_ADMIN,
        f"AutoGMap: campaign waiting for approval — {campaign_name}",
        f"{by} launched “{campaign_name}” to {recipients} people. Campaigns this large need a second person "
        f"to approve them before anything is sent.\n\nOpen it to approve or reject: {url}",
    )
