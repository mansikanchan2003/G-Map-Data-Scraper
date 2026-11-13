"""
Who a search hires for (13 Nov 2026): CSP (the autopilot's), District Coordinator
or State Head. DC and State Head searches are run by hand, their businesses carry
that label, CSP campaigns never reach them, and Business Data filters and exports
by it.
"""
import csv
import io
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.database import Base, get_db
from src.main import app
from src.models import Business, Category, Job, Location
from src.services import custom_target, discovery_autopilot, job_manager

engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
Session = sessionmaker(bind=engine)
Base.metadata.create_all(bind=engine)


@pytest.fixture
def db():
    s = Session()
    for model in (Business, Job, Location, Category):
        s.query(model).delete()
    s.add(Location(location_id="loc", pincode="360001", latitude=22.30, longitude=70.80,
                   district="Rajkot", state="Gujarat", tehsil="Rajkot", anchor_name="360001"))
    s.add(Category(category_id="cat", category_name="Insurance agency"))
    s.commit()
    yield s
    s.rollback()
    s.close()


@pytest.fixture
def client(db):
    # Put back whatever another suite set at import, rather than leave none.
    before = app.dependency_overrides.get(get_db)
    app.dependency_overrides[get_db] = lambda: db
    yield TestClient(app)
    if before is None:
        app.dependency_overrides.pop(get_db, None)
    else:
        app.dependency_overrides[get_db] = before


def _listing(name, phone, place):
    return {"name": name, "address": "Rajkot", "phone": phone, "website": None,
            "google_maps_url": f"https://maps.google.com/{place}", "place_id": place,
            "latitude": 22.301, "longitude": 70.801, "category": "Insurance agency"}


def _run(db, job_id, listings):
    eng = MagicMock()
    eng.execute_discovery.return_value = {"status": "success", "results": listings}
    return job_manager.execute_single_job(job_id, db, custom_engine=eng)


def test_a_dc_search_is_its_own_job_and_never_runs_on_its_own(db):
    loc, cat = db.get(Location, "loc"), db.get(Category, "cat")
    assert custom_target.generate_jobs_for(db, [loc], [cat])["jobs_created"] == 1
    assert custom_target.generate_jobs_for(db, [loc], [cat], "DC")["jobs_created"] == 1     # not the CSP job
    assert custom_target.generate_jobs_for(db, [loc], [cat], "DC")["jobs_created"] == 0
    kinds = sorted(j.hiring_for for j in db.query(Job))
    assert kinds == ["CSP", "DC"]
    # The autopilot and a plain batch see only the CSP job.
    assert discovery_autopilot.pending_by_state(db) == {"Gujarat": 1}
    from src.routers.discovery import BatchRequest, apply_target_filters
    plain = apply_target_filters(db.query(Job).filter(Job.status == "PENDING"), BatchRequest()).all()
    assert [j.hiring_for for j in plain] == ["CSP"]
    dc = apply_target_filters(db.query(Job).filter(Job.status == "PENDING"), BatchRequest(hiring_for="DC")).all()
    assert [j.hiring_for for j in dc] == ["DC"]


def test_businesses_carry_the_label_of_the_search_that_found_them(db):
    loc, cat = db.get(Location, "loc"), db.get(Category, "cat")
    custom_target.generate_jobs_for(db, [loc], [cat])
    custom_target.generate_jobs_for(db, [loc], [cat], "DC")
    csp_job = db.query(Job).filter(Job.hiring_for == "CSP").one().job_id
    dc_job = db.query(Job).filter(Job.hiring_for == "DC").one().job_id

    _run(db, csp_job, [_listing("Shah Insurance", "9811111111", "p1")])
    _run(db, dc_job, [_listing("Shah Insurance", "9811111111", "p1"),       # found again: now both
                      _listing("Mehta Advisors", "9822222222", "p2")])     # only by the DC search
    shah = db.query(Business).filter(Business.name == "Shah Insurance").one()
    mehta = db.query(Business).filter(Business.name == "Mehta Advisors").one()
    assert (shah.for_csp, shah.for_dc, shah.for_state_head) == (True, True, False)
    assert (mehta.for_csp, mehta.for_dc, mehta.for_state_head) == (False, True, False)


def _business(db, key, phone, **flags):
    db.add(Business(business_id=key, job_id="j", name=f"Shop {key}", phone=phone, category="Insurance agency",
                    district="Rajkot", state="Gujarat", source_query="q", dedup_key=key, **flags))


def _three(db):
    db.add(Job(job_id="j", location_id="loc", category_id="cat", status="COMPLETED", search_query="q"))
    _business(db, "csp", "+919811111111")                                       # found before: CSP
    _business(db, "dc", "+919822222222", for_csp=False, for_dc=True)
    _business(db, "head", "+919833333333", for_csp=False, for_state_head=True)
    db.commit()


def test_business_data_filters_by_type_and_counts_each(db, client):
    _three(db)
    names = lambda **p: sorted(b["name"] for b in client.get("/api/v1/businesses", params=p).json()["items"])  # noqa: E731
    assert names() == ["Shop csp", "Shop dc", "Shop head"]
    assert names(hiring_for="CSP") == ["Shop csp"]
    assert names(hiring_for="DC") == ["Shop dc"]
    assert names(hiring_for="STATE_HEAD") == ["Shop head"]
    rows = client.get("/api/v1/businesses", params={"hiring_for": "DC"}).json()["items"]
    assert rows[0]["hiring_for"] == ["DC"]
    assert client.get("/api/v1/businesses", params={"hiring_for": "NOPE"}).status_code == 400
    counts = {t["type"]: t["count"] for t in client.get("/api/v1/businesses/types").json()}
    assert counts == {"CSP": 1, "DC": 1, "STATE_HEAD": 1}


def test_the_export_holds_only_what_the_filter_shows(db, client):
    _three(db)
    r = client.get("/api/v1/export/businesses", params={"format": "csv", "hiring_for": "DC"})
    assert "businesses_export_dc.csv" in r.headers["content-disposition"]
    rows = list(csv.reader(io.StringIO(r.content.decode("utf-8-sig"))))
    assert rows[0][-1] == "type" and [row[0] for row in rows[1:]] == ["Shop dc"]
    assert rows[1][-1] == "District Coordinator"
    from openpyxl import load_workbook
    x = client.get("/api/v1/export/businesses", params={"format": "excel", "hiring_for": "STATE_HEAD"})
    ws = load_workbook(io.BytesIO(x.content)).active
    assert [r[0] for r in ws.iter_rows(min_row=2, values_only=True)] == ["Shop head"]
    every = client.get("/api/v1/export/businesses", params={"format": "csv"}).content.decode("utf-8-sig")
    assert every.count("Shop ") == 3


def test_csp_campaigns_never_reach_a_dc_or_state_head_search(db):
    from src.routers.audience import AudienceFilters, _build
    _three(db)
    _, contacts = _build(db, AudienceFilters(), True)
    assert [c["name"] for c in contacts] == ["Shop csp"]
