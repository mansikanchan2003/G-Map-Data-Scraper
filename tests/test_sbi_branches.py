"""
SBI branch PINs: branches from the bank's list, each PIN a target location.

The Configuration page shows these PINs in a section of their own, with the
branches they serve; for scraping they are ordinary locations with jobs.
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.database import Base, get_db
from src.main import app
from src.models import Category, Job, Location, SbiBranch
from src.services import config_loader

engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

CHOTILA = {"branch_code": "60104", "branch_name": "CHOTILA", "pincode": "363520", "ifsc": "SBIN0060104",
           "town": "Chotila", "district": "Surendranagar", "state": "Gujarat", "module": "AO Ahmedabad"}
THANGADH = {"branch_code": "60111", "branch_name": "THANGADH", "pincode": "363530", "ifsc": "SBIN0060111",
            "town": "Thangadh", "district": "Surendranagar", "state": "Gujarat"}


@pytest.fixture
def client(monkeypatch):
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    db.add_all([Category(category_id="c1", category_name="Copy shop"),
                Category(category_id="c2", category_name="Kiosk")])
    db.commit()
    db.close()
    placed = {"363520": (22.42, 71.19), "363530": (22.56, 71.19)}
    monkeypatch.setattr(config_loader, "_geocode_pin",
                        lambda pin, state: placed.get(pin, "the PIN code could not be found on the map"))

    def override():
        s = TestingSessionLocal()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db] = override
    yield TestClient(app)
    app.dependency_overrides.pop(get_db, None)


def test_branches_become_locations_with_jobs(client):
    r = client.post("/api/v1/config/branch-pins", json={"branches": [CHOTILA, THANGADH]})
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["branches_saved"] == 2 and sorted(out["pins_created"]) == ["363520", "363530"]
    assert out["jobs"]["created"] == 4  # 2 PINs x 2 categories

    db = TestingSessionLocal()
    loc = db.query(Location).filter_by(pincode="363520").one()
    assert (loc.district, loc.state, loc.anchor_name, loc.source_dataset) == ("Surendranagar", "Gujarat", "Chotila", "sbi_branches")
    assert db.query(Job).filter_by(location_id=loc.location_id).count() == 2
    db.close()


def test_the_section_lists_each_pin_with_its_branches(client):
    second = {**CHOTILA, "branch_code": "99999", "branch_name": "CHOTILA BAZAR"}
    client.post("/api/v1/config/branch-pins", json={"branches": [CHOTILA, second, THANGADH]})
    pins = {p["pincode"]: p for p in client.get("/api/v1/config/branch-pins").json()}
    assert sorted(b["branch_code"] for b in pins["363520"]["branches"]) == ["60104", "99999"]
    assert pins["363520"]["location"]["anchor_name"] == "Chotila"
    assert pins["363520"]["branches"][0]["module"] == "AO Ahmedabad"
    assert pins["363530"]["jobs"] == {"total": 2, "completed": 0, "pending": 2, "failed": 0}


def test_an_existing_pin_is_reused_and_adding_again_changes_nothing(client):
    client.post("/api/v1/config/branch-pins", json={"branches": [CHOTILA]})
    again = client.post("/api/v1/config/branch-pins", json={"branches": [{**CHOTILA, "note": "checked"}]}).json()
    assert again["pins_created"] == [] and again["jobs"] == {"created": 0, "existing": 2}
    db = TestingSessionLocal()
    assert db.query(Location).filter_by(pincode="363520").count() == 1
    assert db.get(SbiBranch, "60104").note == "checked"
    db.close()


def test_a_pin_off_the_map_keeps_its_branch_and_says_why(client):
    lost = {**CHOTILA, "branch_code": "1", "pincode": "999999"}
    out = client.post("/api/v1/config/branch-pins", json={"branches": [lost]}).json()
    assert out["branches_saved"] == 1 and out["jobs"]["created"] == 0
    assert out["problems"][0]["pincode"] == "999999"
    pins = client.get("/api/v1/config/branch-pins").json()
    assert pins[0]["location"] is None and pins[0]["branches"][0]["branch_code"] == "1"


def test_a_malformed_pin_is_refused(client):
    r = client.post("/api/v1/config/branch-pins", json={"branches": [{**CHOTILA, "pincode": "36352"}]})
    assert r.status_code == 422
