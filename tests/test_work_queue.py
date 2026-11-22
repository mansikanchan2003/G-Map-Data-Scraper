"""
Phase 1 of moving off one monolith (22 Nov 2026): the API, the worker and the scraper
run as separate containers from one codebase (src.roles), and scraping the API is
asked for goes through a queue in the database (src.services.work_queue).
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src import roles
from src.database import Base, get_db
from src.main import app
from src.models import Category, Job, Location
from src.models.work_queue import QueuedTask
from src.services import work_queue

engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base.metadata.create_all(bind=engine)


@pytest.fixture
def db(monkeypatch):
    monkeypatch.setattr(work_queue, "SessionLocal", Session)
    monkeypatch.setattr(work_queue, "POLL_SECONDS", 0.01)

    def override():
        s = Session()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db] = override
    s = Session()
    s.query(QueuedTask).delete()
    s.query(Job).delete()
    s.commit()
    yield s
    s.close()
    app.dependency_overrides.pop(get_db, None)


def test_each_role_runs_only_its_share(monkeypatch):
    monkeypatch.setenv("APP_ROLE", "api")
    assert roles.runs("insights_cache") and roles.queue_scraping()
    assert not roles.runs("autopilot") and not roles.runs("nudges") and not roles.runs("memory_guard")
    monkeypatch.setenv("APP_ROLE", "worker")
    assert roles.runs("nudges") and roles.runs("followups") and roles.runs("call_recordings")
    assert not roles.runs("autopilot") and not roles.queue_scraping()
    monkeypatch.setenv("APP_ROLE", "scraper")
    assert roles.runs("autopilot") and roles.runs("scrape_queue") and roles.runs("memory_guard")
    assert not roles.runs("nudges")
    # Unset or unknown: everything in one process, as before.
    monkeypatch.setenv("APP_ROLE", "nonsense")
    assert roles.role() == "all" and roles.runs("autopilot") and roles.runs("nudges")
    assert not roles.queue_scraping()


def test_a_queued_task_is_run_once_and_its_result_kept(db, monkeypatch):
    seen = []
    monkeypatch.setitem(work_queue.HANDLERS, "echo", lambda payload, s: seen.append(payload) or {"got": payload["n"]})
    first = work_queue.enqueue(db, "echo", {"n": 1})
    second = work_queue.enqueue(db, "echo", {"n": 2})
    assert work_queue.pending(db) == 2
    assert work_queue.run_next() and work_queue.run_next() and not work_queue.run_next()
    assert seen == [{"n": 1}, {"n": 2}]                       # oldest first, each once
    task = work_queue.wait(first, 1)
    assert task.status == "DONE" and task.result == {"got": 1} and task.claimed_by
    assert work_queue.get(second).result == {"got": 2}


def test_a_failing_task_is_failed_with_its_error_and_a_restart_does_not_rerun_one(db, monkeypatch):
    def boom(payload, s):
        raise RuntimeError("Chrome crashed")

    monkeypatch.setitem(work_queue.HANDLERS, "boom", boom)
    task_id = work_queue.enqueue(db, "boom", {})
    work_queue.run_next()
    task = work_queue.get(task_id)
    assert task.status == "FAILED" and "Chrome crashed" in task.error
    # Left RUNNING by a scraper that stopped mid-way: failed at the next start, not run twice.
    stuck = work_queue.enqueue(db, "boom", {})
    row = db.query(QueuedTask).filter(QueuedTask.task_id == stuck).one()
    row.status = "RUNNING"
    db.commit()
    assert work_queue.mark_interrupted() == 1
    assert work_queue.get(stuck).error == work_queue.INTERRUPTED


def test_waiting_gives_up_after_its_time(db):
    task_id = work_queue.enqueue(db, "never_run", {})
    with pytest.raises(TimeoutError):
        work_queue.wait(task_id, 0.05)


def _pending_job(db):
    db.add_all([Location(location_id="Lq", pincode="110001", latitude=28.6, longitude=77.2, radius_km=20),
                Category(category_id="Cq", category_name="Kiosk"),
                Job(job_id="jq1", location_id="Lq", category_id="Cq", status="PENDING", search_query="q")])
    db.commit()


def test_the_api_queues_a_batch_for_the_scraper_instead_of_opening_chrome(db, monkeypatch):
    monkeypatch.setenv("APP_ROLE", "api")
    if not db.query(Location).filter(Location.location_id == "Lq").first():
        _pending_job(db)
    ran_here = []
    monkeypatch.setattr("src.routers.discovery._run_batch", lambda *a, **k: ran_here.append(1))
    client = TestClient(app)
    r = client.post("/api/v1/discovery/batch", json={"batch_size": 5, "run_in_background": True})
    assert r.status_code == 200 and r.json()["status"] == "started"
    [task] = db.query(QueuedTask).all()
    assert task.kind == work_queue.DISCOVERY_BATCH and task.payload["batch_size"] == 5
    assert task.payload["run_in_background"] is False and not ran_here


def test_a_waiting_caller_gets_the_scrapers_answer(db, monkeypatch):
    monkeypatch.setenv("APP_ROLE", "api")

    def scraper_answers(task_id, timeout_seconds):
        row = db.query(QueuedTask).filter(QueuedTask.task_id == task_id).one()
        row.status, row.result = "DONE", {"status": "completed", "jobs_processed": 3}
        db.commit()
        return row

    monkeypatch.setattr(work_queue, "wait", scraper_answers)
    client = TestClient(app)
    r = client.post("/api/v1/discovery/batch", json={"batch_size": 3})
    assert r.status_code == 200 and r.json() == {"status": "completed", "jobs_processed": 3}
