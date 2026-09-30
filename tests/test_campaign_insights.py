"""
Campaign Insights.

The promise is two-sided: find what genuinely worked, and never present noise
as a finding. These build campaigns with a known effect planted in them and
check that it — and only it — is reported, and that tests and unknowns never
become recommendations.
"""
import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.database import Base
from src.models import (  # noqa: F401  (registers the tables on Base)
    Business, CampaignInsight, InsightSnapshot, WhatsAppButtonClick, WhatsAppCampaign,
    WhatsAppCampaignRecipient, WhatsAppLinkClick, WhatsAppTemplate,
)
from src.services import campaign_insights as ci

engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False},
                       poolclass=StaticPool)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base.metadata.create_all(bind=engine)

PA_BODY = "ਸਤਿ ਸ੍ਰੀ ਅਕਾਲ ਜੀ " * 30
HI_BODY = "नमस्कार जी " * 30
TRACKED = [{"type": "URL", "text": "Apply", "url": "https://x/r/{{1}}"}]
# 10:30 IST on a Tuesday.
MORNING = datetime(2026, 9, 29, 5, 0, tzinfo=timezone.utc)


@pytest.fixture
def db(monkeypatch):
    import src.database
    monkeypatch.setattr(src.database, "SessionLocal", TestingSessionLocal)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        for model in (InsightSnapshot, CampaignInsight, WhatsAppLinkClick, WhatsAppButtonClick,
                      WhatsAppCampaignRecipient, WhatsAppCampaign, WhatsAppTemplate, Business):
            session.query(model).delete()
        session.commit()
        session.close()


def template(db, name, body, buttons=TRACKED):
    t = WhatsAppTemplate(template_id=uuid.uuid4().hex, name=name, body=body, status="APPROVED",
                         header_type="IMAGE", buttons=buttons)
    db.add(t)
    db.flush()
    return t


def campaign(db, tmpl, segments, sent_at=MORNING):
    """segments: [(state, category, sent, responded)] — a response is a link visit."""
    total = sum(s[2] for s in segments)
    c = WhatsAppCampaign(campaign_id=uuid.uuid4().hex, name=f"{tmpl.name} run", template_id=tmpl.template_id,
                         data_source_type="scraped", status="COMPLETED", total_contacts=total,
                         successful_count=total)
    db.add(c)
    for state, category, sent, responded in segments:
        for i in range(sent):
            phone = f"+91{uuid.uuid4().int % 10**10:010d}"
            bid = uuid.uuid4().hex[:16]
            db.add(Business(business_id=bid, job_id="J", name="b", phone=phone, category=category,
                            state=state, district=f"{state} district", source_query="q", dedup_key=bid))
            rid = uuid.uuid4().hex
            db.add(WhatsAppCampaignRecipient(recipient_id=rid, campaign_id=c.campaign_id, business_id=bid,
                                             phone=phone, status="SENT", sent_at=sent_at))
            if i < responded:
                db.add(WhatsAppLinkClick(click_id=uuid.uuid4().hex, campaign_id=c.campaign_id,
                                         recipient_id=rid, target_url="https://kiosk.eko.in"))
    db.commit()
    return c


@pytest.fixture
def planted(db):
    """Template A to insurance agents in Punjab responds at 30%; everything else at 2%."""
    a = template(db, "A", PA_BODY)
    b = template(db, "B", HI_BODY)
    ca = campaign(db, a, [("Punjab", "Insurance agent", 100, 30), ("Punjab", "Grocery", 100, 2)])
    cb = campaign(db, b, [("Punjab", "Insurance agent", 100, 2), ("Haryana", "Grocery", 100, 2)])
    return {"a": a, "b": b, "ca": ca, "cb": cb}


def test_wilson_interval():
    lo, hi = ci.wilson(30, 100)
    assert 0.21 < lo < 0.22 and 0.39 < hi < 0.40
    assert ci.wilson(0, 0) == (0.0, 0.0)


def test_the_planted_effect_is_found(db, planted):
    book = ci.playbook(db)
    assert book["by_dimension"]["template"]["best"]["values"]["template"] == "A"
    assert book["by_dimension"]["template"]["best"]["confidence"] == "strong"
    assert book["by_dimension"]["category"]["best"]["values"]["category"] == "Insurance agent"
    top = book["combinations"][0]["values"]
    assert set(top.values()) >= {"A", "Insurance agent"} or set(top.values()) >= {"Insurance agent", "Punjabi"}
    assert book["recipe"]["template"] == {"value": "A", "confidence": "strong",
                                          "response_rate": book["by_dimension"]["template"]["best"]["response_rate"]}


def test_every_combination_can_be_explored(db, planted):
    facts = ci.load_facts(db)
    rows = ci.aggregate(facts, ("template", "state", "category"))
    assert len(rows) == 4
    best = rows[0]
    assert best["values"] == {"template": "A", "state": "Punjab", "category": "Insurance agent"}
    assert best["responded"] == 30 and best["sent"] == 100


def test_a_campaign_report_suggests_what_worked(db, planted):
    report = ci.campaign_report(db, planted["cb"].campaign_id)
    messages = " ".join(s["message"] for s in report["suggestions"])
    assert "“A” has the best response on record" in messages
    # Template B is Hindi, and half its recipients are in Punjab.
    mismatch = next(s for s in report["suggestions"] if "not their state's language" in s["message"])
    assert "100 of 200 recipients" in mismatch["message"] and mismatch["confidence"] == "strong"

    own = ci.campaign_report(db, planted["ca"].campaign_id)
    strengths = [s for s in own["suggestions"] if s["kind"] == "strength"]
    assert any("Insurance agent" in s["message"] for s in strengths)


def test_noise_is_not_reported_as_a_finding(db):
    a = template(db, "A", PA_BODY)
    b = template(db, "B", PA_BODY)
    campaign(db, a, [("Punjab", "Grocery", 300, 1)])
    campaign(db, b, [("Punjab", "Grocery", 300, 0)])
    book = ci.playbook(db)
    assert book["by_dimension"]["template"]["best"] is None
    assert book["by_dimension"]["template"]["leader"]["confidence"] == "too_early"
    assert book["combinations"] == []


def test_test_campaigns_and_unknowns_are_never_recommended(db, planted):
    # The team testing on its own phones: 3 sends, every one "responded".
    t = template(db, "Hello test", PA_BODY)
    campaign(db, t, [("Unknown", "Unknown (uploaded list)", 3, 3)])
    book = ci.playbook(db)
    assert book["test_campaigns_excluded"] == 1
    assert book["by_dimension"]["template"]["best"]["values"]["template"] == "A"
    assert book["by_dimension"]["state"]["leader"]["values"]["state"] != "Unknown"
    assert all("Unknown" not in str(c["values"]) for c in book["combinations"])


def test_an_untracked_link_is_called_out(db):
    t = template(db, "Plain link", HI_BODY + " https://kiosk.eko.in", buttons=[])
    c = campaign(db, t, [("Haryana", "Grocery", 50, 0)])
    report = ci.campaign_report(db, c.campaign_id)
    assert any("link is not tracked" in s["message"] for s in report["suggestions"])


def test_finishing_a_campaign_saves_its_report_and_a_snapshot(db, planted):
    ci.on_campaign_finished(planted["ca"].campaign_id)
    ci.on_campaign_finished(planted["cb"].campaign_id)
    saved = db.query(CampaignInsight).filter(CampaignInsight.campaign_id == planted["ca"].campaign_id).one()
    assert saved.metrics["responded"] == 32 and saved.suggestions
    snaps = db.query(InsightSnapshot).order_by(InsightSnapshot.created_at).all()
    assert len(snaps) == 2
    assert snaps[-1].playbook["best"]["template"] == "A"
    assert snaps[-1].playbook["confident"]["template"] is True


def test_the_api(db, planted):
    from src.routers import insights

    listed = insights.list_campaign_insights(db=db)
    assert {r["name"] for r in listed} == {"A run", "B run"}
    assert all(r["headline"] for r in listed)
    rows = insights.explore(dims="template,category", min_sent=1, db=db)["rows"]
    assert rows[0]["values"] == {"template": "A", "category": "Insurance agent"}
    with pytest.raises(Exception):
        insights.explore(dims="nonsense", min_sent=1, db=db)
