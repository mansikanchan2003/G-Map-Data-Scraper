"""
Automated hits on a tracking link are recorded, but never counted as clicks.

Six of the first seven recorded "clicks" in production were curl, Python's
urllib and headless Chrome. The other side matters as much: a real phone
must never be thrown away, so the phones here include one whose brand name
ends in "bot".
"""
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.database import Base, get_db
from src.models import WhatsAppCampaign, WhatsAppCampaignRecipient, WhatsAppLinkClick
from src.services.click_filter import automated_reason

PEOPLE = [
    # The one real click recorded in production so far.
    "Mozilla/5.0 (Linux; Android 16; motorola edge 70 fusion Build/W2WE36.56-62-27; ) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/140.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 18_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) "
    "Version/18.5 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (Linux; Android 13; CUBOT X30) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/139.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (Linux; Android 14; SM-A155F Build/UP1A.231005.007; wv) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Version/4.0 Chrome/140.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36",
]

MACHINES = [
    ("curl/8.7.1", "script or HTTP tool"),
    ("Python-urllib/3.12", "script or HTTP tool"),
    ("python-requests/2.32.3", "script or HTTP tool"),
    ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
     "HeadlessChrome/151.0.7922.34 Safari/537.36", "headless browser"),
    ("WhatsApp/2.24.21.80 A", "WhatsApp link preview"),
    ("facebookexternalhit/1.1 (+http://www.facebook.com/externalhit_uatext.php)", "Meta link preview"),
    ("Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)", "bot or crawler"),
    ("Mozilla/5.0 (compatible; SomeNewCrawlerBot/1.0)", "bot or crawler"),
    ("", "no user agent"),
    (None, "no user agent"),
]


@pytest.mark.parametrize("ua", PEOPLE)
def test_real_phones_and_browsers_count(ua):
    assert automated_reason(ua) is None


@pytest.mark.parametrize("ua, reason", MACHINES)
def test_tools_bots_and_previews_do_not(ua, reason):
    assert automated_reason(ua) == reason


def test_a_head_request_is_a_link_checker_whatever_it_claims():
    assert automated_reason(PEOPLE[0], "HEAD") == "HEAD request (link checker)"


# --- end to end, through the real redirect and the real counts ---------------

engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False},
                       poolclass=StaticPool)
Session = sessionmaker(bind=engine)
Base.metadata.create_all(bind=engine)


@pytest.fixture
def setup():
    from src.main import app

    db = Session()
    campaign = WhatsAppCampaign(campaign_id=uuid.uuid4().hex, name="Punjab", data_source_type="scraped",
                                status="COMPLETED", total_contacts=1, successful_count=1)
    recipient = WhatsAppCampaignRecipient(recipient_id=uuid.uuid4().hex, campaign_id=campaign.campaign_id,
                                          phone="+919000000001", status="SENT", tracking_token=uuid.uuid4().hex)
    db.add_all([campaign, recipient])
    db.commit()

    def override():
        s = Session()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db] = override
    try:
        yield TestClient(app), db, campaign, recipient
    finally:
        app.dependency_overrides.pop(get_db, None)
        for model in (WhatsAppLinkClick, WhatsAppCampaignRecipient, WhatsAppCampaign):
            db.query(model).delete()
        db.commit()
        db.close()


def test_a_preview_fetch_then_a_real_tap_counts_once(setup):
    from src.routers.whatsapp import _visit_counts

    client, db, campaign, recipient = setup
    url = f"/r/{recipient.tracking_token}"

    # WhatsApp fetches the link to build a preview; a scanner checks it; then
    # the recipient taps it.
    for ua in ("WhatsApp/2.24.21.80 A", "curl/8.7.1", PEOPLE[0]):
        r = client.get(url, headers={"user-agent": ua}, follow_redirects=False)
        # Everyone is still sent on: a misjudged person must never be stranded.
        assert r.status_code == 302
        assert r.headers["location"].startswith("https://kiosk.eko.in/signup?utm_source=AutoGMap")
    # The route answers GET only, so a link checker's HEAD is refused before
    # anything is recorded.
    assert client.head(url, headers={"user-agent": PEOPLE[1]}).status_code == 405

    hits = db.query(WhatsAppLinkClick).order_by(WhatsAppLinkClick.clicked_at).all()
    assert len(hits) == 3, "every hit is kept, so the judgement can be checked"
    assert sorted(h.automated_reason or "person" for h in hits) == sorted([
        "WhatsApp link preview", "script or HTTP tool", "person"])

    counts = _visit_counts(db, [campaign.campaign_id])[campaign.campaign_id]
    assert counts == {"unique": 1, "repeated": 0, "total": 1, "automated": 2}


def test_insights_count_only_the_person(setup):
    from src.services import campaign_insights as ci

    client, db, campaign, recipient = setup
    from datetime import datetime, timezone
    recipient.sent_at = datetime.now(timezone.utc)
    db.commit()
    client.get(f"/r/{recipient.tracking_token}", headers={"user-agent": "curl/8.7.1"}, follow_redirects=False)
    facts = ci.load_facts(db, [campaign.campaign_id])
    assert facts[0]["visited"] == 0 and facts[0]["responded"] == 0

    client.get(f"/r/{recipient.tracking_token}", headers={"user-agent": PEOPLE[0]}, follow_redirects=False)
    facts = ci.load_facts(db, [campaign.campaign_id])
    assert facts[0]["visited"] == 1
