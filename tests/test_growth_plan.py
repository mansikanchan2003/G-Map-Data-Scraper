"""
The growth plan: leads against the goal, where people drop out, and what to
do next. Built from campaigns and conversations planted here, so each number
the plan reports can be checked against what was put in.
"""
import json
import math
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
from src.models.app_setting import AppSetting
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


# What scripts/export_business_context.py writes, cut down: three months of a
# network of about 500 CSPs, a few new ones a month, and the onboarding sheet.
CONTEXT = {
    "exported_at": "2026-10-14T12:00:00+00:00",
    "csp_network": {
        "terminal_status": {"Active": 489, "Inactive": 47},
        "commission_by_month": {"2026-07": {"csps": 496, "inr": 8509042}},
        "activity_by_month": {"2026-07": {"csps": 494, "txns": 331556}, "2026-08": {"csps": 491, "txns": 306546},
                              "2026-09": {"csps": 492, "txns": 306176}, "2026-10": {"csps": 477, "txns": 139624}},
        "new_csps_by_first_month": {"2026-08": 7, "2026-09": 2},
        "new_csp_ramp": {"2026-08": {"2026-08": {"csps": 7, "median_txns": 29}, "2026-09": {"csps": 7, "median_txns": 99}}},
        "established_median_txns": {"2026-07": 479, "2026-08": 454, "2026-09": 451, "2026-10": 206},
    },
    "revenue_forecasts": {"Sep-26": {"actual_inr": 8331188, "txns": 305965},
                          "Oct-26": {"projected_inr": 8768364, "txns": 139666}},
    "onboarding": {
        "applicants": {"total": 148, "went_live": 61, "rejected": 36, "in_progress": 51,
                       "by_status": {"Go live done": 61, "Hard Copy Rejected by branch": 16}},
        "go_live_by_month": {"2026-09": 4, "2026-10": 5},
        "this_month_by_state": [{"state": "Gujarat", "target": 43, "leads": 0, "cat1": 0, "cat2": 0, "go_live": 0, "rejected": 0},
                                {"state": "Bihar", "target": 5, "leads": 5, "cat1": 0, "cat2": 5, "go_live": 0, "rejected": 0}],
    },
}


@pytest.fixture
def context(tmp_path, monkeypatch):
    from src.services import business_context
    path = tmp_path / "business_context.json"
    path.write_text(json.dumps(CONTEXT), encoding="utf-8")
    monkeypatch.setattr(business_context, "CONTEXT_FILE", str(path))
    return path


@pytest.fixture
def db(monkeypatch, tmp_path):
    from src.services import business_context
    monkeypatch.setattr(gp, "today_ist", lambda: date(2026, 10, 22))
    # No business data unless a test asks for it.
    monkeypatch.setattr(business_context, "CONTEXT_FILE", str(tmp_path / "none.json"))
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        for model in (WhatsAppMessage, WhatsAppConversation, WhatsAppLinkClick, WhatsAppButtonClick,
                      WhatsAppCampaignRecipient, WhatsAppCampaign, WhatsAppTemplate, Business, Category, AppSetting):
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


def test_leads_this_month_are_counted_against_the_agents_goal(db, context):
    phones = campaign(db, 40)
    person(db, phones[0], bot.SUBMITTED, submitted=True, **qualified())
    person(db, phones[1], bot.AWAIT_UPLOAD, **qualified())
    g = gp.goal(db, gp._people(db), ci.load_facts(db))
    # 7 and 4 went live in Aug and Sep: 5.5 a month. Half as many again is 3,
    # and with 61 of 97 decided applicants going live, 3 need 5 leads.
    assert (g["target"], g["extra_csps"], g["leads"], g["still_needed"]) == (5, 3, 1, 4)
    assert g["set_by"] == "agent" and g["label"] == "Oct 2026"
    assert g["days_left"] == 10                     # 22 to 31 October, both days counted
    assert g["per_day_needed"] == 0.4
    assert any("Gujarat 0 leads of 43" in r for r in g["reasoning"])


def test_last_months_leads_do_not_count_towards_this_month(db, context):
    phones = campaign(db, 40)
    person(db, phones[0], bot.SUBMITTED, submitted=True, **qualified())
    c = db.query(WhatsAppConversation).filter(WhatsAppConversation.phone == phones[0]).one()
    c.documents_submitted_at = datetime(2026, 9, 28, 6, 0, tzinfo=timezone.utc)
    db.commit()
    assert gp.goal(db)["leads"] == 0


def test_without_business_data_the_goal_is_modest(db):
    g = gp.goal(db)
    assert g["target"] == 3 and g["basis"] == "own results only"


def test_the_business_is_summarised_from_onboarding_to_revenue():
    from src.services import business_context as bc
    s = bc.summarise(CONTEXT)
    months = {r["month"]: r for r in s["months"]}
    assert months["2026-07"]["new_csps"] is None          # Tara's first month: new and old look alike
    assert (months["2026-08"]["new_csps"], months["2026-09"]["new_csps"], months["2026-10"]["new_csps"]) == (7, 4, 5)
    assert months["2026-09"]["revenue_basis"] == "actual" and months["2026-08"]["revenue_basis"] == "estimated"
    assert s["revenue_per_txn"] == 27.23
    assert s["onboarding"]["go_live_rate"] == 0.629
    assert [r["median_txns"] for r in s["new_csp_ramp"]] == [29, 99]
    # Seven new CSPs at 99 transactions are a sliver of September's revenue.
    sep = next(c for c in s["new_csps_contribution"] if c["month"] == "2026-09")
    assert sep["from_new_csps_inr"] == round(7 * 99 * (8331188 / 305965)) and sep["share"] < 0.01


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


def test_the_agents_are_told_the_process_and_their_goal(db, context):
    phones = campaign(db, 40)
    person(db, phones[0], bot.SUBMITTED, submitted=True, **qualified())
    brief = gp.agent_brief(db)
    assert brief.startswith("HOW EKO EARNS, from a lead to revenue.")
    assert "Your goal for Oct 2026, which you set from the numbers above: 5 leads; we have 1" in brief
    assert "extra income" in brief
    # The plan's next steps reach the agent, but not the call list's names.
    assert "WHAT TO DO NEXT" in brief and "Try a new kind of template" in brief
    assert "Call the" not in brief


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


def test_a_revenue_goal_is_a_total_between_two_dates(db, context):
    from src.services import business_context as bc
    bc.set_revenue_goal(db, 10_000_000, "2026-10-15", "2026-12-31")   # ₹1 Cr in total by 31 December
    g = gp.goal(db)                                                      # "today" is 22 October
    money = g["revenue"]
    daily = 8768364 / 31                                                 # October's projection, a day
    # Counted to yesterday: 7 days since the 15th.
    assert money["as_of"] == "2026-10-21" and money["earned_inr"] == round(daily * 7)
    assert money["expected_inr"] == round(daily * 78) and money["on_course"]
    assert money["reached_on"] == "2026-11-19"
    # On course: the goal needs no extra leads, so the growth goal stands.
    assert g["target"] == 5
    assert g["reasoning"][0].startswith("The revenue goal: ₹1 Cr in total from 15 Oct 2026 to 31 Dec 2026.")
    assert "passing ₹1 Cr around 19 Nov 2026" in g["reasoning"][1]


def test_a_revenue_goal_out_of_reach_is_said_in_transactions(db, context):
    from src.services import business_context as bc
    bc.set_revenue_goal(db, 30_000_000, "2026-10-15", "2026-12-31")
    money = gp.goal(db)["revenue"]
    assert not money["on_course"] and money["shortfall_inr"] > 0 and money["extra_txns_a_day"] > 0


def test_the_revenue_goal_is_kept_and_cleared(db):
    from src.services import business_context as bc
    assert bc.revenue_goal(db) is None
    bc.set_revenue_goal(db, 10_000_000, "2026-10-15", "2026-12-31")
    assert bc.revenue_goal(db) == {"inr": 10_000_000, "from": "2026-10-15", "to": "2026-12-31"}
    with pytest.raises(ValueError):
        bc.set_revenue_goal(db, 1, "2026-12-31", "2026-10-15")
    bc.set_revenue_goal(db, None)
    assert bc.revenue_goal(db) is None
