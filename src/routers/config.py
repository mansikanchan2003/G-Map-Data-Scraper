from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from src.database import get_db
from src.services import config_loader
from src.config import settings
from src.models import Category, Job, Location
from src.schemas.common import Pagination
from src.schemas.location import LocationResponse
from src.schemas.category import CategoryResponse

router = APIRouter(prefix="/api/v1/config", tags=["Configuration"])

@router.post("/sync")
def sync_configuration(db: Session = Depends(get_db)):
    return config_loader.sync_config(db)

@router.get("/locations", response_model=Pagination[LocationResponse])
def get_locations(
    page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db)
):
    query = db.query(Location)
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

@router.get("/categories", response_model=Pagination[CategoryResponse])
def get_categories(
    page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db)
):
    query = db.query(Category)
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


class ResolvePlaceRequest(BaseModel):
    place: str = Field(..., min_length=1, max_length=200)


class LocationCreateRequest(BaseModel):
    """
    A target PIN the user adds by hand.

    State and district are required rather than optional: every business
    discovered here copies them, so a location saved without them yields rows
    that can never be filtered by geography. Maps names the state for a PIN
    code, but it never names the district — that is always the user's to give.
    """
    pincode: str = Field(..., min_length=1, max_length=10)
    state: str = Field(..., min_length=1, max_length=100)
    district: str = Field(..., min_length=1, max_length=100)
    tehsil: Optional[str] = Field(None, max_length=100)
    anchor_name: Optional[str] = Field(None, max_length=200)
    latitude: Optional[float] = Field(None, ge=-90, le=90)
    longitude: Optional[float] = Field(None, ge=-180, le=180)
    radius_km: Optional[float] = Field(None, gt=0, le=200)


@router.post("/locations/resolve")
def resolve_location(payload: ResolvePlaceRequest):
    """
    Look a place up on Maps without saving anything.

    This exists so the add-location form can be filled in for the user: it
    returns the coordinates, and the state and PIN where Maps stated them. The
    district is never returned, because Maps does not say it.
    """
    from src.services.discovery_engine import GoogleMapsDiscoveryEngine

    engine = GoogleMapsDiscoveryEngine(headless=settings.browser_headless)
    try:
        resolved = engine.resolve_place(payload.place)
    finally:
        engine.close()

    if not resolved:
        raise HTTPException(
            status_code=404,
            detail=f"Could not find '{payload.place}' on Google Maps. "
                   f"Try a PIN code or a more specific name.",
        )

    return {
        "place": payload.place,
        "latitude": resolved["latitude"],
        "longitude": resolved["longitude"],
        "resolved_name": resolved.get("resolved_name"),
        "state": resolved.get("state"),
        "pincode": resolved.get("pincode"),
        "radius_km": settings.default_radius_km,
    }


@router.post("/locations", response_model=LocationResponse, status_code=201)
def create_location(payload: LocationCreateRequest, db: Session = Depends(get_db)):
    """
    Add a target PIN, so the matrix can grow past the spreadsheets it started from.

    Coordinates may be given directly; otherwise the PIN or anchor name is
    resolved through Maps, because a job cannot be built without them.
    """
    from src.services.custom_target import ensure_location
    from src.services.discovery_engine import GoogleMapsDiscoveryEngine

    place = (payload.anchor_name or payload.pincode).strip()

    engine = None
    if payload.latitude is None or payload.longitude is None:
        engine = GoogleMapsDiscoveryEngine(headless=settings.browser_headless)
    try:
        result = ensure_location(
            db, place,
            latitude=payload.latitude, longitude=payload.longitude,
            radius_km=payload.radius_km, engine=engine,
            state=payload.state, district=payload.district, tehsil=payload.tehsil,
        )
    finally:
        if engine:
            engine.close()

    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])

    location = result["location"]

    # Reusing a row must not silently keep stale geography, and a PIN the user
    # typed is better evidence than one Maps guessed.
    if payload.pincode.strip():
        location.pincode = payload.pincode.strip()
    location.state = payload.state.strip()
    location.district = payload.district.strip()
    if payload.tehsil:
        location.tehsil = payload.tehsil.strip()
    if payload.anchor_name:
        location.anchor_name = payload.anchor_name.strip()

    db.commit()
    db.refresh(location)
    return location


@router.delete("/locations/{location_id}")
def delete_location(location_id: str, db: Session = Depends(get_db)):
    """
    Remove a target PIN.

    A location with jobs against it is kept: deleting it would orphan the
    businesses already discovered there. Those are cleared from the Jobs
    Monitor first.
    """
    location = db.query(Location).filter(Location.location_id == location_id).first()
    if not location:
        raise HTTPException(status_code=404, detail="Location not found")

    job_count = db.query(Job).filter(Job.location_id == location_id).count()
    if job_count:
        raise HTTPException(
            status_code=409,
            detail=f"'{location.anchor_name or location.pincode}' has {job_count} job(s) "
                   f"against it. Remove those jobs first.",
        )

    db.delete(location)
    db.commit()
    return {"status": "deleted", "location_id": location_id}
