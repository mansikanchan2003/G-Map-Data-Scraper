"""
Partner organisations: searched at SBI branch PINs only, and kept apart from
the businesses that campaigns invite.
"""
import uuid

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.database import Base
from src.models import Business, Category, Job, Location, SbiBranch
from src.models.business import CONTACTABLE, NOT_PARTNER
from src.services import job_manager, partners


@pytest.fixture
def db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    s = sessionmaker(bind=engine)()
    s.add(Location(location_id="LBRANCH", pincode="360050", latitude=22.0, longitude=71.2, district="Rajkot", state="Gujarat"))
    s.add(Location(location_id="LOTHER", pincode="110001", latitude=28.6, longitude=77.2, district="New Delhi", state="Delhi"))
    s.add(SbiBranch(branch_code="1234", branch_name="JASDAN", pincode="360050", state="Gujarat"))
    s.add(Category(category_id="CSHOP", category_name="Copy shop"))
    s.commit()
    yield s
    s.close()


def test_partner_categories_are_searched_at_branch_pins_only(db):
    made = partners.ensure_jobs(db)
    assert made["created"] == len(partners.PARTNER_CATEGORIES)
    pins = {j.location.pincode for j in db.query(Job).all()}
    assert pins == {"360050"}
    # The ordinary job generation leaves them out, so they never spread to every PIN.
    job_manager.generate_jobs(db)
    partner_ids = [c.category_id for c in partners.ensure_categories(db)]
    other = db.query(Job).filter(Job.location_id == "LOTHER", Job.category_id.in_(partner_ids)).count()
    assert other == 0
    # Running again makes nothing new.
    assert partners.ensure_jobs(db)["created"] == 0


def _business(db, name, category, location_id, phone):
    job_id = uuid.uuid4().hex[:16]
    db.add(Job(job_id=job_id, location_id=location_id, category_id="CSHOP", search_query="q"))
    db.add(Business(business_id=uuid.uuid4().hex[:16], job_id=job_id, name=name, category=category,
                    phone=phone, source_query="q", dedup_key=uuid.uuid4().hex))
    db.commit()


def test_partners_have_their_own_list_and_stay_out_of_business_data(db):
    partners.ensure_categories(db)
    _business(db, "RSETI Rajkot", "Rural Self Employment Training Institute", "LBRANCH", "+919800000001")
    _business(db, "Seva NGO", "Non-governmental organization", "LBRANCH", "+919800000002")
    _business(db, "Raj Copy", "Copy shop", "LBRANCH", "+919800000003")

    listed = partners.list_partners(db)
    assert sorted(p["name"] for p in listed["partners"]) == ["RSETI Rajkot", "Seva NGO"]
    assert listed["partners"][0]["branches"] == [{"code": "1234", "name": "JASDAN"}]
    assert [p["name"] for p in partners.list_partners(db, kind="Non-governmental organization")["partners"]] == ["Seva NGO"]

    business_data = [b.name for b in db.query(Business).filter(CONTACTABLE, NOT_PARTNER).all()]
    assert business_data == ["Raj Copy"]


def test_a_campaign_audience_never_includes_partners(db):
    from src.routers.audience import AudienceFilters, _build
    partners.ensure_categories(db)
    _business(db, "Seva NGO", "Non-governmental organization", "LBRANCH", "+919800000002")
    _business(db, "Raj Copy", "Copy shop", "LBRANCH", "+919800000003")
    summary, contacts = _build(db, AudienceFilters(branches=["1234"]), True)
    assert [c["name"] for c in contacts] == ["Raj Copy"]
