import hashlib
import urllib.parse
from sqlalchemy.orm import Session
from src.models import Location, Category, Job
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
    
    # Generate cross product
    # Note: For ~8400 jobs, we can do this in memory or via a batched insert.
    # We will do a safe upsert-like check or batched creation.
    
    # Pre-fetch existing job IDs for faster lookups
    existing_job_ids = {job.job_id for job in db.query(Job.job_id).all()}
    
    new_jobs = []
    
    for loc in locations:
        for cat in categories:
            job_id = generate_job_id(loc.location_id, cat.category_id)
            
            if job_id not in existing_job_ids:
                search_query = build_search_query(cat.category_name, loc.latitude, loc.longitude)
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
