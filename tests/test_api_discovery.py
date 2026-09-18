import pytest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from src.main import app
from src.database import Base, get_db
from src.models import Location, Category, Job, Business

SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"
engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base.metadata.create_all(bind=engine)

def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()

@pytest.fixture(autouse=True)
def setup_db():
    app.dependency_overrides[get_db] = override_get_db
    yield
    app.dependency_overrides[get_db] = override_get_db

client = TestClient(app)

def test_api_run_job_endpoint():
    db = TestingSessionLocal()
    loc = Location(location_id="loc_api_01", pincode="110001", latitude=28.6304, longitude=77.2177, radius_km=20.0)
    cat = Category(category_id="cat_api_01", category_name="Travel Agency")
    job = Job(job_id="job_api_01", location_id="loc_api_01", category_id="cat_api_01", status="PENDING", search_query="https://maps.google.com")
    db.add_all([loc, cat, job])
    db.commit()
    db.close()

    mock_discovery_result = {
        "status": "success",
        "job_id": "job_api_01",
        "count": 1,
        "results": [
            {
                "name": "Delhi Tours",
                "address": "Connaught Place, New Delhi",
                "phone": "011 2334 5566",
                "website": "https://delhitours.com",
                "google_maps_url": "https://maps.google.com/place_delhi_tours",
                "place_id": "ChIJ_delhi_tours",
                "latitude": 28.6305,
                "longitude": 77.2178,
                "category": "Travel Agency"
            }
        ]
    }

    with patch("src.services.job_manager.GoogleMapsDiscoveryEngine.execute_discovery", return_value=mock_discovery_result):
        response = client.post("/api/v1/jobs/job_api_01/run")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["job_id"] == "job_api_01"
        assert data["businesses_saved"] == 1

def test_api_discovery_status_and_stop():
    res_status = client.get("/api/v1/discovery/status")
    assert res_status.status_code == 200
    assert "State is fully managed via PostgreSQL" in res_status.json()["message"]

    res_stop = client.post("/api/v1/discovery/stop")
    assert res_stop.status_code == 200
    assert "Draining is orchestrated externally" in res_stop.json()["message"]


def test_business_api_public_contract():
    """Verify GET /api/v1/businesses exposes exactly the 9 user-facing fields
    and does NOT expose the 3 internal email-enrichment fields."""
    db = TestingSessionLocal()
    loc = Location(location_id="loc_pub_01", pincode="560001", latitude=12.9716, longitude=77.5946, radius_km=20.0)
    cat = Category(category_id="cat_pub_01", category_name="Savings bank")
    job = Job(
        job_id="job_pub_01",
        location_id="loc_pub_01",
        category_id="cat_pub_01",
        status="COMPLETED",
        search_query="https://maps.google.com",
    )
    biz = Business(
        business_id="biz_pub_01",
        job_id="job_pub_01",
        name="Test Bank",
        address="123 MG Road, Bangalore",
        phone="08012345678",
        email="test@testbank.com",
        email_source_url="https://testbank.com/contact",
        email_enrichment_status="found",
        website="https://testbank.com",
        category="Savings bank",
        district="Bangalore Urban",
        state="Karnataka",
        is_valid=True,
        source_query="https://maps.google.com",
        dedup_key="pid:test_pub_01",
    )
    db.add_all([loc, cat, job, biz])
    db.commit()
    db.close()

    response = client.get("/api/v1/businesses?page=1&page_size=100")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] >= 1

    # Find the business we just seeded
    matches = [b for b in data["items"] if b.get("name") == "Test Bank"]
    assert len(matches) == 1, "Test Bank not found in /api/v1/businesses response"
    item = matches[0]

    # --- 9 user-facing fields MUST be present ---
    EXPECTED_FIELDS = {"name", "address", "phone", "email", "website",
                       "category", "district", "state", "verified"}
    for field in EXPECTED_FIELDS:
        assert field in item, f"Expected user-facing field '{field}' is missing"

    # --- 3 internal fields MUST be absent ---
    FORBIDDEN_FIELDS = {"email_source_url", "email_enrichment_status", "email_enriched_at"}
    for field in FORBIDDEN_FIELDS:
        assert field not in item, f"Internal field '{field}' must not be exposed in public API"

    # --- Verify values round-trip correctly ---
    assert item["name"] == "Test Bank"
    assert item["verified"] is True
    assert item["email"] == "test@testbank.com"


def test_business_detail_api_public_contract():
    """Verify GET /api/v1/businesses/{id} also follows the public contract."""
    response = client.get("/api/v1/businesses/biz_pub_01")
    assert response.status_code == 200
    item = response.json()

    EXPECTED_FIELDS = {"name", "address", "phone", "email", "website",
                       "category", "district", "state", "verified"}
    for field in EXPECTED_FIELDS:
        assert field in item, f"Expected user-facing field '{field}' is missing"

    FORBIDDEN_FIELDS = {"email_source_url", "email_enrichment_status", "email_enriched_at"}
    for field in FORBIDDEN_FIELDS:
        assert field not in item, f"Internal field '{field}' must not be exposed in public detail API"

    assert item["verified"] is True
