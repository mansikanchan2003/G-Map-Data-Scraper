"""
The business agent: templates written for scraped businesses, learning from
earlier results, held for a reviewer, and filled per business when sent.
"""
import uuid
from datetime import datetime, timezone
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.database import Base
from src.models import Business, Category, Job, Location
from src.models.whatsapp import WhatsAppCampaign, WhatsAppCampaignRecipient, WhatsAppTemplate
from src.services import business_agent as ba
from src.services import template_studio as studio

EXPORT = [
    {"name": "Ankush Battery & Solar", "address": "Main Rd", "phone": "+919876543210", "email": "",
     "website": "", "category": "Battery store", "district": "Kanpur", "state": "Uttar Pradesh", "verified": "TRUE"},
    {"name": "Computer Complex", "address": "Mall Rd", "phone": "+919876543211", "email": "",
     "website": "", "category": "Computer store", "district": "Kanpur", "state": "Uttar Pradesh", "verified": "TRUE"},
    {"name": "Sharma Insurance", "address": "", "phone": "+919876543212", "email": "",
     "website": "", "category": "Insurance agency", "district": "", "state": "Uttar Pradesh", "verified": "TRUE"},
]

def _now():
    return datetime.now(timezone.utc)


GOOD_BODY = ("नमस्ते {{name}} 🙏\n\nक्या आप अपने {{category}} के साथ अतिरिक्त आय चाहते हैं? Eko के साथ SBI Kiosk "
             "(CSP) खोलें और हर महीने ₹15,000 से ₹50,000 तक कमीशन कमाने का अवसर पाएं।\n\n"
             "अभी आवेदन करें 👇\n{{link}}\n\nकॉल या WhatsApp करें: +91 7291988625\n\nधन्यवाद!")


def variant(**over):
    v = {"angle_key": "extra_income", "angle": "Extra income alongside the shop",
         "learned": "Hindi templates with a direct greeting drew the only taps.",
         "body": GOOD_BODY, "footer": "Team Eko", "callback_button": "मुझे कॉल करें"}
    v.update(over)
    return v


class TestAudience:
    def test_summary_offers_only_complete_fields(self):
        s = ba.summarise(EXPORT)
        # district is blank for one business in three, so it is not offered.
        assert s["usable_fields"] == ["name", "category", "state"]
        assert s["main_state"] == "Uttar Pradesh"
        assert s["examples"]["name"] == "Ankush Battery & Solar"
        assert ba.language_for(s) == "hi"

    def test_an_export_without_names_is_refused(self):
        with pytest.raises(ValueError, match="no business name"):
            ba.summarise([{"phone": "1", "message": "hi"}])


class TestValidation:
    allowed = ["name", "category", "state"]

    def test_a_good_variant_passes(self):
        assert ba.validate(variant(), "hi", self.allowed) == []

    @pytest.mark.parametrize("body, problem", [
        (GOOD_BODY.replace("{{name}}", "दोस्त"), "does not greet the business by {{name}}"),
        (GOOD_BODY + " {{district}} में", "cannot be filled: {{district}}"),
        (GOOD_BODY.replace("+91 7291988625", ""), "contact number"),
        (GOOD_BODY + " https://kiosk.eko.in", "web address"),
        (GOOD_BODY.replace("{{link}}", ""), "{{link}} exactly once"),
        (GOOD_BODY + " {{link}} फिर से", "{{link}} exactly once"),
        (GOOD_BODY.split("\n\nकॉल")[0], "ends with a variable"),
        ("{{name}} जी, " + GOOD_BODY, "begins with a variable"),
    ])
    def test_problems_are_named(self, body, problem):
        assert any(problem in e for e in ba.validate(variant(body=body), "hi", self.allowed))

    def test_english_values_in_blanks_are_not_wrong_script(self):
        # {{category}} will be filled with "Battery store"; the template text
        # itself is all Devanagari, which is what is checked.
        assert not any("script" in e or "Devanagari" in e
                       for e in ba.validate(variant(), "hi", self.allowed))


@pytest.fixture
def db(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    monkeypatch.setattr("src.database.SessionLocal", Session)
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://indev.eko.in/autogmap")
    session = Session()
    yield session
    session.close()


class FakeGemini:
    prompts = []

    def __init__(self, *a, **k):
        pass

    def is_configured(self):
        return True

    def text_model(self):
        return "fake-model"

    def generate_json(self, prompt, temperature=1.0):
        FakeGemini.prompts.append(prompt)
        if "checking marketing copy" in prompt:
            return {"unsupported": []}
        return {"variants": [variant(), variant(angle_key="trust_in_sbi", angle="SBI trust")]}


def make_round(db, count=2):
    summary = ba.summarise(EXPORT)
    rows = ba.create_placeholders(db, summary, count, "festive tone", "hi",
                                  "https://kiosk.eko.in/?utm_source=AutoGMap&utm_medium=whatsapp#apply-now",
                                  "businesses_export.xlsx")
    with patch("src.services.business_agent.GeminiClient", FakeGemini):
        ba.run_generation([r.template_id for r in rows])
    db.expire_all()
    return [db.query(WhatsAppTemplate).get(r.template_id) for r in rows]


def test_a_round_writes_drafts_that_wait_for_review(db):
    FakeGemini.prompts = []
    drafts = make_round(db)
    assert [d.status for d in drafts] == [studio.AWAITING_APPROVAL] * 2
    d = drafts[0]
    assert d.origin == "agent" and d.generation["kind"] == "business"
    assert d.meta_template_name is None, "nothing reaches Meta before Approve"
    assert d.generation["variables"] == ["name", "category"]
    assert "{{link}}" in d.body, "the tracked link is in the message itself"
    assert [b["type"] for b in d.buttons] == ["QUICK_REPLY"], "no Apply button"
    assert {x.generation["angle_key"] for x in drafts} == {"extra_income", "community_respect"} \
        or len({x.generation["angle_key"] for x in drafts}) == 2
    assert "festive tone" in FakeGemini.prompts[0]


def test_the_agent_is_shown_how_earlier_templates_did(db):
    old = WhatsAppTemplate(template_id="old1", name="Hindi launch", status="APPROVED", origin="manual",
                           meta_template_name="hindi_launch", language_code="hi",
                           body="नमस्ते {{name}}, SBI Kiosk खोलें। " * 12, buttons=[])
    rejected = WhatsAppTemplate(template_id="rej1", name="Too pushy", status="REJECTED", origin="sheet",
                                meta_template_name="pushy", language_code="hi", body="Buy now",
                                generation={"rejected_reason": "PROMOTIONAL"}, buttons=[])
    db.add_all([old, rejected,
                WhatsAppCampaign(campaign_id="c1", name="launch", data_source_type="scraped", template_id="old1")])
    for i in range(3):
        db.add(WhatsAppCampaignRecipient(recipient_id=f"r{i}", campaign_id="c1", phone=f"+91987654321{i}",
                                         status="READ", sent_at=_now(), delivered_at=_now(), read_at=_now()))
    db.commit()

    FakeGemini.prompts = []
    make_round(db, count=1)
    prompt = FakeGemini.prompts[0]
    assert "Hindi launch" in prompt and "sent 3" in prompt
    assert "PROMOTIONAL" in prompt
    assert "Battery store" in prompt, "the businesses themselves are described"


def test_approving_submits_with_the_businesses_own_examples(db):
    d = make_round(db, count=1)[0]
    captured = {}

    def create(self, name, language, category, components):
        captured.update(name=name, components=components)
        return {"status": "success", "template_status": "PENDING"}

    with patch("src.services.meta_whatsapp_service.MetaWhatsAppService.create_message_template", create):
        result = studio.approve(db, d, "reviewer@eko.co.in", "MARKETING")
    assert result["status"] == "success"
    body = next(c for c in captured["components"] if c["type"] == "BODY")
    assert "{{1}}" in body["text"] and "{{2}}" in body["text"] and "{{3}}" in body["text"]
    assert body["example"] == {"body_text": [["Ankush Battery & Solar", "Battery store",
                                              "https://indev.eko.in/autogmap/r/0123456789abcdef"]]}
    buttons = next(c for c in captured["components"] if c["type"] == "BUTTONS")["buttons"]
    assert [b["type"] for b in buttons] == ["QUICK_REPLY"]


def test_a_scraped_audience_is_filled_from_each_business(db):
    from src.services.whatsapp_service import WhatsAppCampaignService, parameter_value, template_placeholders

    d = make_round(db, count=1)[0]
    d.status = "APPROVED"
    db.add_all([Location(location_id="l1", pincode="208001", latitude=26.4, longitude=80.3),
                Category(category_id="k1", category_name="Battery store"),
                Job(job_id="j1", location_id="l1", category_id="k1", search_query="q")])
    db.add(Business(business_id="b1", job_id="j1", name="Ankush Battery & Solar", phone="+919876543210",
                    category="Battery store", state="Uttar Pradesh", source_query="q", dedup_key="b1"))
    db.add(Business(business_id="b2", job_id="j1", name="No Category Co", phone="+919876543211",
                    category="", state="Uttar Pradesh", source_query="q", dedup_key="b2"))
    db.commit()

    campaign = WhatsAppCampaignService(db).create_campaign_and_recipients(
        name="UP agent", template_id=d.template_id, account_id=None, data_source_type="scraped",
        contacts=[{"phone": "+919876543210", "name": "Ankush Battery & Solar", "business_id": "b1"},
                  {"phone": "+919876543211", "name": "No Category Co", "business_id": "b2"}],
    )
    recs = {r.business_id: r for r in db.query(WhatsAppCampaignRecipient).filter_by(campaign_id=campaign.campaign_id)}
    assert recs["b1"].status == "PENDING"
    token = recs["b1"].tracking_token
    assert [parameter_value(recs["b1"], p, d) for p in template_placeholders(d)] == \
        ["Ankush Battery & Solar", "Battery store", f"https://indev.eko.in/autogmap/r/{token}"]
    assert recs["b2"].status == "SKIPPED" and recs["b2"].reason == "No value for {{category}}"


def test_an_edit_is_checked_without_a_poster(db):
    d = make_round(db, count=1)[0]
    warnings = ba.update(db, d, GOOD_BODY.replace("{{category}}", "{{district}}"), None, None)
    assert any("{{district}}" in w for w in warnings)
    assert d.generation["variables"] == ["name", "district"]


def test_business_drafts_are_kept_out_of_the_poster_list(db):
    from fastapi.testclient import TestClient
    from src.database import get_db
    from src.main import app

    make_round(db, count=1)
    app.dependency_overrides[get_db] = lambda: db
    try:
        client = TestClient(app)
        assert client.get("/api/v1/whatsapp/studio/drafts").json() == []
        assert len(client.get("/api/v1/whatsapp/studio/business-drafts").json()) == 1
    finally:
        app.dependency_overrides.pop(get_db, None)
