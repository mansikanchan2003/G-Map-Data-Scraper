import pytest
from fastapi.testclient import TestClient
from src.main import app
from src.database import get_db, Base
from src.models import *
from src.models.run_log import RunLog
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from datetime import datetime, timezone, timedelta

# In-memory DB setup
SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"
engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()

app.dependency_overrides[get_db] = override_get_db

@pytest.fixture(autouse=True)
def setup_db():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)

@pytest.fixture
def client():
    return TestClient(app)

def test_runs_endpoint_empty(client):
    res = client.get("/api/v1/runs")
    assert res.status_code == 200
    data = res.json()
    assert "total" in data
    assert "items" in data

def test_export_endpoint_empty(client):
    res = client.get("/api/v1/export/businesses?format=json")
    assert res.status_code == 200
    data = res.json()
    assert "items" in data
    assert "export_metadata" in data
    assert isinstance(data["items"], list)

def test_export_endpoint_csv(client):
    res = client.get("/api/v1/export/businesses?format=csv")
    assert res.status_code == 200
    assert res.headers["content-type"] == "text/csv; charset=utf-8"
    csv_content = res.text
    assert "email,website,category,district,state,verified" in csv_content

def test_businesses_endpoint_pagination(client):
    res = client.get("/api/v1/businesses")
    assert res.status_code == 200
    data = res.json()
    assert "total" in data
    assert data["page_size"] == 100

def test_stats_endpoint(client):
    res = client.get("/api/v1/stats")
    assert res.status_code == 200
    data = res.json()
    assert "jobs" in data
    assert "businesses" in data
    assert "pending" in data["jobs"]


# --- Batch cancellation -----------------------------------------------------
# /discovery/stop used to only return a message; stopping a batch really meant
# restarting the backend, which would also kill anything else in the process
# (a WhatsApp campaign mid-send, for instance). The batch now checks its own
# run row between jobs and winds down cleanly.

def test_stop_endpoint_marks_the_active_run_cancelling():
    import inspect
    from src.routers import discovery

    source = inspect.getsource(discovery.stop_discovery)
    assert "CANCELLING" in source, "stop must record the request somewhere the batch can see"
    assert "RunLog" in source, "stop must target the active run"


def test_batch_checks_for_cancellation_between_jobs():
    import inspect
    from src.routers import discovery

    # run_batch_discovery only dispatches; the batch itself is _run_batch
    source = inspect.getsource(discovery._run_batch)
    loop_at = source.index("for job in pending_jobs:")
    execute_at = source.index("job_manager.execute_single_job")
    check_at = source.index('run_log.status == "CANCELLING"')

    assert loop_at < check_at < execute_at, (
        "the cancellation check must run inside the loop and before the next job starts"
    )


def test_run_status_ignores_per_job_advisories():
    """
    `errors` collects per-job notes like "Enrichment partial failures", which
    only mean a website yielded no email. Counting those as failure marked
    every successful batch FAILED on the dashboard.
    """
    import inspect
    from src.routers import discovery

    # run_batch_discovery only dispatches; the batch itself is _run_batch
    source = inspect.getsource(discovery._run_batch)
    status_block = source[source.index("batch_error = any("):]
    status_block = status_block[:status_block.index("run_log.jobs_attempted")]

    assert 'run_log.status = "COMPLETED"' in status_block
    assert "batch_error" in status_block, "only a batch-level exception is a real failure"
    assert 'run_log.status = "PARTIAL"' in status_block, "some jobs failing is partial, not failed"
