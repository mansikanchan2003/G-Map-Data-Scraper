"""
The business agent: templates written for scraped businesses, learning from
earlier results, held for a reviewer, and filled per business when sent.
"""
import copy
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


HI_POSTER = {
    "headline_line1": "अपनी दुकान के साथ",
    "headline_line2": "बढ़ाएँ अपनी आय",
    "headline_highlight": "अपनी आय",
    "subline": "Eko के साथ SBI Kiosk Operator / CSP बनें",
    "callout": "हर महीने ₹15,000 से ₹50,000 तक कमीशन कमाने का अवसर",
    "callout_highlight": "कमाने का अवसर",
    "benefits_title": "आपको मिलेगा",
    "benefits": [{"icon": icon, "text": text} for icon, text in [
        ("account", "नया SBI खाता"), ("withdrawal", "नकद निकासी"), ("transfer", "मनी ट्रांसफर"),
        ("banking", "बैलेंस जाँच"), ("support", "प्रशिक्षण और सहायता"), ("income", "अतिरिक्त कमाई")]],
    "cta": "आज ही आवेदन करें",
    "opportunity_title": "दुकान के साथ अतिरिक्त आय",
    "opportunity_text": "आपके मौजूदा ग्राहक ही आपके पहले Kiosk ग्राहक बनेंगे।",
    "sign_title": "ग्राहक सेवा केंद्र",
    "bank_name": "भारतीय स्टेट बैंक",
    "phone_label": "कॉल / WhatsApp:",
    "web_label": "अभी आवेदन करें:",
}


def variant(**over):
    v = {"angle_key": "extra_income", "angle": "Extra income alongside the shop",
         "learned": "Hindi templates with a direct greeting drew the only taps.",
         "body": GOOD_BODY, "footer": "Team Eko", "callback_button": "मुझे कॉल करें",
         "poster": copy.deepcopy(HI_POSTER)}
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


# --- the image, made from the finished text -----------------------------------

PHRASE = "अतिरिक्त आय चाहते हैं"  # copied from GOOD_BODY
SCENE = "A shopkeeper in his forties serves a farmer at the counter of his battery store."


class ImageGemini(FakeGemini):
    """FakeGemini that also makes photos and reads their signs."""

    reads: list = []          # what each sign photo is read as, in turn
    images = 0
    allowance = None          # images left before the "free allowance" runs out
    image_failure = None      # an error every image request raises
    last_used_image_model = "fake-flux"

    def generate_json(self, prompt, temperature=1.0):
        FakeGemini.prompts.append(prompt)
        if "checking marketing copy" in prompt:
            return {"unsupported": []}
        return {"variants": [variant(image_phrase=PHRASE, photo_scene=SCENE)]}

    def generate_image(self, prompt, seed=None):
        from src.services.gemini_client import ImageUnavailable
        if ImageGemini.image_failure:
            raise ImageGemini.image_failure
        if ImageGemini.allowance is not None:
            if ImageGemini.allowance <= 0:
                raise ImageUnavailable("You have exceeded your free ZeroGPU quota.")
            ImageGemini.allowance -= 1
        ImageGemini.images += 1
        return b"\xff\xd8photo"

    def inspect_image(self, image, mime, question):
        if "sign_text" in question:
            read = ImageGemini.reads.pop(0) if ImageGemini.reads else ""
            return {"sign_text": read, "other_text": "", "photorealistic": True,
                    "operator_serving_customer": True, "anatomy_problems": False, "issues": []}
        return {"has_text": False, "photorealistic": True, "operator_serving_customer": True,
                "anatomy_problems": False, "issues": []}


@pytest.fixture
def images(monkeypatch, tmp_path):
    monkeypatch.setattr(studio, "MEDIA_DIR", str(tmp_path))
    posters = []
    monkeypatch.setattr(studio.poster_renderer, "render",
                        lambda poster, lang, photo, mime: posters.append((poster["headline_line2"], lang)) or b"\xff\xd8POSTER")
    monkeypatch.setattr(studio.poster_renderer, "render_photo_with_logo", lambda photo, mime: b"\xff\xd8LOGO")
    ImageGemini.reads, ImageGemini.images = [], 0
    ImageGemini.allowance = ImageGemini.image_failure = None
    return posters


def image_round(db):
    summary = ba.summarise(EXPORT)
    rows = ba.create_placeholders(db, summary, 1, None, "hi", "https://kiosk.eko.in/", None)
    with patch("src.services.business_agent.GeminiClient", ImageGemini):
        ba.run_generation([r.template_id for r in rows])
    db.expire_all()
    return db.query(WhatsAppTemplate).get(rows[0].template_id)


def test_the_prompt_asks_for_a_phrase_from_the_body_and_a_scene_without_text(db, images):
    FakeGemini.prompts = []
    image_round(db)
    prompt = FakeGemini.prompts[0]
    assert '"image_phrase": "2 to 5 words copied exactly from your headline or body' in prompt
    assert "No text, signs or logos" in prompt
    # The 9 October instructions asked the image model for Indic text and logos.
    assert "MUST instruct the model to write" not in prompt


def test_a_correct_sign_makes_the_photo_the_header(db, images):
    ImageGemini.reads = [PHRASE]
    d = image_round(db)
    assert d.status == studio.AWAITING_APPROVAL
    assert d.header_type == "IMAGE" and d.header_content
    assert d.generation["image_mode"] == "photo_text"
    assert ImageGemini.images == 1 and images == []


def test_a_misspelt_sign_gets_the_full_poster(db, images):
    ImageGemini.reads = ["अतिरिक्त आय चाहत"]
    d = image_round(db)
    assert d.generation["image_mode"] == "typeset"
    assert images == [(HI_POSTER["headline_line2"], "hi")], "the poster agent's full poster, not a thin banner"
    assert d.generation["poster"]["callout"] == HI_POSTER["callout"]
    assert ImageGemini.images == 2  # one sign photo, one plain photo
    assert d.status == studio.AWAITING_APPROVAL and d.header_content


def test_a_spent_allowance_waits_and_the_queue_finishes_it(db, images):
    from datetime import timedelta
    from src.services import photo_queue

    ImageGemini.allowance = 0
    d = image_round(db)
    assert d.status == studio.PHOTO_PENDING
    assert d.body == GOOD_BODY, "the text is kept while the photo waits"

    ImageGemini.allowance, ImageGemini.reads = 5, [PHRASE]
    with patch("src.services.template_studio.GeminiClient", ImageGemini):
        assert photo_queue.tick(db, now=_now() + timedelta(hours=3)) == 1
    db.expire_all()
    d = db.query(WhatsAppTemplate).get(d.template_id)
    assert d.status == studio.AWAITING_APPROVAL and d.generation["image_mode"] == "photo_text"


def test_another_photo_failure_leaves_a_sendable_draft(db, images):
    from src.services.gemini_client import GeminiError

    ImageGemini.image_failure = GeminiError("the Space returned an error")
    d = image_round(db)
    assert d.status == studio.AWAITING_APPROVAL
    assert not d.header_content
    assert "photo" in d.generation["photo_error"].lower()


def test_an_edit_that_drops_the_phrase_is_flagged(db, images):
    ImageGemini.reads = [PHRASE]
    d = image_round(db)
    problems = ba.update(db, d, GOOD_BODY.replace("अतिरिक्त आय चाहते हैं", "और कमाई चाहते हैं"), None, None)
    assert any("no longer in the message" in p for p in problems)


@pytest.mark.parametrize("phrase, problem", [
    ("{{name}} आय चाहते", "has a blank in it"),
    ("यह कहीं नहीं लिखा", "not copied exactly from the headline or body"),
    ("आय", "needs 2 to 5"),
])
def test_image_phrase_rules(phrase, problem):
    errors = ba.validate(variant(image_phrase=phrase), "hi", ["name", "category", "state"])
    assert any(problem in e for e in errors)


def test_a_good_image_phrase_passes():
    assert ba.validate(variant(image_phrase=PHRASE), "hi", ["name", "category", "state"]) == []


def test_the_prompt_asks_for_the_full_poster(db, images):
    FakeGemini.prompts = []
    image_round(db)
    prompt = FakeGemini.prompts[0]
    for field in ("headline_line1", "callout", "benefits", "opportunity_text", "sign_title", "web_label"):
        assert f'"{field}"' in prompt, field


def test_poster_problems_are_named():
    bad = copy.deepcopy(HI_POSTER)
    bad["benefits"] = bad["benefits"][:4]
    bad["cta"] = "Apply today"
    bad["callout"] = "{{name}} के लिए अवसर"
    errors = ba.validate(variant(poster=bad), "hi", ["name", "category", "state"])
    assert any("exactly 6 are needed" in e for e in errors)
    assert any(e.startswith("poster.cta") and "Devanagari" in e for e in errors)
    assert any("the poster has a blank in it" in e for e in errors)


def test_a_phrase_from_the_poster_headline_is_allowed():
    v = variant(image_phrase=HI_POSTER["headline_line2"])
    assert ba.validate(v, "hi", ["name", "category", "state"]) == []
