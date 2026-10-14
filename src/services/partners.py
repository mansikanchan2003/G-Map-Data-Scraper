"""
Organisations that help people find work or start a business, near SBI branches.

The people themselves are not collected. Their details on government portals
are published for welfare or transparency, not for outreach, mostly sit
behind logins, and WhatsApp requires a person's own opt-in before they are
messaged (the user's decision, 2026-10-14, to stay within the DPDP Act, the
IT Act and WhatsApp's policy). Instead the organisations that serve them —
RSETIs, NGOs, SHG federations, skill centres — are found through their public
Google Maps listings, like any business, so they can be asked to refer people
who want to become an SBI Customer Service Point. Those people then write to
us themselves.

The categories carry the persona PARTNER_PERSONA. Their jobs are made for SBI
branch PIN codes only (job_manager.generate_jobs leaves them out elsewhere),
and their results are kept out of Business Data and campaign audiences
(models.business.NOT_PARTNER) and shown on the Partner Organisations tab.
"""
import logging
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from src.models import Business, Category, Job, Location, SbiBranch
from src.models.business import CONTACTABLE, IS_PARTNER, PARTNER_PERSONA
from src.services.config_loader import generate_category_id

logger = logging.getLogger("gmap_scraper.partners")

# What Google Maps is searched for, near each branch PIN, and what each is.
PARTNER_CATEGORIES = [
    ("Rural Self Employment Training Institute",
     "RSETIs train rural youth to start businesses; many are sponsored by SBI"),
    ("Non-governmental organization", "NGOs running livelihood, skills and placement programmes"),
    ("Self help group", "SHGs and their federations, which reach women entrepreneurs in every village"),
    ("Skill development center", "PMKVY and DDU-GKY training centres, whose trainees look for work"),
    ("District Industries Centre", "Where people apply for loans to start a business"),
    ("Common Service Centre", "Village-level entrepreneurs already running a service point"),
    ("Block Development Office", "Block offices, where the rural livelihood mission works with SHGs"),
]


def ensure_categories(db: Session) -> List[Category]:
    """The partner categories, created on first use and marked with their persona."""
    out = []
    for name, _why in PARTNER_CATEGORIES:
        cat = db.query(Category).filter(Category.category_name == name).first()
        if cat is None:
            cat = Category(category_id=generate_category_id(name), category_name=name, persona=PARTNER_PERSONA)
            db.add(cat)
        elif cat.persona != PARTNER_PERSONA:
            cat.persona = PARTNER_PERSONA
        out.append(cat)
    db.commit()
    return out


def branch_locations(db: Session) -> List[Location]:
    pins = [p for (p,) in db.query(SbiBranch.pincode).distinct().all()]
    return db.query(Location).filter(Location.pincode.in_(pins)).all() if pins else []


def ensure_jobs(db: Session) -> Dict:
    """Make sure every branch PIN has a job for every partner category."""
    from src.services.custom_target import generate_jobs_for

    categories = ensure_categories(db)
    locations = branch_locations(db)
    if not locations:
        return {"created": 0, "existing": 0}
    result = generate_jobs_for(db, locations, categories)
    return {"created": result["jobs_created"], "existing": result["jobs_existing"]}


def list_partners(db: Session, kind: Optional[str] = None, branch: Optional[str] = None,
                  q: Optional[str] = None) -> Dict:
    """Every partner organisation found, with the branch whose PIN it was found at."""
    branches: Dict[str, List[SbiBranch]] = {}
    for b in db.query(SbiBranch).all():
        branches.setdefault(b.pincode, []).append(b)

    query = (db.query(Business, Location.pincode)
             .join(Job, Job.job_id == Business.job_id)
             .join(Location, Location.location_id == Job.location_id)
             .filter(IS_PARTNER, CONTACTABLE, Location.pincode.in_(list(branches) or [""])))
    if kind:
        query = query.filter(Business.category == kind)
    if branch:
        pins = [p for p, bs in branches.items() if any(b.branch_code == branch for b in bs)]
        query = query.filter(Location.pincode.in_(pins or [""]))
    if q and q.strip():
        like = f"%{q.strip()}%"
        query = query.filter(Business.name.ilike(like) | Business.address.ilike(like))

    rows = []
    for biz, pin in query.order_by(Business.category, Business.name).all():
        near = branches.get(pin, [])
        rows.append({
            "business_id": biz.business_id, "name": biz.name, "type": biz.category,
            "phone": biz.phone, "email": biz.email, "website": biz.website,
            "address": biz.address, "district": biz.district, "state": biz.state,
            "google_maps_url": biz.google_maps_url, "pincode": pin,
            "branches": [{"code": b.branch_code, "name": b.branch_name} for b in near],
            "discovered_at": biz.discovered_at,
        })

    # How far the scraping has got, so an empty list can say why.
    cats = [c for c in db.query(Category).filter(Category.persona == PARTNER_PERSONA).all()]
    jobs = (db.query(Job.status).join(Location, Location.location_id == Job.location_id)
            .filter(Job.category_id.in_([c.category_id for c in cats]),
                    Location.pincode.in_(list(branches) or [""])).all())
    progress = {"total": len(jobs), "done": sum(1 for (s,) in jobs if s in ("COMPLETED", "PARTIAL")),
                "pending": sum(1 for (s,) in jobs if s == "PENDING"),
                "failed": sum(1 for (s,) in jobs if s == "FAILED")}

    return {
        "partners": rows,
        "types": [{"value": n, "why": why} for n, why in PARTNER_CATEGORIES],
        "branches": sorted(({"code": b.branch_code, "name": b.branch_name, "pincode": b.pincode}
                            for bs in branches.values() for b in bs), key=lambda b: b["name"]),
        "progress": progress,
    }
