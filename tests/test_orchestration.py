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
    res = client.get("/api/v1/export/businesses")
    assert res.status_code == 200
    data = res.json()
    assert "total" in data
    assert "export_metadata" in data

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
