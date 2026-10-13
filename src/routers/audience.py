"""
Campaign audience selection.

Picking who a WhatsApp campaign goes to is a decision about geography and
history: which state / district / tehsil, how many, and whether people already
contacted should be reached again. Those questions are answered here so the
campaign builder receives a finished contact list rather than a raw export.
"""
import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import and_, func, or_
from sqlalchemy.orm import Session

from src.database import get_db
from src.models import Business
from src.models.whatsapp import WhatsAppCampaignRecipient
from src.services.whatsapp_normalizer import WhatsAppNormalizer

router = APIRouter(prefix="/api/v1/whatsapp/audience", tags=["Campaign Audience"])
logger = logging.getLogger("gmap_scraper.audience")

ALL = "All"

# Recipient statuses that mean a message reached Meta and was not refused.
CONTACTED_STATUSES = ("SENT", "DELIVERED", "READ")


class Place(BaseModel):
    """A district or tehsil, named with the levels above it: names repeat across states."""
    state: Optional[str] = None
    district: Optional[str] = None
    tehsil: Optional[str] = None


class AudienceFilters(BaseModel):
    # Any number of each. A district narrows only its own state, and a tehsil
    # only its own district: Gujarat and Punjab with Rajkot picked is Rajkot
    # and the whole of Punjab, not Rajkot alone.
    states: List[str] = Field(default_factory=list)
    districts: List[Place] = Field(default_factory=list)
    tehsils: List[Place] = Field(default_factory=list)
    # One of each, as the picker sent before it took several. Still read, so
    # a page loaded before the change keeps working.
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
    # The levels above, so the same district name in two states stays two options.
    state: Optional[str] = None
    district: Optional[str] = None


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


def _picked(value: Optional[str]) -> Optional[str]:
    return value if value and value != ALL else None


def _selection(f: AudienceFilters):
    """The picked states, (state, district) pairs and (state, district, tehsil) triples."""
    states = {s for s in f.states if _picked(s)}
    districts = {(p.state, p.district) for p in f.districts if _picked(p.district)}
    tehsils = {(p.state, p.district, p.tehsil) for p in f.tehsils if _picked(p.tehsil)}
    state, district, tehsil = _picked(f.state), _picked(f.district), _picked(f.tehsil)
    if state:
        states.add(state)
    if district:
        districts.add((state, district))
    if tehsil:
        tehsils.add((state, district, tehsil))
    return states, districts, tehsils


def _place(state: Optional[str], district: Optional[str] = None, tehsil: Optional[str] = None):
    parts = [Business.state == state] if state else []
    if district:
        parts.append(Business.district == district)
    if tehsil:
        parts.append(Business.tehsil == tehsil)
    return and_(*parts)


def _geo_filtered(query, f: AudienceFilters):
    """
    Narrow a business query to the selected geography.

    Each pick at a lower level replaces its parent with itself: a state with
    districts picked in it means just those districts, a district with
    tehsils picked means just those tehsils. A parent with nothing picked
    under it is taken whole. Nothing picked at all is everywhere.
    """
    states, districts, tehsils = _selection(f)
    narrowed_districts = {(s, d) for s, d, _ in tehsils}
    narrowed_states = {s for s, _ in districts} | {s for s, _, _ in tehsils}

    conditions = [_place(s, d, t) for s, d, t in tehsils]
    conditions += [_place(s, d) for s, d in districts if (s, d) not in narrowed_districts]
    conditions += [_place(s) for s in states if s not in narrowed_states]
    if not conditions:
        return query
    return query.filter(or_(*conditions))


def _contacted_phones(db: Session) -> set:
    """
    Phone numbers a campaign has already reached.

    Every stage a sent message can reach counts. The webhook moves a
    recipient on from SENT to DELIVERED and READ, and a filter on "SENT"
    alone let exactly the people who certainly received a message back into
    the next audience. A recipient that was skipped, or that Meta reported
    as failed, never received anything, so excluding them would quietly
    shrink the audience.
    """
    rows = db.query(WhatsAppCampaignRecipient.phone).filter(
        WhatsAppCampaignRecipient.status.in_(CONTACTED_STATUSES)
    ).distinct().all()
    return {r[0] for r in rows if r[0]}


@router.get("/options", response_model=AudienceOptions)
def audience_options(
    states: List[str] = Query(default=[]),
    districts: List[str] = Query(default=[], description='Picked districts as "state|district"'),
    state: Optional[str] = ALL,
    district: Optional[str] = ALL,
    db: Session = Depends(get_db),
):
    """
    Geography available to choose from, with business counts.

    Districts are those of the picked states (every one when none is
    picked), and tehsils those of the picked districts, or else of the
    picked states. Each option names the levels above it.
    """
    picked_states = {s for s in states if _picked(s)}
    if _picked(state):
        picked_states.add(state)
    picked_districts = set()
    for key in districts:
        s, _, d = key.partition("|")
        if d:
            picked_districts.add((s or None, d))
    if _picked(district):
        picked_districts.add((_picked(state), district))

    def counts(columns, where):
        q = db.query(*columns, func.count(Business.business_id)).filter(columns[-1].isnot(None))
        if where is not None:
            q = q.filter(where)
        return q.group_by(*columns).order_by(func.count(Business.business_id).desc()).all()

    in_states = or_(*[Business.state == s for s in picked_states]) if picked_states else None
    in_districts = (or_(*[_place(s, d) for s, d in picked_districts]) if picked_districts else in_states)

    return AudienceOptions(
        states=[GeoOption(value=v, businesses=c) for v, c in counts([Business.state], None) if v],
        districts=[GeoOption(value=d, businesses=c, state=s)
                   for s, d, c in counts([Business.state, Business.district], in_states) if d],
        tehsils=[GeoOption(value=t, businesses=c, state=s, district=d)
                 for s, d, t, c in counts([Business.state, Business.district, Business.tehsil], in_districts) if t],
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
        # Where the business is and what it does travel with it: the template
        # agent reads them to pick the audience's language and to write to
        # the kind of business, and they fill the template's blanks.
        entry = {"name": b.name, "phone": canonical, "business_id": b.business_id,
                 "state": b.state, "district": b.district, "category": b.category}
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
        f"audience event=AUDIENCE_SELECTED selection={_selection(filters)} limit={filters.limit} "
        f"include_contacted={filters.include_already_contacted} sendable={summary['sendable']}"
    )
    return AudiencePreview(**summary, contacts=contacts)
