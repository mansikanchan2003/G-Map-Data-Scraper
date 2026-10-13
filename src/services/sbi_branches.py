"""
SBI branches whose areas are targeted for CSP operators.

A branch list from the bank names branches by code. Each branch's PIN code
becomes a target location like any other, so it is scraped with the usual
jobs; the branch itself is kept beside it so the Configuration page can show
these PINs in a section of their own, with the branches each one serves.
"""
from typing import Dict, List, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from src.config import settings
from src.models import Category, Job, Location, SbiBranch
from src.services import config_loader
from src.utils.logging import logger

FIELDS = ("branch_name", "ifsc", "pincode", "town", "district", "state", "tehsil",
          "address", "circle", "network", "module", "region", "note")


def _location_for(db: Session, branch: SbiBranch) -> Dict:
    """The branch PIN's location, created from the PIN code if it is new."""
    location = db.query(Location).filter(Location.pincode == branch.pincode).first()
    if location:
        return {"location": location, "created": False}

    coords = config_loader._geocode_pin(branch.pincode, branch.state)
    if isinstance(coords, str):
        return {"error": coords}
    lat, lng = coords
    location = Location(
        location_id=config_loader.generate_location_id(lat, lng, branch.pincode),
        pincode=branch.pincode,
        latitude=lat,
        longitude=lng,
        radius_km=settings.default_radius_km,
        district=branch.district,
        state=branch.state,
        tehsil=branch.tehsil or branch.town,
        anchor_name=branch.town,
        pin_basis="SBI branch PIN",
        coordinate_precision="pincode",
        source_dataset="sbi_branches",
    )
    db.add(location)
    db.flush()
    return {"location": location, "created": True}


def add_branches(db: Session, rows: List[dict], generate_jobs: bool = True) -> Dict:
    """
    Saves the branches and makes sure each one's PIN is a target location.

    A branch is kept even when its PIN cannot be placed on the map, so it
    still shows; the reason is reported and no jobs are made for it.
    """
    from src.services.custom_target import generate_jobs_for

    saved, locations, created, problems = 0, {}, [], []
    for row in rows:
        code = str(row["branch_code"]).strip()
        branch = db.get(SbiBranch, code) or SbiBranch(branch_code=code)
        for key in FIELDS:
            value = row.get(key)
            if value is not None:
                setattr(branch, key, str(value).strip() or None)
        db.add(branch)
        saved += 1

        found = _location_for(db, branch)
        if "error" in found:
            problems.append({"branch_code": code, "pincode": branch.pincode, "error": found["error"]})
            continue
        locations[found["location"].location_id] = found["location"]
        if found["created"]:
            created.append(branch.pincode)

    db.commit()
    jobs = {"created": 0, "existing": 0}
    if generate_jobs and locations:
        result = generate_jobs_for(db, list(locations.values()), db.query(Category).all())
        jobs = {"created": result.get("jobs_created", result.get("created", 0)),
                "existing": result.get("jobs_existing", result.get("existing", 0))}
    logger.info(f"sbi_branches event=BRANCHES_ADDED saved={saved} new_pins={created} problems={len(problems)}")
    return {"branches_saved": saved, "pins_created": created, "jobs": jobs, "problems": problems}


def branch_pins(db: Session) -> List[Dict]:
    """Each branch PIN with its location, its branches and how far its scraping has got."""
    branches = db.query(SbiBranch).order_by(SbiBranch.pincode, SbiBranch.branch_code).all()
    pins: Dict[str, Dict] = {}
    for b in branches:
        entry = pins.setdefault(b.pincode, {"pincode": b.pincode, "location": None, "branches": [],
                                            "jobs": {"total": 0, "completed": 0, "pending": 0, "failed": 0},
                                            "businesses_saved": 0})
        entry["branches"].append({k: getattr(b, k) for k in ("branch_code",) + FIELDS})

    if not pins:
        return []
    for loc in db.query(Location).filter(Location.pincode.in_(list(pins))).all():
        pins[loc.pincode]["location"] = {
            "location_id": loc.location_id, "anchor_name": loc.anchor_name, "district": loc.district,
            "state": loc.state, "tehsil": loc.tehsil, "latitude": loc.latitude, "longitude": loc.longitude,
            "radius_km": loc.radius_km,
        }
    counts = (
        db.query(Location.pincode, Job.status, func.count(Job.job_id), func.coalesce(func.sum(Job.businesses_saved), 0))
        .join(Job, Job.location_id == Location.location_id)
        .filter(Location.pincode.in_(list(pins)))
        .group_by(Location.pincode, Job.status)
        .all()
    )
    for pincode, status, n, saved in counts:
        jobs = pins[pincode]["jobs"]
        jobs["total"] += n
        key = (status or "").lower()
        if key in jobs:
            jobs[key] += n
        pins[pincode]["businesses_saved"] += int(saved or 0)
    return list(pins.values())
