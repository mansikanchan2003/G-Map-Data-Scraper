"""
Ad-hoc discovery targets.

The spreadsheets define the standing job matrix, but a user should not be
limited to it: they may want one town and two categories that were never in
the source files. Anything created here joins the same locations / categories /
jobs tables, so it runs, deduplicates and reports exactly like the rest.
"""
import hashlib
import logging
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from src.config import settings
from src.models import Category, Job, Location
from src.services.discovery_engine import GoogleMapsDiscoveryEngine
from src.services.job_manager import build_search_query
from src.services.geo_validator import is_valid_coordinate

logger = logging.getLogger("gmap_scraper.custom_target")

CUSTOM_DATASET = "user_defined"


def _short_id(*parts: str) -> str:
    return hashlib.sha256("".join(str(p) for p in parts).encode("utf-8")).hexdigest()[:12]


def ensure_category(db: Session, name: str) -> Optional[Category]:
    """Find or create a category. Names are matched case-insensitively."""
    name = (name or "").strip()
    if not name:
        return None

    existing = db.query(Category).filter(
        Category.category_name.ilike(name)
    ).first()
    if existing:
        return existing

    category = Category(category_id=_short_id("cat", name.lower()), category_name=name)
    db.add(category)
    db.flush()
    logger.info(f"custom_target event=CATEGORY_CREATED name={name}")
    return category


def ensure_location(
    db: Session,
    place: str,
    latitude: Optional[float] = None,
    longitude: Optional[float] = None,
    radius_km: Optional[float] = None,
    engine: Optional[GoogleMapsDiscoveryEngine] = None,
    state: Optional[str] = None,
    district: Optional[str] = None,
    tehsil: Optional[str] = None,
) -> Dict:
    """
    Find or create a location for a typed place.

    Coordinates may be supplied directly; otherwise the place is resolved
    through Google Maps, because a job cannot be built without them.

    Every business discovered here inherits this row's state, district and
    tehsil, so a location saved without them yields businesses that cannot be
    filtered by geography afterwards. The caller's values win; Maps fills in
    the state only where it actually named one.

    Returns {"location": Location} or {"error": "..."}.
    """
    place = (place or "").strip()
    if not place:
        return {"error": "Place is required"}

    # An existing pincode or anchor name should be reused rather than
    # duplicated, so repeated runs do not fragment the dataset.
    existing = db.query(Location).filter(
        (Location.pincode == place) | (Location.anchor_name.ilike(place))
    ).first()
    if existing:
        return {"location": existing, "reused": True}

    resolved_pincode = None
    if latitude is None or longitude is None:
        owns_engine = engine is None
        engine = engine or GoogleMapsDiscoveryEngine(headless=settings.browser_headless)
        try:
            resolved = engine.resolve_place(place)
        finally:
            if owns_engine:
                engine.close()

        if not resolved:
            return {"error": f"Could not find '{place}' on Google Maps. "
                             f"Try a more specific name, or enter coordinates."}
        latitude = resolved["latitude"]
        longitude = resolved["longitude"]
        state = state or resolved.get("state")
        resolved_pincode = resolved.get("pincode")

    if not is_valid_coordinate(latitude, longitude):
        return {"error": f"Invalid coordinates for '{place}'"}

    location = Location(
        location_id=_short_id("loc", place.lower()),
        # A typed town has no PIN of its own, but searching it may still have
        # landed on one, which beats recording "NOT FOUND".
        pincode=place if place.isdigit() else (resolved_pincode or "NOT FOUND"),
        latitude=float(latitude),
        longitude=float(longitude),
        radius_km=float(radius_km or settings.default_radius_km),
        district=(district or "").strip() or None,
        state=(state or "").strip() or None,
        tehsil=(tehsil or "").strip() or None,
        anchor_name=place,
        source_dataset=CUSTOM_DATASET,
    )
    db.add(location)
    db.flush()
    logger.info(
        f"custom_target event=LOCATION_CREATED place={place} "
        f"lat={latitude} lng={longitude} radius={location.radius_km} "
        f"state={location.state or '-'} district={location.district or '-'}"
    )
    return {"location": location, "reused": False}


def generate_jobs_for(db: Session, locations: List[Location], categories: List[Category]) -> Dict:
    """
    Create the missing (location × category) jobs.

    A job that already exists is left alone whatever its state: recreating it
    would either duplicate work already done or reset a job mid-flight.
    """
    created, existing = 0, 0

    for loc in locations:
        for cat in categories:
            job_id = hashlib.sha256(
                f"{loc.location_id}{cat.category_id}".encode("utf-8")
            ).hexdigest()[:16]

            if db.query(Job).filter(Job.job_id == job_id).first():
                existing += 1
                continue

            db.add(Job(
                job_id=job_id,
                location_id=loc.location_id,
                category_id=cat.category_id,
                status="PENDING",
                search_query=build_search_query(cat.category_name, loc.latitude, loc.longitude),
                max_retries=settings.job_retry_limit,
            ))
            created += 1

    db.commit()
    logger.info(f"custom_target event=JOBS_GENERATED created={created} existing={existing}")
    return {"jobs_created": created, "jobs_existing": existing}
