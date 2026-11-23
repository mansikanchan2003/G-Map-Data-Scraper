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
    assert counts == {"CSP": 1, "CSP_NEAR_DC": 0, "DC": 1, "STATE_HEAD": 1}


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


def test_a_campaign_audience_can_be_picked_by_kind_of_business(db, client):
    """17 Nov 2026: the audience picker offers the kinds of business, with counts."""
    from src.routers.audience import AudienceFilters, _build
    _three(db)
    db.add(Business(business_id="kiosk", job_id="j", name="Shop kiosk", phone="+919844444444", category="Kiosk",
                    district="Rajkot", state="Gujarat", source_query="q", dedup_key="kiosk"))
    db.commit()
    kinds = {o["value"]: o["businesses"] for o in client.get("/api/v1/whatsapp/audience/options").json()["categories"]}
    assert kinds == {"Insurance agency": 1, "Kiosk": 1}          # the DC and State Head shops are not counted
    _, contacts = _build(db, AudienceFilters(categories=["Kiosk"]), True)
    assert [c["name"] for c in contacts] == ["Shop kiosk"]
    _, every = _build(db, AudienceFilters(), True)
    assert sorted(c["name"] for c in every) == ["Shop csp", "Shop kiosk"]


def test_business_data_shows_a_pin_code(db, client):
    """17 Nov 2026: the PIN in the Maps address, else the searched place's PIN."""
    from src.services.business_pin import from_address
    assert from_address("Shop 4, Jagat Circle, Kalaburagi, Karnataka 585102") == "585102"
    assert from_address("8RMP+7FR, opp. Bus Stand, Rajkot") is None
    assert from_address("Plot 12, 3rd floor, 380 015 Ahmedabad") == "380015"
    _three(db)
    db.query(Business).filter(Business.business_id == "csp").update({"address": "Main Rd, Rajkot, Gujarat 360005"})
    db.commit()
    rows = {r["name"]: r["pincode"] for r in client.get("/api/v1/businesses").json()["items"]}
    assert rows["Shop csp"] == "360005"          # from its address
    assert rows["Shop dc"] == "360001"           # the searched place's PIN
    out = client.get("/api/v1/export/businesses", params={"format": "csv", "hiring_for": "CSP"}).content.decode("utf-8-sig")
    head, first = list(csv.reader(io.StringIO(out)))[:2]
    assert first[head.index("pincode")] == "360005"


def test_csps_near_dcs_are_an_audience_of_their_own(db, client):
    """17 Nov 2026: Who to message: CSPs, CSPs near DCs, DCs or State Heads; each only its own label."""
    from src.routers.audience import AudienceFilters, _build
    from src.services.job_manager import _hiring_flags
    _three(db)
    _business(db, "near", "+919855555555", **_hiring_flags("CSP_NEAR_DC"))
    db.commit()
    names = lambda who: sorted(c["name"] for c in _build(db, AudienceFilters(hiring_for=who), True)[1])  # noqa: E731
    assert names("CSP") == ["Shop csp"]                 # the CSPs near DCs are not in the CSP audience
    assert names("CSP_NEAR_DC") == ["Shop near"]
    assert names("DC") == ["Shop dc"]
    assert names("STATE_HEAD") == ["Shop head"]
    states = client.get("/api/v1/whatsapp/audience/options", params={"hiring_for": "CSP_NEAR_DC"}).json()["states"]
    assert [(s["value"], s["businesses"]) for s in states] == [("Gujarat", 1)]
    # Business Data lists the type with its own count, and filters by it.
    counts = {t["type"]: t["count"] for t in client.get("/api/v1/businesses/types").json()}
    assert counts["CSP_NEAR_DC"] == 1
    rows = client.get("/api/v1/businesses", params={"hiring_for": "CSP_NEAR_DC"}).json()["items"]
    assert [r["name"] for r in rows] == ["Shop near"] and rows[0]["hiring_for"] == ["CSP_NEAR_DC"]


def test_a_lead_near_an_sbi_csp_centre_is_labelled():
    from src.services.applications import _near_centre
    centres = [{"name": "Baragarh (CISBI 340526)", "code": "CISBI 340526", "coords": (30.53, 77.18)}]
    hit = _near_centre(centres, [30.50, 77.15])
    assert hit and hit["code"] == "CISBI 340526" and hit["distance_km"] < 10
    assert _near_centre(centres, [30.90, 74.60]) is None        # Firozpur, far away
    assert _near_centre([], [30.50, 77.15]) is None


def test_dc_data_counts_only_dc_leads_by_state_district_category_and_day(db, client):
    """23 Nov 2026: Biswajit Sir's DC Data tab."""
    _three(db)
    _business(db, "dc2", "+919844444444", for_csp=False, for_dc=True, email="a@b.in")
    db.add(Business(business_id="dc3", job_id="j", name="Shop dc3", phone="+919855555555", category="Manpower consultancy",
                    district="Ludhiana", state="Punjab", source_query="q", dedup_key="dc3", for_csp=False, for_dc=True))
    db.commit()
    s = client.get("/api/v1/businesses/dc-summary").json()
    assert (s["total"], s["today"], s["last_7_days"]) == (3, 3, 3)
    assert (s["with_phone"], s["with_email"], s["with_website"]) == (3, 1, 0)
    assert [(st["state"], st["count"]) for st in s["states"]] == [("Gujarat", 2), ("Punjab", 1)]
    assert s["states"][0]["districts"] == [{"district": "Rajkot", "count": 2}]
    assert {c["category"]: c["count"] for c in s["categories"]} == {"Insurance agency": 2, "Manpower consultancy": 1}
    assert len(s["daily"]) == 30 and s["daily"][-1]["count"] == 3 and sum(d["count"] for d in s["daily"]) == 3
    assert client.get("/api/v1/businesses/dc-summary", params={"days": 7}).json()["daily"].__len__() == 7
