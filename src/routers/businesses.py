from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import or_
from src.database import get_db
from src.models import Business, Job, Location
from src.schemas.common import Pagination
from src.schemas.business import BusinessResponse
from typing import Optional
from datetime import datetime

router = APIRouter(prefix="/api/v1/businesses", tags=["Businesses"])

@router.get("", response_model=Pagination[BusinessResponse])
def get_businesses(
    page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=500),
    category: Optional[str] = None,
    district: Optional[str] = None,
    state: Optional[str] = None,
    pincode: Optional[str] = None,
    is_valid: Optional[bool] = None,
    search: Optional[str] = None,
    since: Optional[datetime] = None,
    sort_by: str = Query("discovered_at", pattern="^(discovered_at|name|distance_km)$"),
    sort_order: str = Query("desc", pattern="^(asc|desc)$"),
    db: Session = Depends(get_db)
):
    query = db.query(Business)
    
    if category:
        query = query.filter(Business.category == category)
    if district:
        query = query.filter(Business.district == district)
    if state:
        query = query.filter(Business.state == state)
    if is_valid is not None:
        query = query.filter(Business.is_valid == is_valid)
    if since:
        query = query.filter(Business.discovered_at >= since)
    if search:
        search_term = f"%{search}%"
        query = query.filter(
            or_(
                Business.name.ilike(search_term),
                Business.address.ilike(search_term)
            )
        )
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
    total_pages = (total + page_size - 1) // page_size
    
    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": total_pages,
        "has_next": page < total_pages,
        "has_prev": page > 1
    }

@router.get("/{business_id}", response_model=BusinessResponse)
def get_business(business_id: str, db: Session = Depends(get_db)):
    biz = db.query(Business).filter(Business.business_id == business_id).first()
    if not biz:
        raise HTTPException(status_code=404, detail="Business not found")
    return biz
