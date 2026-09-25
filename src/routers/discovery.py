import uuid
import time
from fastapi import APIRouter, Depends, HTTPException, Body
from sqlalchemy import func
from sqlalchemy.orm import Session
from src.database import get_db, SessionLocal
from src.models import Job, RunLog
from src.services import job_manager
from src.utils.logging import logger
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field
from datetime import datetime, timezone
import json

router = APIRouter(prefix="/api/v1/discovery", tags=["Discovery"])

class BatchRequest(BaseModel):
    batch_size: int = Field(50, ge=1, le=500)
    delay_between_jobs_seconds: float = Field(2.0, ge=0.0, le=60.0)
    trigger_source: str = "api"
    # Restrict the batch to jobs whose location falls in these states.
    # Omitted means every pending job is eligible, which is the behaviour the
    # n8n daily workflow relies on.
    states: Optional[List[str]] = None
    # Narrower targeting: specific pincodes/anchor names, and specific
    # categories. All supplied filters are combined with AND.
    pincodes: Optional[List[str]] = None
    anchor_names: Optional[List[str]] = None
    categories: Optional[List[str]] = None

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

    def apply_target_filters(query):
        """
        Narrow a PENDING-job query to the requested states / pincodes /
        anchor names / categories. Comparisons are case-insensitive so
        "punjab" and "Punjab" behave the same. Filters combine with AND;
        passing none leaves the query untouched, which is what the n8n
        daily workflow relies on.
        """
        from src.models import Location, Category

        def clean(values):
            return [v.strip().lower() for v in (values or []) if v and v.strip()]

        states = clean(payload.states)
        pincodes = clean(payload.pincodes)
        anchors = clean(payload.anchor_names)
        categories = clean(payload.categories)

        if states or pincodes or anchors:
            query = query.join(Location, Location.location_id == Job.location_id)
            if states:
                query = query.filter(func.lower(Location.state).in_(states))
            if pincodes:
                query = query.filter(func.lower(Location.pincode).in_(pincodes))
            if anchors:
                query = query.filter(func.lower(Location.anchor_name).in_(anchors))

        if categories:
            query = query.join(Category, Category.category_id == Job.category_id)
            query = query.filter(func.lower(Category.category_name).in_(categories))

        return query

    # Check pending jobs
    pending_query = apply_target_filters(db.query(Job).filter(Job.status == "PENDING"))
    pending_jobs = pending_query.limit(payload.batch_size).all()

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
        cancelled = False
        for job in pending_jobs:
            # /discovery/stop marks the active run CANCELLING. Checking it here
            # lets a batch wind down between jobs instead of needing the whole
            # backend restarted, which would also kill anything else running in
            # the process (a WhatsApp campaign, for instance).
            db.refresh(run_log)
            if run_log.status == "CANCELLING":
                cancelled = True
                logger.info(
                    f"discovery run_id={run_id} event=BATCH_CANCELLED "
                    f"processed={attempted} remaining={len(pending_jobs) - attempted}"
                )
                break

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
        # Mirror the batch's own filters so the caller can drain one target
        # without unrelated pending jobs making it look unfinished.
        remaining = apply_target_filters(
            db.query(Job).filter(Job.status == "PENDING")
        ).count()

        # Update RunLog
        run_log = db.query(RunLog).filter(RunLog.run_id == run_id).first()
        if run_log:
            # `errors` also carries per-job advisories such as "Enrichment
            # partial failures", which only mean a website did not yield an
            # email. Treating any entry as failure marked every successful
            # batch FAILED, so the run's status follows the job outcomes and
            # only a batch-level exception counts as a real failure.
            batch_error = any("batch_error" in e for e in errors)
            if cancelled:
                run_log.status = "CANCELLED"
            elif batch_error:
                run_log.status = "FAILED"
            elif blocked > 0:
                run_log.status = "BLOCKED"
            elif failed > 0 and completed == 0:
                run_log.status = "FAILED"
            elif failed > 0:
                run_log.status = "PARTIAL"
            else:
                run_log.status = "COMPLETED"
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
        "status": "cancelled" if cancelled else ("completed" if blocked == 0 else "blocked"),
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
def stop_discovery(db: Session = Depends(get_db)):
    """
    Asks the active discovery batch to stop after the job it is on.

    The batch checks this between jobs, so the running job still finishes and
    its businesses are saved. Nothing is killed mid-flight, and any campaign
    sharing the process is unaffected.
    """
    active = (
        db.query(RunLog)
        .filter(RunLog.status == "RUNNING")
        .order_by(RunLog.started_at.desc())
        .first()
    )
    if not active:
        return {"status": "idle", "message": "No discovery batch is running."}

    active.status = "CANCELLING"
    db.commit()
    logger.info(f"discovery run_id={active.run_id} event=STOP_REQUESTED")
    return {
        "status": "cancelling",
        "run_id": active.run_id,
        "message": "Stop requested. The batch will finish the job it is on and then stop.",
    }
