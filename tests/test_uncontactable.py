"""
A business with neither a phone nor an email is never shown, and never kept.

A website-only listing is saved before its email is looked for, so for a
minute or two it has neither. Seen in that window it reads as a broken
record; and a job cut off in that window — one was, by a deploy — never
comes back to delete it.
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.database import Base, get_db
from src.main import app
from src.models import Business, Category, Job, Location
from src.services import job_manager

engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False},
                       poolclass=StaticPool)
Session = sessionmaker(bind=engine)
Base.metadata.create_all(bind=engine)


def business(key, job_id, phone=None, email=None, website="https://example.in"):
    return Business(business_id=key, job_id=job_id, name=f"Shop {key}", phone=phone, email=email,
                    website=website, category="Bank", source_query="q", dedup_key=key)


@pytest.fixture
def db():
    s = Session()
    for model in (Business, Job, Location, Category):
        s.query(model).delete()
    s.add(Location(location_id="loc", pincode="140001", latitude=30.0, longitude=75.0))
    s.add(Category(category_id="cat", category_name="Bank"))
    s.add(Job(job_id="done", location_id="loc", category_id="cat", status="COMPLETED", search_query="q"))
    s.add(Job(job_id="live", location_id="loc", category_id="cat", status="RUNNING", search_query="q"))
    s.add_all([
        business("phone", "done", phone="+919876543210"),
        business("email", "done", email="shop@example.in"),
        business("stranded", "done"),            # its job ended without cleaning up
        business("blank", "done", phone="", email=""),
        business("waiting", "live"),             # its job is still looking for an email
    ])
    s.commit()
    yield s
    s.rollback()
    s.close()


def test_leftovers_of_a_finished_job_are_removed_but_not_a_running_ones(db):
    assert job_manager.drop_uncontactable(db) == 2
    left = {b.business_id for b in db.query(Business)}
    assert left == {"phone", "email", "waiting"}
    assert job_manager.drop_uncontactable(db) == 0


def test_a_row_still_waiting_for_its_email_is_not_shown(db):
    app.dependency_overrides[get_db] = lambda: db
    try:
        client = TestClient(app)
        listed = client.get("/api/v1/businesses").json()
        stats = client.get("/api/v1/stats").json()
    finally:
        app.dependency_overrides.pop(get_db, None)
    assert listed["total"] == 2
    assert {b["name"] for b in listed["items"]} == {"Shop phone", "Shop email"}
    assert stats["businesses"]["total"] == 2


def test_search_finds_the_kind_of_business_and_the_place(db):
    db.add_all([
        Business(business_id="k1", job_id="done", name="Sharma Store", phone="+919811111111", category="Kiosk",
                 district="Agra", state="Uttar Pradesh", source_query="q", dedup_key="k1"),
        Business(business_id="k2", job_id="done", name="Patel Seva", phone="+919822222222", category="Kiosk",
                 district="Rajkot", state="Gujarat", source_query="q", dedup_key="k2"),
    ])
    db.commit()
    app.dependency_overrides[get_db] = lambda: db
    try:
        client = TestClient(app)
        found = lambda **p: {{"Sharma Store": "k1", "Patel Seva": "k2"}[b["name"]] for b in client.get("/api/v1/businesses", params=p).json()["items"]}
        assert found(search="Kiosk", state="Uttar Pradesh") == {"k1"}
        assert found(search="kiosk") == {"k1", "k2"}
        assert found(search="Kiosk Rajkot") == {"k2"}
        assert found(search="9822222222") == {"k2"}
        assert found(search="  ", state="uttar pradesh") == {"k1"}
    finally:
        app.dependency_overrides.pop(get_db, None)
