"""
A batch must not scrape into a dead internet connection.

When the server's link went down, every job failed on a name lookup and was
marked FAILED, one after another, for two days. A batch now recognises the
connection as the problem, stops, and gives the jobs back.
"""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import src.routers.discovery as discovery
from src.database import Base
from src.models import Category, Job, Location, RunLog

engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False},
                       poolclass=StaticPool)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base.metadata.create_all(bind=engine)

DNS_ERROR = "Navigation timeout or network failure: Page.goto: net::ERR_NAME_NOT_RESOLVED at https://www.google.com/maps"


@pytest.fixture
def db(monkeypatch):
    monkeypatch.setattr("src.database.SessionLocal", TestingSessionLocal)
    s = TestingSessionLocal()
    for model in (RunLog, Job, Location, Category):
        s.query(model).delete()
    s.add(Location(location_id="locO", pincode="140001", latitude=30.0, longitude=75.0,
                   radius_km=20.0, state="Punjab"))
    for i in range(8):
        s.add(Category(category_id=f"cat{i}", category_name=f"Category {i}"))
        s.add(Job(job_id=f"job{i:013d}", location_id="locO", category_id=f"cat{i}",
                  status="PENDING", search_query="q"))
    s.commit()
    yield s
    s.rollback()
    s.close()


def failing_on(error):
    """A stand-in job runner: marks the job FAILED the way a real one does."""
    seen = []

    def run(job_id, session, run_id):
        seen.append(job_id)
        own = TestingSessionLocal()
        own.query(Job).filter(Job.job_id == job_id).update(
            {"status": "FAILED", "attempt_count": Job.attempt_count + 1, "error_message": error})
        own.commit()
        own.close()
        return {"job_status": "FAILED", "error": error, "listings_found": 0, "businesses_saved": 0}

    run.seen = seen
    return run


def batch():
    return discovery.BatchRequest(batch_size=8, delay_between_jobs_seconds=0, trigger_source="autopilot")


def test_a_batch_stops_when_the_internet_is_gone_and_returns_its_jobs(db, monkeypatch):
    runner = failing_on(DNS_ERROR)
    monkeypatch.setattr(discovery, "_run_job_with_timeout", runner)
    monkeypatch.setattr(discovery.connectivity, "is_online", lambda: False)

    result = discovery._run_batch(batch(), db)

    assert len(runner.seen) == 3, "stopped after three failures, not all eight"
    assert result["offline"] is True and result["status"] == "blocked"
    db.expire_all()
    jobs = db.query(Job).all()
    assert all(j.status == "PENDING" for j in jobs), "the searches were never made, so they are not failures"
    assert all(j.attempt_count == 0 for j in jobs), "and the attempt is not held against them"
    assert db.query(RunLog).one().status == "OFFLINE"


def test_failures_with_the_internet_up_are_ordinary_failures(db, monkeypatch):
    """Three bad searches in a row while online is not an outage."""
    runner = failing_on(DNS_ERROR)
    monkeypatch.setattr(discovery, "_run_job_with_timeout", runner)
    monkeypatch.setattr(discovery.connectivity, "is_online", lambda: True)

    result = discovery._run_batch(batch(), db)

    assert len(runner.seen) == 8 and result["offline"] is False
    db.expire_all()
    assert db.query(Job).filter(Job.status == "FAILED").count() == 8


def test_other_errors_never_ask_about_the_connection(db, monkeypatch):
    runner = failing_on("Unexpected discovery error: selector changed")
    monkeypatch.setattr(discovery, "_run_job_with_timeout", runner)
    asked = []
    monkeypatch.setattr(discovery.connectivity, "is_online", lambda: asked.append(1) or False)

    result = discovery._run_batch(batch(), db)

    assert len(runner.seen) == 8 and result["offline"] is False and asked == []


@pytest.mark.parametrize("error, network", [
    (DNS_ERROR, True),
    ("Page.goto: net::ERR_INTERNET_DISCONNECTED", True),
    ("Page.goto: Timeout 30000ms exceeded", False),
    ("Google Maps access restricted or CAPTCHA presented", False),
    (None, False),
])
def test_which_errors_read_as_the_connection(error, network):
    assert discovery.connectivity.looks_like_network_failure(error) is network
