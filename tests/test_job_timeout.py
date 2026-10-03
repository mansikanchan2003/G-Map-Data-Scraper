"""
A wedged job must not take the batch down with it.

Every Playwright call already carries a timeout, but a browser process that
stops responding does not always let them fire — one job sat RUNNING for
fifty minutes and the batch behind it never moved. This is the backstop that
does not depend on Playwright behaving.
"""
import time

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import src.routers.discovery as discovery
from src.database import Base
from src.models import Category, Job, Location  # noqa: F401

engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base.metadata.create_all(bind=engine)

JOB_ID = "jobtimeout000001"


@pytest.fixture
def db(monkeypatch):
    monkeypatch.setattr("src.database.SessionLocal", TestingSessionLocal)
    s = TestingSessionLocal()
    s.query(Job).delete()
    s.query(Location).delete()
    s.query(Category).delete()
    s.add(Category(category_id="catT", category_name="Test Category"))
    s.add(Location(location_id="locT", pincode="140001", latitude=30.0,
                   longitude=75.0, radius_km=20.0, state="Punjab"))
    s.add(Job(job_id=JOB_ID, location_id="locT", category_id="catT",
              status="RUNNING", search_query="https://maps.google.com"))
    s.commit()
    try:
        yield s
    finally:
        s.rollback()
        s.close()


def test_a_hung_job_is_abandoned_and_the_batch_continues(db, monkeypatch):
    monkeypatch.setattr(discovery.settings, "job_timeout_seconds", 1)

    def never_returns(job_id, session, *a, **k):
        time.sleep(30)          # the wedged browser
        return {"job_status": "COMPLETED"}

    monkeypatch.setattr(discovery.job_manager, "execute_single_job", never_returns)

    started = time.time()
    res = discovery._run_job_with_timeout(JOB_ID, db, "run-test")
    elapsed = time.time() - started

    assert res["job_status"] == "TIMEOUT"
    # Returned promptly rather than waiting out the hung call.
    assert elapsed < 10, f"waited {elapsed:.1f}s"


def test_an_abandoned_job_goes_back_to_pending(db, monkeypatch):
    monkeypatch.setattr(discovery.settings, "job_timeout_seconds", 1)
    monkeypatch.setattr(discovery.job_manager, "execute_single_job",
                        lambda *a, **k: time.sleep(30))

    discovery._run_job_with_timeout(JOB_ID, db, "run-test")

    db.expire_all()
    job = db.query(Job).filter(Job.job_id == JOB_ID).first()
    # Left RUNNING it would block the stale-job sweep as well; PENDING means
    # it is simply tried again.
    assert job.status == "PENDING"
    assert "Abandoned" in (job.error_message or "")


def test_a_job_that_finishes_in_time_is_untouched(db, monkeypatch):
    monkeypatch.setattr(discovery.settings, "job_timeout_seconds", 30)
    monkeypatch.setattr(
        discovery.job_manager, "execute_single_job",
        lambda *a, **k: {"job_status": "COMPLETED", "listings_found": 7,
                         "businesses_saved": 5},
    )

    res = discovery._run_job_with_timeout(JOB_ID, db, "run-test")
    assert res["job_status"] == "COMPLETED"
    assert res["businesses_saved"] == 5

    db.expire_all()
    assert db.query(Job).filter(Job.job_id == JOB_ID).first().status == "RUNNING"


def test_a_job_that_raises_is_reported_not_swallowed(db, monkeypatch):
    monkeypatch.setattr(discovery.settings, "job_timeout_seconds", 30)

    def boom(*a, **k):
        raise RuntimeError("browser crashed")

    monkeypatch.setattr(discovery.job_manager, "execute_single_job", boom)

    res = discovery._run_job_with_timeout(JOB_ID, db, "run-test")
    assert res["job_status"] == "FAILED"
    assert "browser crashed" in res["error"]


# --- the browsers a job leaves behind -----------------------------------------

def _spawn_stand_in_browser():
    """A child process that would run for a minute, like a wedged Chromium."""
    import subprocess
    import sys
    from src.utils import browser_processes

    before = browser_processes.snapshot()
    proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
    browser_processes.claim_new(before)
    return proc


def test_a_hung_jobs_browser_is_killed_not_left_running(db, monkeypatch):
    """
    Abandoning the thread used to leave its Chromium alive. On a shared
    server those pile up until nothing answers.
    """
    monkeypatch.setattr(discovery.settings, "job_timeout_seconds", 1)
    started = {}

    def wedged(job_id, session, *a, **k):
        started["proc"] = _spawn_stand_in_browser()
        started["proc"].wait()          # stuck until the browser goes away
        return {"job_status": "FAILED", "error": "browser closed"}

    monkeypatch.setattr(discovery.job_manager, "execute_single_job", wedged)

    res = discovery._run_job_with_timeout(JOB_ID, db, "run-test")
    assert res["job_status"] == "TIMEOUT"
    assert started["proc"].poll() is not None, "the browser is still running"

    db.expire_all()
    assert db.query(Job).filter(Job.job_id == JOB_ID).first().status == "PENDING"


def test_a_browser_left_by_a_finished_job_is_killed_too(db, monkeypatch):
    """The email step can give up on closing its browser and return anyway."""
    monkeypatch.setattr(discovery.settings, "job_timeout_seconds", 30)
    started = {}

    def leaves_one_behind(job_id, session, *a, **k):
        started["proc"] = _spawn_stand_in_browser()
        return {"job_status": "COMPLETED", "listings_found": 1, "businesses_saved": 1}

    monkeypatch.setattr(discovery.job_manager, "execute_single_job", leaves_one_behind)

    res = discovery._run_job_with_timeout(JOB_ID, db, "run-test")
    assert res["job_status"] == "COMPLETED"
    started["proc"].wait(timeout=10)
    assert started["proc"].poll() is not None


def test_a_browser_the_job_closed_itself_is_not_an_error(db, monkeypatch):
    from src.utils import browser_processes
    monkeypatch.setattr(discovery.settings, "job_timeout_seconds", 30)

    def tidy(job_id, session, *a, **k):
        proc = _spawn_stand_in_browser()
        proc.kill()
        proc.wait()
        return {"job_status": "COMPLETED"}

    monkeypatch.setattr(discovery.job_manager, "execute_single_job", tidy)
    killed = []
    real = browser_processes.kill_for_thread
    monkeypatch.setattr(browser_processes, "kill_for_thread", lambda i: killed.append(real(i)) or killed[-1])

    discovery._run_job_with_timeout(JOB_ID, db, "run-test")
    assert killed == [0]
