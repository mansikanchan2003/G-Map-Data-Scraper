import uuid
import time
from fastapi import APIRouter, Depends, HTTPException, Body, BackgroundTasks
from sqlalchemy import func
from sqlalchemy.orm import Session
from src.database import get_db, SessionLocal
from src.models import Job, RunLog
from src.config import settings
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
    # A batch takes tens of minutes. n8n waits for the result, but a browser
    # cannot hold the request open that long, so the dashboard starts it in
    # the background and follows the run instead.
    run_in_background: bool = False

class DiscoveryTarget(BaseModel):
    """A location or category that discovery can still be run against."""
    value: str
    label: str
    pending: int
    done: int


class DiscoveryTargets(BaseModel):
    states: List[str]
    locations: List[DiscoveryTarget]
    categories: List[DiscoveryTarget]


class CustomPlace(BaseModel):
    place: str                       # pincode, town or address
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    radius_km: Optional[float] = None


class CustomRunRequest(BaseModel):
    """Run discovery on places and categories that are not in the spreadsheets."""
    places: List[CustomPlace] = Field(default_factory=list, max_length=50)
    categories: List[str] = Field(default_factory=list, max_length=50)
    batch_size: int = Field(25, ge=1, le=500)
    delay_between_jobs_seconds: float = Field(5.0, ge=0.0, le=60.0)
    run_now: bool = True


@router.post("/custom-run")
def custom_discovery_run(
    payload: CustomRunRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """
    Adds places and categories, then optionally runs discovery on them.

    Places are resolved to coordinates through Google Maps, since a job cannot
    be built without them. Anything already known is reused rather than
    duplicated, so running the same target twice does not fragment the data.
    """
    from src.services.custom_target import ensure_category, ensure_location, generate_jobs_for
    from src.services.discovery_engine import GoogleMapsDiscoveryEngine

    if not payload.places or not payload.categories:
        raise HTTPException(status_code=400, detail="At least one place and one category are required.")

    categories, locations, errors = [], [], []

    for name in payload.categories:
        cat = ensure_category(db, name)
        if cat:
            categories.append(cat)

    # One browser for every place, rather than one per place.
    engine = GoogleMapsDiscoveryEngine(headless=settings.browser_headless)
    try:
        for p in payload.places:
            result = ensure_location(
                db, p.place, p.latitude, p.longitude, p.radius_km, engine=engine
            )
            if "error" in result:
                errors.append({"place": p.place, "error": result["error"]})
            else:
                locations.append(result["location"])
    finally:
        engine.close()

    if not locations or not categories:
        db.rollback()
        raise HTTPException(
            status_code=400,
            detail={"message": "Nothing could be set up from this request.", "errors": errors},
        )

    db.commit()
    generated = generate_jobs_for(db, locations, categories)

    response = {
        "status": "ready",
        "locations": [
            {"place": l.anchor_name, "pincode": l.pincode,
             "latitude": l.latitude, "longitude": l.longitude, "radius_km": l.radius_km}
            for l in locations
        ],
        "categories": [c.category_name for c in categories],
        "errors": errors,
        **generated,
    }

    if payload.run_now:
        batch = BatchRequest(
            batch_size=payload.batch_size,
            delay_between_jobs_seconds=payload.delay_between_jobs_seconds,
            trigger_source="custom_run",
            anchor_names=[l.anchor_name for l in locations],
            categories=[c.category_name for c in categories],
        )
        eligible = apply_target_filters(
            db.query(Job).filter(Job.status == "PENDING"), batch
        ).limit(payload.batch_size).count()

        if eligible:
            background_tasks.add_task(_run_batch_detached, batch)
            response["status"] = "started"
            response["jobs_queued"] = eligible
        else:
            response["status"] = "idle"
            response["jobs_queued"] = 0
            response["message"] = "These targets have no pending jobs left."

    return response


@router.get("/targets", response_model=DiscoveryTargets)
def discovery_targets(state: Optional[str] = None, db: Session = Depends(get_db)):
    """
    What a discovery batch can be pointed at, with how much work is left.

    Counts are of jobs rather than locations or categories, because that is
    what a batch consumes -- a location with 0 pending has nothing to run even
    though it exists.
    """
    from src.models import Location, Category

    loc_q = (
        db.query(
            Location.anchor_name, Location.pincode, Location.district, Location.state,
            func.count(Job.job_id).filter(Job.status == "PENDING").label("pending"),
            func.count(Job.job_id).filter(Job.status.in_(("COMPLETED", "PARTIAL"))).label("done"),
        )
        .join(Job, Job.location_id == Location.location_id)
        .group_by(Location.anchor_name, Location.pincode, Location.district, Location.state)
    )
    if state:
        loc_q = loc_q.filter(func.lower(Location.state) == state.strip().lower())

    locations = [
        DiscoveryTarget(
            value=anchor,
            label=f"{anchor} · {pincode}" + (f" · {district}" if district else ""),
            pending=pending, done=done,
        )
        for anchor, pincode, district, _st, pending, done in loc_q.all() if anchor
    ]
    locations.sort(key=lambda t: (-t.pending, t.value))

    cat_q = (
        db.query(
            Category.category_name,
            func.count(Job.job_id).filter(Job.status == "PENDING").label("pending"),
            func.count(Job.job_id).filter(Job.status.in_(("COMPLETED", "PARTIAL"))).label("done"),
        )
        .join(Job, Job.category_id == Category.category_id)
        .group_by(Category.category_name)
    )
    if state:
        cat_q = cat_q.join(Location, Location.location_id == Job.location_id).filter(
            func.lower(Location.state) == state.strip().lower()
        )

    categories = [
        DiscoveryTarget(value=name, label=name, pending=pending, done=done)
        for name, pending, done in cat_q.all() if name
    ]
    categories.sort(key=lambda t: (-t.pending, t.value))

    states = [
        r[0] for r in db.query(Location.state).filter(Location.state.isnot(None))
        .distinct().order_by(Location.state).all()
    ]

    return DiscoveryTargets(states=states, locations=locations, categories=categories)


def apply_target_filters(query, payload: "BatchRequest"):
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


@router.post("/batch")
def run_batch_discovery(
    payload: BatchRequest = Body(default_factory=BatchRequest),
    background_tasks: BackgroundTasks = None,
    db: Session = Depends(get_db)
):
    """
    Processes a single batch of jobs.

    Synchronous by default, which is what the n8n workflow relies on: it calls
    this repeatedly until pending_jobs_remaining reaches 0. With
    run_in_background the batch is started and the run id returned immediately,
    for callers that cannot hold a request open for the length of a batch.
    """
    if payload.run_in_background:
        # Count first so the caller learns straight away whether the selection
        # actually matches anything.
        eligible = apply_target_filters(db.query(Job).filter(Job.status == "PENDING"), payload).limit(payload.batch_size).count()

        if eligible == 0:
            return {
                "status": "idle",
                "message": "No pending jobs match this selection.",
                "jobs_queued": 0,
            }

        started = payload.model_copy(update={"run_in_background": False})
        background_tasks.add_task(_run_batch_detached, started)
        logger.info(
            f"discovery event=BATCH_QUEUED jobs={eligible} "
            f"states={payload.states} anchors={payload.anchor_names} "
            f"categories={payload.categories}"
        )
        return {
            "status": "started",
            "message": f"Discovery started for {eligible} job(s). Watch the latest run for progress.",
            "jobs_queued": eligible,
        }

    return _run_batch(payload, db)


def _run_batch_detached(payload: "BatchRequest"):
    """Run a batch on its own session, since the request's is already closed."""
    db = SessionLocal()
    try:
        _run_batch(payload, db)
    except Exception:
        logger.exception("discovery event=BACKGROUND_BATCH_FAILED")
    finally:
        db.close()


def _run_batch(payload: "BatchRequest", db: Session):
    start_time = time.time()


    # Check pending jobs
    pending_query = apply_target_filters(db.query(Job).filter(Job.status == "PENDING"), payload)
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
        remaining = apply_target_filters(db.query(Job).filter(Job.status == "PENDING"), payload).count()

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
