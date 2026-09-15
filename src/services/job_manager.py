import hashlib
import json
import urllib.parse
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
from sqlalchemy.orm import Session
from src.models import Location, Category, Job, Business
from src.services.discovery_engine import discovery_engine, build_search_url
from src.services.normalizer import normalize_business_record
from src.services.geo_validator import validate_geo_distance
from src.services.deduplicator import generate_dedup_key, generate_business_id
from src.utils.logging import logger

def generate_job_id(location_id: str, category_id: str) -> str:
    s = f"{location_id}{category_id}".encode('utf-8')
    return hashlib.sha256(s).hexdigest()[:16]

def build_search_query(category_name: str, latitude: float, longitude: float) -> str:
    query = urllib.parse.quote(category_name)
    return f"https://www.google.com/maps/search/{query}/@{latitude},{longitude},12z"

def generate_jobs(db: Session) -> dict:
    logger.info("Starting job generation...")
    
    locations = db.query(Location).all()
    categories = db.query(Category).all()
    
    if not locations or not categories:
        logger.warning("Locations or categories are empty. Cannot generate jobs.")
        return {"jobs_created": 0, "jobs_existing": 0, "total_jobs": 0, "message": "No locations or categories found."}

    existing_jobs_count = db.query(Job).count()
    jobs_created = 0
    
    existing_job_ids = {job.job_id for job in db.query(Job.job_id).all()}
    new_jobs = []
    
    for loc in locations:
        for cat in categories:
            job_id = generate_job_id(loc.location_id, cat.category_id)
            
            if job_id not in existing_job_ids:
                search_query = build_search_url(cat.category_name, loc.pincode, loc.latitude, loc.longitude)
                new_job = Job(
                    job_id=job_id,
                    location_id=loc.location_id,
                    category_id=cat.category_id,
                    status="PENDING",
                    search_query=search_query
                )
                new_jobs.append(new_job)

    if new_jobs:
        db.bulk_save_objects(new_jobs)
        db.commit()
        jobs_created = len(new_jobs)
        logger.info(f"Generated {jobs_created} new jobs.")
    else:
        logger.info("All jobs already exist.")

    total_jobs = db.query(Job).count()
    
    return {
        "jobs_created": jobs_created,
        "jobs_existing": total_jobs - jobs_created,
        "total_jobs": total_jobs,
        "message": "Job generation complete" if jobs_created > 0 else "All jobs already exist"
    }

def execute_single_job(
    job_id: str,
    db: Session,
    custom_engine = None,
    page_override = None
) -> Dict[str, Any]:
    """
    Executes a single discovery job by ID:
    1. Loads job, location, and category
    2. Marks job RUNNING
    3. Runs discovery engine
    4. Normalizes, geo-validates, deduplicates, and saves results
    5. Updates job status and audit fields
    """
    job = db.query(Job).filter(Job.job_id == job_id).first()
    if not job:
        return {
            "status": "failed",
            "job_id": job_id,
            "query": "",
            "count": 0,
            "results": [],
            "error": f"Job with ID '{job_id}' not found"
        }

    loc = db.query(Location).filter(Location.location_id == job.location_id).first()
    cat = db.query(Category).filter(Category.category_id == job.category_id).first()

    if not loc or not cat:
        job.status = "FAILED"
        job.error_message = "Associated Location or Category not found"
        db.commit()
        return {
            "status": "failed",
            "job_id": job_id,
            "query": job.search_query,
            "count": 0,
            "results": [],
            "error": job.error_message
        }

    # Atomically lock and mark RUNNING to prevent race conditions
    now = datetime.now(timezone.utc)
    updated_count = db.query(Job).filter(
        Job.job_id == job_id,
        Job.status == "PENDING"
    ).update({
        "status": "RUNNING",
        "attempt_count": Job.attempt_count + 1,
        "last_attempt_at": now
    }, synchronize_session="fetch")
    
    if updated_count == 0:
        db.rollback()
        return {
            "status": "failed",
            "job_id": job_id,
            "query": job.search_query,
            "count": 0,
            "results": [],
            "error": "Job is no longer PENDING or could not be claimed safely."
        }
    db.commit()
    db.refresh(job)

    engine = custom_engine or discovery_engine
    job_payload = {
        "job_id": job.job_id,
        "category": cat.category_name,
        "pincode": loc.pincode,
        "latitude": loc.latitude,
        "longitude": loc.longitude,
        "radius_km": loc.radius_km or 20.0
    }

    # Execute discovery
    discovery_res = engine.execute_discovery(job_payload, page_override=page_override)
    
    raw_listings = discovery_res.get("results", [])
    raw_status = discovery_res.get("status", "failed")
    error_msg = discovery_res.get("error")
    blocked_reason = discovery_res.get("blocked_reason")

    saved_count = 0
    persisted_results = []

    if raw_status in ("success", "partial") and raw_listings:
        for item in raw_listings:
            normalized = normalize_business_record(item)
            
            # Geo distance validation
            is_valid, distance_km, geo_notes = validate_geo_distance(
                business_lat=normalized.get("latitude"),
                business_lng=normalized.get("longitude"),
                target_lat=loc.latitude,
                target_lng=loc.longitude,
                radius_km=loc.radius_km or 20.0
            )

            # Deduplication
            dedup_key = generate_dedup_key(
                name=normalized["name"],
                address=normalized["address"],
                phone=normalized["phone"],
                place_id=normalized["place_id"],
                maps_url=normalized["google_maps_url"]
            )

            biz_id = generate_business_id(
                name=normalized["name"],
                phone=normalized["phone"],
                lat=normalized["latitude"],
                lng=normalized["longitude"],
                maps_url=normalized["google_maps_url"]
            )

            existing_biz = db.query(Business).filter(Business.dedup_key == dedup_key).first()

            if existing_biz:
                # Update existing record if richer data
                if not existing_biz.phone and normalized["phone"]:
                    existing_biz.phone = normalized["phone"]
                if not existing_biz.address and normalized["address"]:
                    existing_biz.address = normalized["address"]
                if not existing_biz.website and normalized["website"]:
                    existing_biz.website = normalized["website"]
                if not existing_biz.place_id and normalized["place_id"]:
                    existing_biz.place_id = normalized["place_id"]
                if existing_biz.latitude is None and normalized["latitude"] is not None:
                    existing_biz.latitude = normalized["latitude"]
                    existing_biz.longitude = normalized["longitude"]
                    existing_biz.distance_km = distance_km
                    existing_biz.is_valid = is_valid
                    existing_biz.validation_errors = json.dumps(geo_notes) if geo_notes else None
                persisted_results.append({
                    "business_id": existing_biz.business_id,
                    "name": existing_biz.name,
                    "phone": existing_biz.phone,
                    "address": existing_biz.address,
                    "is_valid": existing_biz.is_valid,
                    "distance_km": existing_biz.distance_km,
                    "is_duplicate": True
                })
            else:
                new_biz = Business(
                    business_id=biz_id,
                    job_id=job.job_id,
                    name=normalized["name"],
                    address=normalized["address"],
                    phone=normalized["phone"],
                    email=normalized["email"],
                    website=normalized["website"],
                    google_maps_url=normalized["google_maps_url"],
                    place_id=normalized["place_id"],
                    category=cat.category_name,
                    district=loc.district,
                    state=loc.state,
                    officename=loc.anchor_name,
                    latitude=normalized["latitude"],
                    longitude=normalized["longitude"],
                    distance_km=distance_km,
                    source_query=job.search_query,
                    dedup_key=dedup_key,
                    is_valid=is_valid,
                    validation_errors=json.dumps(geo_notes) if geo_notes else None
                )
                db.add(new_biz)
                saved_count += 1
                persisted_results.append({
                    "business_id": biz_id,
                    "name": normalized["name"],
                    "phone": normalized["phone"],
                    "address": normalized["address"],
                    "is_valid": is_valid,
                    "distance_km": distance_km,
                    "is_duplicate": False
                })

    # Update job status
    completion_time = datetime.now(timezone.utc)
    job.listings_found = len(raw_listings)
    job.businesses_saved = saved_count
    job.completed_at = completion_time

    if raw_status == "blocked":
        job.status = "BLOCKED"
        job.blocked_reason = blocked_reason or "CAPTCHA or access restriction"
        job.error_message = error_msg
    elif raw_status == "failed":
        job.status = "FAILED"
        job.error_message = error_msg
    elif raw_status == "zero_results":
        job.status = "COMPLETED"
        job.error_message = None
    elif raw_status == "partial":
        job.status = "PARTIAL"
        job.error_message = f"Extracted {len(raw_listings)} listings with some detail extraction failures"
    else:
        job.status = "COMPLETED"
        job.error_message = None

    db.commit()

    # Email Enrichment Phase
    try:
        businesses_in_job = db.query(Business).filter(Business.job_id == job.job_id).all()
        to_enrich_dicts = []
        
        for b in businesses_in_job:
            if b.website:
                if b.email:
                    if not b.email_enrichment_status:
                        b.email_enrichment_status = "skipped_existing_email"
                else:
                    to_enrich_dicts.append({
                        "business_id": b.business_id,
                        "name": b.name,
                        "website": b.website
                    })
        
        if to_enrich_dicts:
            from src.services.email_enricher import email_enricher
            enrichment_results = email_enricher.enrich_batch(to_enrich_dicts)
            
            now_dt = datetime.now(timezone.utc)
            for res in enrichment_results:
                b_model = next((b for b in businesses_in_job if b.business_id == res["business_id"]), None)
                if b_model:
                    if res["email"]:
                        b_model.email = res["email"]
                    b_model.email_source_url = res.get("email_source_url")
                    b_model.email_enrichment_status = res.get("email_enrichment_status")
                    b_model.email_enriched_at = now_dt
                    
            db.commit()
        else:
            db.commit() # commit the skipped statuses
    except Exception as enrich_err:
        logger.error(f"Email enrichment failed for Job {job_id}: {enrich_err}")

    return {
        "status": "success" if job.status in ("COMPLETED", "PARTIAL") else "failed",
        "job_id": job.job_id,
        "job_status": job.status,
        "query": job.search_query,
        "listings_found": len(raw_listings),
        "businesses_saved": saved_count,
        "results": persisted_results,
        "error": job.error_message,
        "blocked_reason": job.blocked_reason
    }

def retry_job(job_id: str, db: Session) -> Dict[str, Any]:
    job = db.query(Job).filter(Job.job_id == job_id).first()
    if not job:
        return {"error": "Job not found", "job_id": job_id}
    
    prev_status = job.status
    job.status = "PENDING"
    job.error_message = None
    job.blocked_reason = None
    db.commit()

    return {
        "job_id": job.job_id,
        "previous_status": prev_status,
        "new_status": "PENDING",
        "attempt_count": job.attempt_count,
        "message": "Job queued for retry"
    }

def retry_all_jobs(db: Session, target_status: str = "FAILED") -> Dict[str, Any]:
    jobs_to_retry = db.query(Job).filter(Job.status == target_status).all()
    count = 0
    for j in jobs_to_retry:
        j.status = "PENDING"
        j.error_message = None
        j.blocked_reason = None
        count += 1
    db.commit()
    return {
        "jobs_retried": count,
        "message": f"{count} jobs queued for retry"
    }

def recover_stale_jobs(db: Session, max_age_minutes: int = 30) -> Dict[str, Any]:
    """Finds RUNNING jobs older than max_age_minutes and resets them to PENDING."""
    from datetime import timedelta
    now = datetime.now(timezone.utc)
    threshold = now - timedelta(minutes=max_age_minutes)
    
    stale_jobs = db.query(Job).filter(
        Job.status == "RUNNING",
        Job.last_attempt_at < threshold
    ).all()
    
    count = 0
    for j in stale_jobs:
        j.status = "PENDING"
        j.error_message = "Recovered from stale RUNNING state"
        j.blocked_reason = None
        count += 1
    
    db.commit()
    logger.info(f"Recovered {count} stale RUNNING jobs.")
    return {"recovered_count": count}

def auto_retry_failed_jobs(db: Session, max_retries: int = 3) -> Dict[str, Any]:
    """Finds FAILED jobs with attempt_count < max_retries and sets them to PENDING."""
    failed_jobs = db.query(Job).filter(
        Job.status == "FAILED",
        Job.attempt_count < max_retries
    ).all()
    
    count = 0
    for j in failed_jobs:
        j.status = "PENDING"
        j.error_message = "Auto-queued for retry"
        count += 1
        
    db.commit()
    logger.info(f"Auto-retried {count} FAILED jobs.")
    return {"retried_count": count}
