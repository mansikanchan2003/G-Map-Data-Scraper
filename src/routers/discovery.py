import uuid
import time
from fastapi import APIRouter, Depends, HTTPException, Body
from sqlalchemy.orm import Session
from src.database import get_db, SessionLocal
from src.models import Job, RunLog
from src.services import job_manager
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field
from datetime import datetime, timezone
import json

router = APIRouter(prefix="/api/v1/discovery", tags=["Discovery"])

class BatchRequest(BaseModel):
    batch_size: int = Field(50, ge=1, le=500)
    delay_between_jobs_seconds: float = Field(2.0, ge=0.0, le=60.0)
    trigger_source: str = "api"

@router.post("/batch")
def run_batch_discovery(
    payload: BatchRequest = Body(default_factory=BatchRequest),
    db: Session = Depends(get_db)
):
    """
    Synchronously processes a single batch of jobs.
    Designed to be called repeatedly by an external orchestrator (e.g., n8n)
    until pending_jobs_remaining reaches 0.
    """
    start_time = time.time()
    
    # Check pending jobs
    pending_jobs = (
        db.query(Job)
        .filter(Job.status == "PENDING")
        .limit(payload.batch_size)
        .all()
    )
    
    if not pending_jobs:
        return {
            "status": "completed",
            "message": "No pending jobs to process.",
            "jobs_processed": 0,
            "pending_jobs_remaining": 0
        }
        
    run_id = str(uuid.uuid4())
    run_log = RunLog(
        run_id=run_id,
        trigger_source=payload.trigger_source,
        status="RUNNING",
        started_at=datetime.now(timezone.utc)
    )
    db.add(run_log)
    db.commit()

    attempted = 0
    completed = 0
    failed = 0
    blocked = 0
    discovered = 0
    saved = 0
    updated_businesses = 0
    duplicate_businesses = 0
    emails_found_total = 0
    emails_not_found_total = 0
    emails_failed_total = 0
    unidentifiable_total = 0
    detail_extraction_failed_total = 0
    errors = []
    
    try:
        for job in pending_jobs:
            res = job_manager.execute_single_job(job.job_id, db)
            attempted += 1

            status = res.get("job_status")
            if status in ("COMPLETED", "PARTIAL"):
                completed += 1
            elif status == "BLOCKED":
                blocked += 1
            else:
                failed += 1

            discovered += res.get("listings_found", 0)
            saved += res.get("businesses_saved", 0)
            updated_businesses += res.get("businesses_updated", 0)
            duplicate_businesses += res.get("businesses_duplicate", 0)
            unidentifiable_total += res.get("unidentifiable_count", 0)
            detail_extraction_failed_total += res.get("detail_extraction_failed_count", 0)
            emails_found_total += res.get("emails_found", 0)
            emails_not_found_total += res.get("emails_not_found", 0)
            emails_failed_total += res.get("emails_failed", 0)

            if res.get("error"):
                errors.append({"job_id": job.job_id, "error": res["error"]})

            if blocked > 0:
                break

            time.sleep(payload.delay_between_jobs_seconds)
            
    except Exception as e:
        errors.append({"batch_error": str(e)})
    finally:
        duration = round(time.time() - start_time, 2)
        remaining = db.query(Job).filter(Job.status == "PENDING").count()
        
        # Update RunLog
        run_log = db.query(RunLog).filter(RunLog.run_id == run_id).first()
        if run_log:
            run_log.status = "COMPLETED" if blocked == 0 and not errors else ("BLOCKED" if blocked > 0 else "FAILED")
            run_log.jobs_attempted = attempted
            run_log.jobs_completed = completed
            run_log.jobs_failed = failed
            run_log.jobs_total = attempted
            run_log.businesses_discovered = discovered
            run_log.businesses_new = saved
            run_log.businesses_updated = updated_businesses
            run_log.businesses_duplicate = duplicate_businesses
            run_log.email_enriched = emails_found_total + emails_not_found_total + emails_failed_total
            run_log.email_found = emails_found_total
            run_log.email_not_found = emails_not_found_total
            run_log.email_failed = emails_failed_total
            run_log.errors_count = len(errors)
            run_log.duration_seconds = duration
            run_log.error_summary = json.dumps(errors) if errors else None
            run_log.completed_at = datetime.now(timezone.utc)
            db.commit()

    return {
        "status": "completed" if blocked == 0 else "blocked",
        "run_id": run_id,
        "jobs_processed": attempted,
        "jobs_completed": completed,
        "jobs_failed": failed,
        "businesses_saved": saved,
        "unidentifiable_total": unidentifiable_total,
        "detail_extraction_failed_total": detail_extraction_failed_total,
        "pending_jobs_remaining": remaining,
        "duration_seconds": duration,
        "errors": errors
    }

@router.get("/status")
def get_discovery_status():
    return {"message": "State is fully managed via PostgreSQL. Draining is orchestrated externally."}

@router.post("/stop")
def stop_discovery():
    return {"message": "Draining is orchestrated externally. Stop the workflow in n8n to halt discovery."}
