import uuid
import time
from fastapi import APIRouter, Depends, HTTPException, Body
from sqlalchemy.orm import Session
from src.database import get_db
from src.models import Job, RunLog
from src.services import job_manager
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field
from datetime import datetime, timezone
import json

router = APIRouter(prefix="/api/v1/discovery", tags=["Discovery"])

# Simple in-process state tracking for discovery batches
_discovery_state = {
    "is_running": False,
    "current_run_id": None,
    "started_at": None,
    "jobs_processed": 0,
    "jobs_total": 0,
    "current_job_id": None,
    "stop_requested": False
}

class BatchRequest(BaseModel):
    batch_size: int = 10
    delay_between_jobs_seconds: float = 2.0
    trigger_source: str = "api"
    jobs_retried: int = Field(0, ge=0)
    jobs_recovered: int = Field(0, ge=0)

@router.post("/batch")
def run_batch_discovery(
    payload: BatchRequest = Body(default_factory=BatchRequest),
    db: Session = Depends(get_db)
):
    global _discovery_state
    if _discovery_state["is_running"]:
        raise HTTPException(
            status_code=503,
            detail="Discovery engine already running (another batch is in progress)."
        )

    run_id = str(uuid.uuid4())
    _discovery_state["is_running"] = True
    _discovery_state["current_run_id"] = run_id
    _discovery_state["started_at"] = time.time()
    _discovery_state["jobs_processed"] = 0
    _discovery_state["stop_requested"] = False

    pending_jobs = (
        db.query(Job)
        .filter(Job.status == "PENDING")
        .limit(payload.batch_size)
        .all()
    )

    _discovery_state["jobs_total"] = len(pending_jobs)
    
    start_time = time.time()
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
    errors = []

    try:
        run_log = RunLog(
            run_id=run_id,
            trigger_source=payload.trigger_source,
            status="RUNNING",
            started_at=datetime.now(timezone.utc)
        )
        db.add(run_log)
        db.commit()

        for job in pending_jobs:
            if _discovery_state["stop_requested"]:
                break

            _discovery_state["current_job_id"] = job.job_id
            res = job_manager.execute_single_job(job.job_id, db)
            attempted += 1
            _discovery_state["jobs_processed"] = attempted

            status = res.get("job_status")
            if status in ("COMPLETED", "PARTIAL"):
                completed += 1
            elif status == "BLOCKED":
                blocked += 1
            else:
                failed += 1

            found = res.get("listings_found", 0)
            persisted = res.get("businesses_saved", 0)
            updated = res.get("businesses_updated", 0)
            duplicate = res.get("businesses_duplicate", 0)
            e_found = res.get("emails_found", 0)
            e_not_found = res.get("emails_not_found", 0)
            e_failed = res.get("emails_failed", 0)
            
            discovered += found
            saved += persisted
            updated_businesses += updated
            duplicate_businesses += duplicate
            emails_found_total += e_found
            emails_not_found_total += e_not_found
            emails_failed_total += e_failed

            if res.get("error"):
                errors.append({"job_id": job.job_id, "error": res["error"]})

            if blocked > 0:
                # Early stop if blocked/CAPTCHA detected to prevent account/IP escalation
                break

            time.sleep(payload.delay_between_jobs_seconds)

    except Exception as e:
        errors.append({"batch_error": str(e)})
        failed += (len(pending_jobs) - attempted)
    finally:
        _discovery_state["is_running"] = False
        _discovery_state["current_run_id"] = None
        _discovery_state["current_job_id"] = None
        
        duration = round(time.time() - start_time, 2)
        
        # Update RunLog
        run_log = db.query(RunLog).filter(RunLog.run_id == run_id).first()
        if run_log:
            run_log.status = "COMPLETED" if blocked == 0 and not errors else ("BLOCKED" if blocked > 0 else "FAILED")
            run_log.jobs_attempted = attempted
            run_log.jobs_completed = completed
            run_log.jobs_failed = failed
            run_log.jobs_total = _discovery_state["jobs_total"]
            run_log.jobs_retried = payload.jobs_retried
            run_log.jobs_recovered = payload.jobs_recovered
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
        "run_id": run_id,
        "status": "COMPLETED" if blocked == 0 and not errors else ("BLOCKED" if blocked > 0 else "FAILED"),
        "jobs_attempted": attempted,
        "jobs_completed": completed,
        "jobs_failed": failed,
        "jobs_blocked": blocked,
        "businesses_discovered": discovered,
        "businesses_saved": saved,
        "duration_seconds": duration,
        "errors": errors
    }

@router.get("/status")
def get_discovery_status():
    return _discovery_state

@router.post("/stop")
def stop_discovery():
    global _discovery_state
    if not _discovery_state["is_running"]:
        return {"message": "No discovery run is active."}
    _discovery_state["stop_requested"] = True
    return {
        "message": "Stop signal sent. Current job will complete before stopping.",
        "run_id": _discovery_state["current_run_id"]
    }
