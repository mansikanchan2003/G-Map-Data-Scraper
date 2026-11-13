# tests/test_foundation.py
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from src.main import app
from src.database import Base, get_db
from src.models import Location, Category, Job, Business, RunLog

# Use a test SQLite database file
# Its own file: other suites drop and recreate the tables in test.db.
SQLALCHEMY_DATABASE_URL = "sqlite:///test_foundation.db"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base.metadata.drop_all(bind=engine)
Base.metadata.create_all(bind=engine)

def override_get_db():
    try:
        db = TestingSessionLocal()
        yield db
    finally:
        db.close()


@pytest.fixture(autouse=True)
def _this_suites_db():
    """
    Points the app at this suite's database for each of its tests, and puts back
    whatever was there after. Set once at import instead, the override belonged to
    whichever test module pytest imported last, for the whole run.
    """
    before = app.dependency_overrides.get(get_db)
    app.dependency_overrides[get_db] = override_get_db
    yield
    if before is None:
        app.dependency_overrides.pop(get_db, None)
    else:
        app.dependency_overrides[get_db] = before

client = TestClient(app)

def test_health_check():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"

def test_sync_configuration():
    response = client.post("/api/v1/config/sync")
    assert response.status_code == 200
    data = response.json()
    assert data["locations"]["total_in_db"] > 0
    assert data["categories"]["total_in_db"] > 0

def test_generate_jobs():
    response = client.post("/api/v1/jobs/generate")
    assert response.status_code in (200, 201)
    data = response.json()
    assert data["total_jobs"] > 0

def test_idempotent_jobs():
    client.post("/api/v1/jobs/generate")
    response = client.post("/api/v1/jobs/generate")
    assert response.status_code in (200, 201)
    data = response.json()
    assert data["jobs_created"] == 0
    assert data["jobs_existing"] > 0


class TestForeignNumbersAreNotStored:
    """
    This project targets India, and a border district's search radius reaches
    into another country — a Gurdaspur search returned Narowal, Pakistan.
    Those listings are real but not contactable here, and storing their
    numbers makes the dataset look reachable when it is not.
    """

    def test_a_pakistani_number_is_dropped(self):
        from src.services.normalizer import normalize_phone
        assert normalize_phone("+923121483981") is None

    def test_any_foreign_code_is_dropped(self):
        from src.services.normalizer import normalize_phone
        for number in ("+18005551234", "+442071234567", "+8613800138000"):
            assert normalize_phone(number) is None, number

    def test_indian_numbers_are_kept_in_every_form(self):
        from src.services.normalizer import normalize_phone
        for raw in ("+919896555891", "919896555891", "9896555891",
                    "09896555891", "+91 98965 55891"):
            assert normalize_phone(raw) == "+919896555891", raw
