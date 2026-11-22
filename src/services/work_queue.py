"""
The work queue between the API and the scraper container (Phase 1, 22 Nov 2026).

The API puts a scraping batch or a single job here (enqueue) instead of opening
Chrome itself; the scraper container's consumer thread claims the oldest one, runs
it and writes back the result. A caller that waits for the answer (n8n's batch
calls, the Jobs page's "Run") is answered once the result is in (wait).

Postgres claims rows with SKIP LOCKED, so two consumers would never take the same
task; there is one scraper, which runs one task at a time, as one browser did before.
"""
import logging
import socket
import threading
import time
import uuid
from datetime import datetime, timezone
from typing import Callable, Dict, Optional

from sqlalchemy.orm import Session

from src.database import SessionLocal
from src.models.work_queue import QueuedTask

logger = logging.getLogger("gmap_scraper.work_queue")

DISCOVERY_BATCH = "discovery_batch"
RUN_JOB = "run_job"
POLL_SECONDS = 5
# A task left RUNNING by a scraper that restarted mid-way (a deploy) is not picked up
# again: its jobs go back to PENDING through the usual stale-job sweep.
INTERRUPTED = "Interrupted: the scraper restarted while it ran"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def enqueue(db: Session, kind: str, payload: dict) -> str:
    task = QueuedTask(task_id=uuid.uuid4().hex, kind=kind, payload=payload, status="QUEUED")
    db.add(task)
    db.commit()
    logger.info(f"work_queue event=QUEUED task={task.task_id} kind={kind}")
    return task.task_id


def get(task_id: str) -> Optional[QueuedTask]:
    db = SessionLocal()
    try:
        return db.query(QueuedTask).filter(QueuedTask.task_id == task_id).first()
    finally:
        db.close()


def wait(task_id: str, timeout_seconds: float) -> QueuedTask:
    """The task once it is DONE or FAILED; TimeoutError if it is not by then."""
    deadline = time.monotonic() + timeout_seconds
    while True:
        task = get(task_id)
        if task and task.status in ("DONE", "FAILED"):
            return task
        if time.monotonic() >= deadline:
            raise TimeoutError(f"task {task_id} still {task.status if task else 'missing'}")
        time.sleep(POLL_SECONDS)


def pending(db: Session) -> int:
    return db.query(QueuedTask).filter(QueuedTask.status.in_(("QUEUED", "RUNNING"))).count()


# --- The consumer, in the scraper container ----------------------------------------------

def _run_discovery_batch(payload: dict, db: Session) -> dict:
    from src.routers.discovery import BatchRequest, _run_batch
    return _run_batch(BatchRequest(**{**payload, "run_in_background": False}), db)


def _run_job(payload: dict, db: Session) -> dict:
    from src.services import job_manager
    return job_manager.execute_single_job(payload["job_id"], db)


HANDLERS: Dict[str, Callable[[dict, Session], dict]] = {
    DISCOVERY_BATCH: _run_discovery_batch,
    RUN_JOB: _run_job,
}


def _claim(db: Session) -> Optional[QueuedTask]:
    q = db.query(QueuedTask).filter(QueuedTask.status == "QUEUED").order_by(QueuedTask.created_at)
    if db.bind.dialect.name == "postgresql":
        q = q.with_for_update(skip_locked=True)
    task = q.first()
    if task is None:
        db.rollback()
        return None
    task.status, task.started_at, task.claimed_by = "RUNNING", _now(), socket.gethostname()[:100]
    db.commit()
    return task


def run_next() -> bool:
    """Claims and runs the oldest queued task; False when there was none."""
    db = SessionLocal()
    try:
        task = _claim(db)
        if task is None:
            return False
        task_id, kind, payload = task.task_id, task.kind, dict(task.payload or {})
        logger.info(f"work_queue event=STARTED task={task_id} kind={kind}")
        work = SessionLocal()
        try:
            result, error, status = HANDLERS[kind](payload, work), None, "DONE"
        except Exception as e:
            logger.exception(f"work_queue event=FAILED task={task_id} kind={kind}")
            result, error, status = None, str(e)[:2000], "FAILED"
        finally:
            work.close()
        row = db.query(QueuedTask).filter(QueuedTask.task_id == task_id).first()
        row.status, row.finished_at, row.error = status, _now(), error
        row.result = _jsonable(result)
        db.commit()
        logger.info(f"work_queue event={status} task={task_id} kind={kind}")
        return True
    finally:
        db.close()


def _jsonable(value):
    import json
    try:
        return json.loads(json.dumps(value, default=str)) if value is not None else None
    except (TypeError, ValueError):
        return {"repr": repr(value)[:2000]}


def mark_interrupted() -> int:
    """At the scraper's start: tasks it was running when it stopped are failed, not re-run."""
    db = SessionLocal()
    try:
        rows = db.query(QueuedTask).filter(QueuedTask.status == "RUNNING").all()
        for row in rows:
            row.status, row.finished_at, row.error = "FAILED", _now(), INTERRUPTED
        db.commit()
        return len(rows)
    finally:
        db.close()


_thread: Optional[threading.Thread] = None
_stop = threading.Event()


def _loop() -> None:
    while not _stop.is_set():
        try:
            if run_next():
                continue
        except Exception:
            logger.exception("work_queue event=LOOP_ERROR")
        _stop.wait(POLL_SECONDS)


def start() -> None:
    global _thread
    if _thread and _thread.is_alive():
        return
    _stop.clear()
    n = mark_interrupted()
    if n:
        logger.warning(f"work_queue event=INTERRUPTED_TASKS_FAILED count={n}")
    _thread = threading.Thread(target=_loop, name="work-queue", daemon=True)
    _thread.start()
    logger.info("work_queue event=CONSUMER_STARTED")


def stop() -> None:
    _stop.set()
