import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from src.database import Base
from src.models import Job, Business, RunLog, Location, Category
from src.services.job_manager import recover_stale_jobs, auto_retry_failed_jobs
from datetime import datetime, timezone, timedelta

@pytest.fixture
def test_db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    # Import all models to ensure metadata has all tables
    import src.models
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    yield db
    db.close()
    # No drop_all needed for in-memory SQLite, avoids metadata side-effects

def test_recover_stale_jobs(test_db):
    now = datetime.now(timezone.utc)
    
    j1 = Job(job_id="1", location_id="l1", category_id="c1", status="RUNNING", last_attempt_at=now - timedelta(minutes=40), search_query="")
    j2 = Job(job_id="2", location_id="l1", category_id="c2", status="RUNNING", last_attempt_at=now - timedelta(minutes=10), search_query="")
    j3 = Job(job_id="3", location_id="l1", category_id="c3", status="PENDING", last_attempt_at=now - timedelta(minutes=40), search_query="")
    
    test_db.add_all([j1, j2, j3])
    test_db.commit()

    res = recover_stale_jobs(test_db, max_age_minutes=30)
    assert res["recovered_count"] == 1
    
    test_db.refresh(j1)
    test_db.refresh(j2)
    assert j1.status == "PENDING"
    assert j2.status == "RUNNING"

def test_auto_retry_failed_jobs(test_db):
    j1 = Job(job_id="1", location_id="l1", category_id="c1", status="FAILED", attempt_count=1, search_query="")
    j2 = Job(job_id="2", location_id="l1", category_id="c2", status="FAILED", attempt_count=3, search_query="")
    j3 = Job(job_id="3", location_id="l1", category_id="c3", status="BLOCKED", attempt_count=1, search_query="")
    
    test_db.add_all([j1, j2, j3])
    test_db.commit()

    res = auto_retry_failed_jobs(test_db, max_retries=3)
    assert res["retried_count"] == 1
    
    test_db.refresh(j1)
    test_db.refresh(j2)
    assert j1.status == "PENDING"
    assert j2.status == "FAILED"

def test_maintenance_endpoint(test_db):
    from src.routers.jobs import run_maintenance
    
    now = datetime.now(timezone.utc)
    j1 = Job(job_id="10", location_id="l1", category_id="c1", status="RUNNING", last_attempt_at=now - timedelta(minutes=40), search_query="")
    j2 = Job(job_id="11", location_id="l1", category_id="c2", status="FAILED", attempt_count=2, search_query="")
    
    test_db.add_all([j1, j2])
    test_db.commit()
    
    # Call router function directly to avoid global app.dependency_overrides side-effects
    result = run_maintenance(max_stale_age_minutes=30, max_retries=3, db=test_db)
    
    assert result["status"] == "success"
    assert result["recovered_stale_jobs"] == 1
    assert result["auto_retried_jobs"] == 1
    
    test_db.refresh(j1)
    test_db.refresh(j2)
    assert j1.status == "PENDING"
    assert j2.status == "PENDING"
