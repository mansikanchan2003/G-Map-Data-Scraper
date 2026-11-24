from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_
from src.database import get_db
from src.models import Business, Job, Location
from src.models.business import CONTACTABLE, HIRING_FOR, NOT_PARTNER, hiring_flag
from src.schemas.common import Pagination
from src.schemas.business import BusinessPublicResponse
from typing import Optional
from datetime import datetime

router = APIRouter(prefix="/api/v1/businesses", tags=["Businesses"])

def filtered(query, hiring_for: Optional[str] = None, state: Optional[str] = None, search: Optional[str] = None):
    """
    The Business Data tab's filters, shared with its export so a download holds
    exactly the rows the filters show: who it was found for, the state, and words.
    """
    if hiring_for:
        if hiring_for not in HIRING_FOR:
            raise HTTPException(status_code=400, detail=f"Type must be one of: {', '.join(HIRING_FOR)}.")
        query = query.filter(hiring_flag(hiring_for).is_(True))
    if state:
        query = query.filter(Business.state.ilike(state.strip()))
    if search:
        # Every word must appear somewhere: the name, the kind of business, the
        # place or the phone. "Kiosk Agra" finds kiosks in Agra.
        for word in search.split():
            term = f"%{word}%"
            query = query.filter(or_(
                Business.name.ilike(term), Business.category.ilike(term), Business.address.ilike(term),
                Business.district.ilike(term), Business.tehsil.ilike(term), Business.state.ilike(term),
                Business.phone.ilike(term),
            ))
    return query


@router.get("", response_model=Pagination[BusinessPublicResponse])
def get_businesses(
    page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=500),
    category: Optional[str] = None,
    district: Optional[str] = None,
    state: Optional[str] = None,
    pincode: Optional[str] = None,
    is_valid: Optional[bool] = None,
    search: Optional[str] = None,
    hiring_for: Optional[str] = None,
    since: Optional[datetime] = None,
    sort_by: str = Query("discovered_at", pattern="^(discovered_at|name|distance_km)$"),
    sort_order: str = Query("desc", pattern="^(asc|desc)$"),
    db: Session = Depends(get_db)
):
    # Rows still waiting for their email to be looked up are not shown.
    # Partner organisations have their own tab.
    query = db.query(Business).filter(CONTACTABLE, NOT_PARTNER)
    
    if category:
        query = query.filter(Business.category == category)
    if district:
        query = query.filter(Business.district == district)
    query = filtered(query, hiring_for, state, search)
    if is_valid is not None:
        query = query.filter(Business.is_valid == is_valid)
    if since:
        query = query.filter(Business.discovered_at >= since)
    if pincode:
        # Join with jobs and locations to filter by pincode
        query = query.join(Job, Business.job_id == Job.job_id)\
                     .join(Location, Job.location_id == Location.location_id)\
                     .filter(Location.pincode == pincode)
                     
    # Sorting
    sort_col = getattr(Business, sort_by)
    if sort_order == "desc":
        query = query.order_by(sort_col.desc())
    else:
        query = query.order_by(sort_col.asc())
        
    total = query.count()
    items = query.offset((page - 1) * page_size).limit(page_size).all()
    from src.services import business_pin
    by_job = business_pin.searched(db, [b.job_id for b in items])
    total_pages = (total + page_size - 1) // page_size
    
    return {
        "items": [BusinessPublicResponse.from_orm_business(b, business_pin.pin_for(b, by_job)) for b in items],
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": total_pages,
        "has_next": page < total_pages,
        "has_prev": page > 1
    }

@router.get("/types")
def business_types(db: Session = Depends(get_db)):
    """How many businesses were found for each hiring type, for the Type filter."""
    base = db.query(Business).filter(CONTACTABLE, NOT_PARTNER)
    return [{"type": key, "label": label, "count": base.filter(hiring_flag(key).is_(True)).count()}
            for key, (_, label) in HIRING_FOR.items()]


@router.get("/states")
def business_states(db: Session = Depends(get_db)):
    """The states the shown businesses are in, with how many, most first: the State filter's choices."""
    from sqlalchemy import func
    rows = (db.query(Business.state, func.count(Business.business_id))
            .filter(CONTACTABLE, NOT_PARTNER, Business.state.isnot(None), Business.state != "")
            .group_by(Business.state).order_by(func.count(Business.business_id).desc()).all())
    return [{"state": s, "count": n} for s, n in rows]


@router.get("/dc-summary")
def dc_summary(days: int = Query(30, ge=7, le=180),
               hiring_for: str = Query("DC", pattern="^(DC|CSP_NEAR_DC)$"),
               db: Session = Depends(get_db)):
    """
    The DC Data tab (Biswajit Sir, 23 Nov 2026): the businesses found for District
    Coordinators, or since 24 Nov 2026 the CSPs near DCs (hiring_for), counted by state,
    district and category, how many each day, and how many can be reached by phone,
    email or website. The rows themselves come from the list endpoint with the same
    hiring_for. `totals` has both kinds' counts, for the tab's switch.
    """
    from datetime import timedelta, timezone
    from sqlalchemy import func

    shown = db.query(Business).filter(CONTACTABLE, NOT_PARTNER)
    totals = {key: shown.filter(hiring_flag(key).is_(True)).count() for key in ("DC", "CSP_NEAR_DC")}
    base = shown.filter(hiring_flag(hiring_for).is_(True))
    now = datetime.now(timezone.utc)
    has = lambda col: and_(col.isnot(None), col != "")

    def grouped(*cols, limit=None):
        q = (base.with_entities(*cols, func.count(Business.business_id))
             .group_by(*cols).order_by(func.count(Business.business_id).desc()))
        return q.limit(limit).all() if limit else q.all()

    since = (now - timedelta(days=days - 1)).replace(hour=0, minute=0, second=0, microsecond=0)
    per_day = dict(base.filter(Business.discovered_at >= since)
                   .with_entities(func.date(Business.discovered_at), func.count(Business.business_id))
                   .group_by(func.date(Business.discovered_at)).all())
    per_day = {str(d): n for d, n in per_day.items()}

    by_state: dict = {}
    for state, district, n in grouped(Business.state, Business.district):
        entry = by_state.setdefault(state or "Unknown", {"state": state or "Unknown", "count": 0, "districts": []})
        entry["count"] += n
        entry["districts"].append({"district": district or "Unknown", "count": n})

    last = base.with_entities(func.max(Business.discovered_at)).scalar()
    return {
        "hiring_for": hiring_for,
        "totals": totals,
        "total": totals[hiring_for],
        "last_7_days": base.filter(Business.discovered_at >= now - timedelta(days=7)).count(),
        "today": base.filter(Business.discovered_at >= now.replace(hour=0, minute=0, second=0, microsecond=0)).count(),
        "last_found_at": last.isoformat() if last else None,
        "with_phone": base.filter(has(Business.phone)).count(),
        "with_email": base.filter(has(Business.email)).count(),
        "with_website": base.filter(has(Business.website)).count(),
        "states": sorted(by_state.values(), key=lambda s: -s["count"]),
        "categories": [{"category": c or "General", "count": n} for c, n in grouped(Business.category, limit=12)],
        "daily": [{"date": str((since + timedelta(days=i)).date()),
                   "count": per_day.get(str((since + timedelta(days=i)).date()), 0)} for i in range(days)],
    }


@router.get("/{business_id}", response_model=BusinessPublicResponse)
def get_business(business_id: str, db: Session = Depends(get_db)):
    biz = db.query(Business).filter(Business.business_id == business_id).first()
    if not biz:
        raise HTTPException(status_code=404, detail="Business not found")
    return BusinessPublicResponse.from_orm_business(biz)
