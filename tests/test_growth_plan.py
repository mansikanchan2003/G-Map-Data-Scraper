"""
The growth plan: leads against the goal, where people drop out, and what to
do next. Built from campaigns and conversations planted here, so each number
the plan reports can be checked against what was put in.
"""
import uuid
from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.database import Base
from src.models import (  # noqa: F401  (registers the tables on Base)
    Business, WhatsAppButtonClick, WhatsAppCampaign, WhatsAppCampaignRecipient, WhatsAppLinkClick,
    WhatsAppTemplate,
)
from src.models.category import Category
from src.models.inbox import WhatsAppConversation, WhatsAppMessage
from src.services import campaign_insights as ci
from src.services import growth_plan as gp
from src.services import onboarding_bot as bot

engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False},
                       poolclass=StaticPool)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base.metadata.create_all(bind=engine)

SENT = datetime(2026, 10, 14, 5, 0, tzinfo=timezone.utc)
SERVED = {"pincode": "360055", "served": True, "distance_km": 0.0}


@pytest.fixture
def db(monkeypatch):
    monkeypatch.setattr(gp, "today_ist", lambda: date(2026, 10, 22))
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        for model in (WhatsAppMessage, WhatsAppConversation, WhatsAppLinkClick, WhatsAppButtonClick,
                      WhatsAppCampaignRecipient, WhatsAppCampaign, WhatsAppTemplate, Business, Category):
            session.query(model).delete()
        session.commit()
        session.close()


def _phone(i):
    return f"+9198{i:08d}"


def campaign(db, n, district="Rajkot", category="Kiosk", angle="extra_income", start=0):
    """n businesses messaged; returns their phones."""
    t = WhatsAppTemplate(template_id=uuid.uuid4().hex, name=f"T-{angle}", body="नमस्कार " * 40,
                         status="APPROVED", header_type="IMAGE",
                         generation={"angle_key": angle, "layout": "banner",
                                     "poster": {"headline_line1": "Earn more", "headline_line2": "with SBI"}})
    c = WhatsAppCampaign(campaign_id=uuid.uuid4().hex, name=f"C-{district}", template_id=t.template_id,
                         data_source_type="scraped", status="COMPLETED", total_contacts=n)
    db.add_all([t, c])
    phones = []
    for i in range(start, start + n):
        phone = _phone(i)
        bid = uuid.uuid4().hex[:16]
        db.add(Business(business_id=bid, job_id="J", name="b", phone=phone, category=category,
                        district=district, state="Gujarat", source_query="q", dedup_key=bid))
        db.add(WhatsAppCampaignRecipient(recipient_id=uuid.uuid4().hex, campaign_id=c.campaign_id,
                                         business_id=bid, phone=phone, status="DELIVERED",
                                         sent_at=SENT, delivered_at=SENT))
        phones.append(phone)
    db.commit()
    return phones


def person(db, phone, step, submitted=False, **data):
    at = SENT + timedelta(minutes=30)
    db.add(WhatsAppConversation(phone=phone, profile_name=f"P{phone[-3:]}", bot_step=step, bot_data=data,
                                last_inbound_at=at, last_message_at=at, upload_token=f"tok{phone}" if step in (
                                    bot.AWAIT_UPLOAD, bot.SUBMITTED) else None,
                                documents_submitted_at=at if submitted else None))
    db.add(WhatsAppMessage(message_id=uuid.uuid4().hex, phone=phone, direction="IN", kind="button",
                           body="Interested", created_at=at))
    db.commit()


def qualified(**more):
    return {"coverage": SERVED, "education": "grad", "can_invest": True, **more}


def test_leads_are_counted_against_the_goal(db):
    phones = campaign(db, 40)
    person(db, phones[0], bot.SUBMITTED, submitted=True, **qualified())
    person(db, phones[1], bot.AWAIT_UPLOAD, **qualified())
    g = gp.goal(db, gp._people(db), ci.load_facts(db))
    assert (g["target"], g["leads"], g["still_needed"]) == (10, 1, 9)
    assert g["days_left"] == 10                     # 22 to 31 October, both days counted
    assert g["per_day_needed"] == 0.9
    assert g["leads_per_1000"] == 25.0 and g["messages_needed"] == 360


def test_the_teams_own_tests_are_not_leads(db):
    phones = campaign(db, 40)
    # The team's number was also sent a test campaign, of under ten people.
    test = WhatsAppCampaign(campaign_id="TEST", name="Test", data_source_type="upload",
                            status="COMPLETED", total_contacts=1)
    db.add(test)
    db.add(WhatsAppCampaignRecipient(recipient_id="RT", campaign_id="TEST", phone=phones[0],
                                     status="READ", sent_at=SENT))
    db.commit()
    person(db, phones[0], bot.SUBMITTED, submitted=True, **qualified())
    assert gp.goal(db)["leads"] == 0


def test_the_funnel_finds_where_people_stop(db):
    phones = campaign(db, 40)
    for p in phones[:4]:                 # said they cannot invest
        person(db, p, bot.NOT_INVESTING, coverage=SERVED, education="grad", can_invest=False)
    for p in phones[4:6]:                # not answered yet: still deciding
        person(db, p, bot.AWAIT_INVEST, coverage=SERVED, education="grad")
    person(db, phones[6], bot.AWAIT_UPLOAD, **qualified())
    f = gp.funnel(db, gp._people(db), ci.load_facts(db))
    steps = {s["key"]: s for s in f["steps"]}
    assert (steps["interested"]["count"], steps["education_ok"]["count"], steps["can_invest"]["count"]) == (7, 7, 1)
    assert steps["can_invest"]["waiting"] == 2
    assert steps["can_invest"]["from_previous"] == 0.2          # 1 of the 5 who answered
    leak = f["biggest_leak"]
    assert (leak["step"], leak["from"], leak["to"]) == ("can_invest", 5, 1)
    assert "₹5 lakh" in leak["advice"]


def test_people_part_way_are_listed_to_call_furthest_first(db):
    phones = campaign(db, 40)
    person(db, phones[0], bot.AWAIT_INVEST, coverage=SERVED, education="12")
    person(db, phones[1], bot.AWAIT_UPLOAD, **qualified())
    person(db, phones[2], bot.NOT_INVESTING, coverage=SERVED, education="12", can_invest=False)
    person(db, phones[3], bot.SUBMITTED, submitted=True, **qualified())
    warm = gp.warm_people(gp._people(db))
    assert [w["phone"] for w in warm] == [phones[1], phones[0]]


def test_an_outcome_is_credited_to_the_campaign_they_answered(db):
    first = campaign(db, 30, angle="extra_income")
    # The same people, messaged again later with another angle.
    campaign(db, 30, angle="community_respect")
    rows = db.query(WhatsAppCampaignRecipient).filter(WhatsAppCampaignRecipient.phone == first[0]).all()
    later = SENT + timedelta(hours=2)
    for r in rows:
        if r.campaign.template.generation["angle_key"] == "community_respect":
            r.sent_at = later
    db.commit()
    person(db, first[0], bot.SUBMITTED, submitted=True, **qualified())    # wrote back before the second
    facts = ci.load_facts(db)
    credited = [f for f in facts if f["lead"]]
    assert len(credited) == 1 and credited[0]["angle"] == "extra income"


def test_the_plan_judges_on_the_furthest_stage_with_enough_data(db):
    phones = campaign(db, 60)
    for p in phones[:12]:
        person(db, p, bot.AWAIT_EDUCATION, coverage=SERVED)
    plan = gp.plan(db)
    assert plan["judged_on"] == "interested"       # 12 started; none qualified yet
    assert plan["next_steps"], "always something to do"


def test_targets_offer_businesses_not_yet_messaged(db):
    campaign(db, 40, district="Rajkot", category="Kiosk")
    person(db, _phone(0), bot.AWAIT_EDUCATION, coverage=SERVED)
    # Businesses nobody has messaged yet.
    for i in range(1000, 1025):
        bid = uuid.uuid4().hex[:16]
        db.add(Business(business_id=bid, job_id="J", name="b", phone=_phone(i), category="Travel agent",
                        district="Surat", state="Gujarat", source_query="q", dedup_key=bid))
    db.commit()
    book = ci.playbook(db)
    book["_facts"] = ci.load_facts(db)
    t = gp.targets(db, book)
    assert any(c["name"] == "Travel agent" and c["confidence"] == "untried" and c["left"] == 25
               for c in t["categories"])
    assert t["reachable_left"] == 25


def test_the_agents_are_told_the_goal(db):
    phones = campaign(db, 40)
    person(db, phones[0], bot.SUBMITTED, submitted=True, **qualified())
    brief = gp.agent_brief(db)
    assert "Target: 10 leads by 2026-10-31; we have 1" in brief
    assert "extra income" in brief


def test_delivery_is_measured_only_where_meta_reported(db):
    # An old campaign, sent before delivery reports were recorded, with one
    # report that came in later; then a newer one with reports.
    old = campaign(db, 100, start=500)
    for r in db.query(WhatsAppCampaignRecipient).filter(WhatsAppCampaignRecipient.phone.in_(old)):
        r.sent_at, r.delivered_at = SENT - timedelta(days=20), None
    first = db.query(WhatsAppCampaignRecipient).filter(WhatsAppCampaignRecipient.phone == old[0]).one()
    first.delivered_at = SENT - timedelta(days=5)
    db.commit()
    campaign(db, 40)                       # all 40 delivered
    steps = {s["key"]: s for s in gp.funnel(db, gp._people(db), ci.load_facts(db))["steps"]}
    assert steps["delivered"]["of_tracked"] == 40
    assert steps["delivered"]["from_previous"] == 1.0
