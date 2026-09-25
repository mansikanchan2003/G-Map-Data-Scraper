"""
Campaign audience selection.

Picking who a WhatsApp campaign goes to is a decision about geography and
history: which state / district / tehsil, how many, and whether people already
contacted should be reached again. Those questions are answered here so the
campaign builder receives a finished contact list rather than a raw export.
"""
import logging
from typing import List, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from src.database import get_db
from src.models import Business
from src.models.whatsapp import WhatsAppCampaignRecipient
from src.services.whatsapp_normalizer import WhatsAppNormalizer

router = APIRouter(prefix="/api/v1/whatsapp/audience", tags=["Campaign Audience"])
logger = logging.getLogger("gmap_scraper.audience")

ALL = "All"


class AudienceFilters(BaseModel):
    state: Optional[str] = ALL
    district: Optional[str] = ALL
    tehsil: Optional[str] = ALL
    # How many contacts to take. None means every match.
    limit: Optional[int] = Field(default=None, ge=1, le=100000)
    # Whether people who already received a campaign message may be included.
    include_already_contacted: bool = False


class GeoOption(BaseModel):
    value: str
    businesses: int


class AudienceOptions(BaseModel):
    states: List[GeoOption]
    districts: List[GeoOption]
    tehsils: List[GeoOption]


class AudienceSummary(BaseModel):
    """What the chosen filters actually add up to."""
    total_businesses: int
    with_phone: int
    already_contacted: int
    never_contacted: int
    sendable: int          # after the contacted rule and the limit
    limit_applied: Optional[int] = None


class AudiencePreview(AudienceSummary):
    contacts: List[dict] = []


def _geo_filtered(query, f: AudienceFilters):
    """Narrow a business query to the selected geography."""
    if f.state and f.state != ALL:
        query = query.filter(Business.state == f.state)
    if f.district and f.district != ALL:
        query = query.filter(Business.district == f.district)
    if f.tehsil and f.tehsil != ALL:
        query = query.filter(Business.tehsil == f.tehsil)
    return query


def _contacted_phones(db: Session) -> set:
    """
    Phone numbers a campaign has already reached.

    Only SENT counts: a recipient that was skipped or failed never received
    anything, so excluding them would quietly shrink the audience.
    """
    rows = db.query(WhatsAppCampaignRecipient.phone).filter(
        WhatsAppCampaignRecipient.status == "SENT"
    ).distinct().all()
    return {r[0] for r in rows if r[0]}


@router.get("/options", response_model=AudienceOptions)
def audience_options(
    state: Optional[str] = ALL,
    district: Optional[str] = ALL,
    db: Session = Depends(get_db),
):
    """
    Geography available to choose from, with business counts.

    Districts and tehsils narrow to the level above them, so the three
    dropdowns behave as a cascade.
    """
    def counts(column, filters: AudienceFilters):
        q = db.query(column, func.count(Business.business_id)).filter(column.isnot(None))
        q = _geo_filtered(q, filters)
        rows = q.group_by(column).order_by(func.count(Business.business_id).desc()).all()
        return [GeoOption(value=v, businesses=c) for v, c in rows if v]

    return AudienceOptions(
        states=counts(Business.state, AudienceFilters()),
        districts=counts(Business.district, AudienceFilters(state=state)),
        tehsils=counts(Business.tehsil, AudienceFilters(state=state, district=district)),
    )


def _build(db: Session, f: AudienceFilters, with_contacts: bool):
    base = _geo_filtered(db.query(Business), f)

    total = base.count()
    with_phone_q = base.filter(Business.phone.isnot(None), Business.phone != "")
    rows = with_phone_q.order_by(Business.discovered_at.desc()).all()

    contacted = _contacted_phones(db)

    # Normalise before comparing: a business row may hold "09876543210" while
    # the campaign recorded "+919876543210" for the same person.
    seen = set()
    never, already = [], []
    for b in rows:
        canonical, error = WhatsAppNormalizer.normalize_phone(b.phone)
        if error or not canonical or canonical in seen:
            continue
        seen.add(canonical)
        entry = {"name": b.name, "phone": canonical, "business_id": b.business_id}
        (already if canonical in contacted else never).append(entry)

    pool = (never + already) if f.include_already_contacted else never
    limited = pool[: f.limit] if f.limit else pool

    summary = dict(
        total_businesses=total,
        with_phone=len(seen),
        already_contacted=len(already),
        never_contacted=len(never),
        sendable=len(limited),
        limit_applied=f.limit,
    )
    return summary, limited


@router.post("/summary", response_model=AudienceSummary)
def audience_summary(filters: AudienceFilters, db: Session = Depends(get_db)):
    """Counts for the current selection, without building the contact list."""
    summary, _ = _build(db, filters, with_contacts=False)
    return AudienceSummary(**summary)


@router.post("/preview", response_model=AudiencePreview)
def audience_preview(filters: AudienceFilters, db: Session = Depends(get_db)):
    """The contacts a campaign would be created with, ready to hand over."""
    summary, contacts = _build(db, filters, with_contacts=True)
    logger.info(
        f"audience event=AUDIENCE_SELECTED state={filters.state} district={filters.district} "
        f"tehsil={filters.tehsil} limit={filters.limit} "
        f"include_contacted={filters.include_already_contacted} sendable={summary['sendable']}"
    )
    return AudiencePreview(**summary, contacts=contacts)
