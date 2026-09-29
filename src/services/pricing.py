"""
What a campaign costs.

Meta bills per template message **delivered**, not per message sent, and the
rate depends on the template's category and the recipient's country. Every
number this account sends to is Indian, so one rate card is enough; a second
country would mean keying these by calling code.

These rates are a local copy of a published card, so they can drift. The
authoritative figure is Meta's own pricing_analytics, which
`src.routers.whatsapp` exposes alongside these estimates — the estimate is
what makes a *per-campaign* number possible at all, since Meta reports by day
and category rather than by campaign.
"""
import os
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

# India, per delivered message, before tax. Effective 1 July 2026.
RATES_INR = {
    "MARKETING": Decimal("0.8631"),
    "MARKETING_LITE": Decimal("0.8631"),
    "UTILITY": Decimal("0.1150"),
    "AUTHENTICATION": Decimal("0.1150"),
    # Free until 1 October 2026, and billed per message from then on.
    "SERVICE": Decimal("0.1150"),
}

DEFAULT_CATEGORY = "MARKETING"
CURRENCY = "INR"

# Indian GST on the Meta invoice. Overridable because it is a tax rate, not a
# property of WhatsApp, and it is the part most likely to change first.
GST_RATE = Decimal(os.environ.get("WHATSAPP_GST_RATE", "0.18"))


def rate_for(category: Optional[str]) -> Decimal:
    """Per-message rate for a template category, falling back to marketing."""
    return RATES_INR.get((category or "").upper(), RATES_INR[DEFAULT_CATEGORY])


def _money(value: Decimal) -> float:
    """Round to paise. Floats are fine to hand out; the arithmetic was exact."""
    return float(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def estimate(category: Optional[str], delivered: int) -> dict:
    """
    Cost of `delivered` messages of this category.

    Returns the pre-tax amount, the GST on it and the total, all in INR.
    """
    delivered = max(0, delivered or 0)
    net = rate_for(category) * delivered
    tax = net * GST_RATE
    return {
        "currency": CURRENCY,
        "rate": float(rate_for(category)),
        "billable_messages": delivered,
        "net": _money(net),
        "gst": _money(tax),
        "total": _money(net + tax),
    }
