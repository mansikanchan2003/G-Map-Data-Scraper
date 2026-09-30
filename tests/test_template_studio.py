"""
The Template Studio agent.

These hold the promises made to the team: every template is in the state's
language and script, claims only the allowed facts, carries a checked photo,
and reaches Meta only after a person approves it.

Gemini and the Chromium renderer are replaced with fakes; the poster renderer
has its own real-browser check at the bottom, skipped when Chromium or the
network is unavailable.
"""
import copy
import json
import uuid

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.database import Base
from src.models import (  # noqa: F401  (registers the tables on Base)
    Business, Job, Location, WhatsAppButtonClick, WhatsAppCampaign,
    WhatsAppCampaignRecipient, WhatsAppLinkClick, WhatsAppTemplate,
)
from src.routers import template_studio as studio_router
from src.routers import whatsapp as wa
from src.services import creative_brief, template_studio

engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base.metadata.create_all(bind=engine)

PA_POSTER = {
    "headline_line1": "ਬੈਂਕਿੰਗ ਸੇਵਾਵਾਂ ਜੋੜੋ,",
    "headline_line2": "ਆਪਣਾ ਕਾਰੋਬਾਰ ਵਧਾਓ",
    "headline_highlight": "ਕਾਰੋਬਾਰ ਵਧਾਓ",
    "subline": "Eko ਨਾਲ ਜੁੜ ਕੇ SBI ਦੇ Kiosk Operator / CSP ਬਣੋ",
    "callout": "ਹਰ ਮਹੀਨੇ ₹15,000 ਤੋਂ ₹50,000 ਤੱਕ ਕਮਿਸ਼ਨ ਕਮਾਉਣ ਦਾ ਮੌਕਾ",
    "callout_highlight": "₹15,000 ਤੋਂ ₹50,000",
    "benefits_title": "ਤੁਹਾਨੂੰ ਮਿਲੇਗਾ",
    "benefits": [
        {"icon": "application", "text": "ਆਸਾਨ ਅਰਜ਼ੀ ਪ੍ਰਕਿਰਿਆ"},
        {"icon": "support", "text": "ਟ੍ਰੇਨਿੰਗ ਅਤੇ ਸਹਾਇਤਾ"},
        {"icon": "banking", "text": "ਬੈਂਕਿੰਗ ਸੇਵਾਵਾਂ"},
        {"icon": "income", "text": "ਵਾਧੂ ਕਮਾਈ"},
        {"icon": "growth", "text": "ਕਾਰੋਬਾਰ ਵਧਾਓ"},
        {"icon": "schemes", "text": "ਸਰਕਾਰੀ ਯੋਜਨਾਵਾਂ"},
    ],
    "cta": "ਅੱਜ ਹੀ ਅਪਲਾਈ ਕਰੋ",
    "opportunity_title": "ਹਰ ਪੇਸ਼ੇਵਰ ਲਈ ਵਧੀਆ ਮੌਕਾ!",
    "opportunity_text": "ਆਪਣੇ ਨੈੱਟਵਰਕ ਨਾਲ ਆਪਣੀ ਨਵੀਂ ਪਛਾਣ ਬਣਾਓ।",
    "sign_title": "ਗਾਹਕ ਸੇਵਾ ਕੇਂਦਰ",
    "bank_name": "ਭਾਰਤੀ ਸਟੇਟ ਬੈਂਕ",
    "phone_label": "ਕਾਲ / ਵਟਸਐਪ ਕਰੋ:",
    "web_label": "ਹੁਣੇ ਅਪਲਾਈ ਕਰੋ:",
}

PA_VARIANT = {
    "angle": "Extra income beside an existing shop",
    "body": "*ਸਤਿ ਸ੍ਰੀ ਅਕਾਲ ਜੀ* 🙏\n\nEko ਨਾਲ ਜੁੜ ਕੇ ਆਪਣੇ ਇਲਾਕੇ ਵਿੱਚ *SBI CSP* ਸ਼ੁਰੂ ਕਰੋ।\n\n"
            "📞 ਕਾਲ / WhatsApp: +91 7291988625\n\n*ਧੰਨਵਾਦ ਜੀ।* 🙏",
    "footer": "ਟੀਮ Eko",
    "apply_button": "ਹੁਣੇ ਅਪਲਾਈ ਕਰੋ",
    "callback_button": "ਮੈਨੂੰ ਕਾਲ ਕਰੋ",
    "poster": PA_POSTER,
    "photo_scene": "A Sikh shopkeeper in his forties serves a farmer at the counter.",
}

PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 64
GOOD_CHECK = {"has_text": False, "photorealistic": True,
              "operator_serving_customer": True, "anatomy_problems": False, "issues": []}


class FakeGemini:
    """Stands in for Gemini; records prompts so tests can read what it was told."""

    prompts: list = []
    variants: list = []
    checks: list = []
    # What the fact check reports, one entry per call; empty means all supported.
    unsupported: list = []

    def __init__(self):
        self.image_calls = 0

    def is_configured(self):
        return True

    def text_model(self):
        return "fake-text"

    def image_model(self):
        return "fake-image"

    def generate_json(self, prompt, temperature=1.0):
        if "checking marketing copy" in prompt:
            return {"unsupported": FakeGemini.unsupported.pop(0) if FakeGemini.unsupported else []}
        FakeGemini.prompts.append(prompt)
        return {"variants": copy.deepcopy(FakeGemini.variants)}

    def generate_image(self, prompt, aspect_ratio="1:1"):
        self.image_calls += 1
        return PNG

    def inspect_image(self, image, mime, question):
        return dict(FakeGemini.checks.pop(0) if FakeGemini.checks else GOOD_CHECK)


class FakeUser:
    email = "reviewer@eko.co.in"


@pytest.fixture
def db(monkeypatch, tmp_path):
    import src.database

    monkeypatch.setattr(src.database, "SessionLocal", TestingSessionLocal)
    monkeypatch.setattr(template_studio, "MEDIA_DIR", str(tmp_path))
    monkeypatch.setattr(template_studio, "GeminiClient", FakeGemini)
    monkeypatch.setattr(template_studio.poster_renderer, "render",
                        lambda poster, lang, photo, mime: b"\xff\xd8JPEG" + lang.encode())
    FakeGemini.prompts, FakeGemini.variants, FakeGemini.checks = [], [copy.deepcopy(PA_VARIANT)], []
    FakeGemini.unsupported = []

    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        for model in (WhatsAppLinkClick, WhatsAppButtonClick, WhatsAppCampaignRecipient,
                      WhatsAppCampaign, WhatsAppTemplate, Business, Job, Location):
            session.query(model).delete()
        session.commit()
        session.close()


def generate(db, state="Punjab", count=1, brief=None):
    rows = template_studio.create_placeholders(db, state, count, brief)
    ids = [r.template_id for r in rows]
    template_studio.run_generation(ids, state, brief)
    db.expire_all()
    return db.query(WhatsAppTemplate).filter(WhatsAppTemplate.template_id.in_(ids)).all()


# --- the brief ---------------------------------------------------------------

def test_every_targeted_state_has_a_language():
    for state in ("Gujarat", "Haryana", "Uttar Pradesh", "Punjab", "Maharashtra", "Rajasthan"):
        assert creative_brief.language_for_state(state), state
    assert creative_brief.language_for_state("Punjab") == "pa"
    assert creative_brief.language_for_state("uttar pradesh") == "hi"
    assert creative_brief.language_for_state("Gujarat") == "gu"
    assert creative_brief.language_for_state("Maharashtra") == "mr"


def test_hindi_heading_on_a_punjabi_poster_is_caught():
    # The mistake already made on a poster that went out.
    problems = creative_brief.script_problems("ਆਪਕੋ आपको मिलेगा", "pa")
    assert any("Devanagari" in p for p in problems)
    assert creative_brief.script_problems("Eko ਨਾਲ SBI CSP", "pa") == []
    assert creative_brief.script_problems("Team Eko", "pa")  # no Gurmukhi at all


# --- copy validation ---------------------------------------------------------

def test_a_good_variant_passes():
    assert template_studio.validate_copy(copy.deepcopy(PA_VARIANT), "pa") == []


@pytest.mark.parametrize("change, expected", [
    ({"body": PA_VARIANT["body"] + "\nhttps://kiosk.eko.in"}, "URL"),
    ({"body": "*ਸਤਿ ਸ੍ਰੀ ਅਕਾਲ ਜੀ*"}, "contact number"),
    ({"body": "नमस्कार +91 7291988625"}, "Devanagari"),
    ({"apply_button": "ਹੁਣੇ ਅਪਲਾਈ ਕਰੋ ਹੁਣੇ ਅਪਲਾਈ ਕਰੋ"}, "apply_button"),
])
def test_bad_variants_are_refused(change, expected):
    variant = {**copy.deepcopy(PA_VARIANT), **change}
    errors = template_studio.validate_copy(variant, "pa")
    assert any(expected in e for e in errors), errors


def test_poster_text_in_the_wrong_script_is_refused():
    variant = copy.deepcopy(PA_VARIANT)
    variant["poster"]["benefits_title"] = "आपको मिलेगा"
    errors = template_studio.validate_copy(variant, "pa")
    assert any("poster.benefits_title" in e and "Devanagari" in e for e in errors)


# --- a generation round ------------------------------------------------------

def test_a_round_produces_drafts_awaiting_approval(db, monkeypatch):
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://indev.eko.in/autogmap")
    [draft] = generate(db)

    assert draft.status == template_studio.AWAITING_APPROVAL
    assert draft.origin == "agent" and draft.target_state == "Punjab"
    assert draft.language_code == "pa"
    assert draft.meta_template_name is None  # never submitted
    assert draft.header_type == "IMAGE"
    assert json.loads(draft.header_content)["source_type"] == "upload"
    assert draft.buttons[0] == {"type": "URL", "text": "ਹੁਣੇ ਅਪਲਾਈ ਕਰੋ",
                                "url": "https://indev.eko.in/autogmap/r/{{1}}"}
    assert draft.buttons[1]["type"] == "QUICK_REPLY"
    assert draft.generation["angle"] == PA_VARIANT["angle"]
    assert draft.generation["photo_check"]["passed"] is True


def test_drafts_stay_out_of_the_templates_list(db):
    [draft] = generate(db)
    listed = {t.template_id for t in wa.list_templates(db=db)}
    assert draft.template_id not in listed


def test_a_photo_with_lettering_is_regenerated(db):
    FakeGemini.checks = [{**GOOD_CHECK, "has_text": True, "issues": ["letters on the wall"]}, GOOD_CHECK]
    [draft] = generate(db)
    assert draft.generation["photo_check"]["attempt"] == 2
    assert draft.generation["photo_check"]["passed"] is True


def test_when_no_photo_passes_the_reviewer_is_told(db):
    bad = {**GOOD_CHECK, "photorealistic": False, "issues": ["looks rendered"]}
    FakeGemini.checks = [bad, bad, bad]
    [draft] = generate(db)
    assert draft.status == template_studio.AWAITING_APPROVAL
    assert draft.generation["photo_check"]["passed"] is False
    assert "looks rendered" in draft.generation["photo_check"]["issues"]


def test_missing_variants_fail_rather_than_hang(db):
    drafts = generate(db, count=2)  # the fake only ever writes one
    statuses = sorted(d.status for d in drafts)
    assert statuses == [template_studio.AWAITING_APPROVAL, template_studio.GENERATION_FAILED]


# --- the reviewer ------------------------------------------------------------

def test_only_approval_submits_to_meta(db, monkeypatch):
    monkeypatch.setenv("MOCK_WHATSAPP_API", "true")
    [draft] = generate(db)

    # The generic submit endpoint refuses an unapproved agent draft.
    with pytest.raises(HTTPException) as exc:
        wa.submit_template(draft.template_id, None, db=db)
    assert exc.value.status_code == 409

    result = studio_router.approve_draft(draft.template_id, None, db=db, user=FakeUser())
    assert result["status"] == "success"
    db.refresh(draft)
    assert draft.meta_template_name and draft.meta_template_name.startswith("punjab_studio_")
    assert draft.status == "PENDING"
    assert draft.reviewed_by == "reviewer@eko.co.in"
    assert draft.template_id in {t.template_id for t in wa.list_templates(db=db)}


def test_a_rejection_reason_reaches_the_next_round(db):
    [draft] = generate(db)
    studio_router.reject_draft(
        draft.template_id, studio_router.RejectRequest(reason="Headline sounds too salesy"),
        db=db, user=FakeUser(),
    )
    db.refresh(draft)
    assert draft.status == template_studio.REJECTED

    generate(db)
    prompt = FakeGemini.prompts[-1]
    assert "Headline sounds too salesy" in prompt
    assert PA_VARIANT["angle"] in prompt  # tried angles are not repeated


def test_editing_poster_text_rerenders(db):
    [draft] = generate(db)
    before = draft.header_content
    warnings = template_studio.update_draft(
        db, draft, None, None, None, {"cta": "ਅੱਜ ਹੀ ਜੁੜੋ"})
    assert warnings == []
    assert draft.header_content != before
    assert draft.generation["poster"]["cta"] == "ਅੱਜ ਹੀ ਜੁੜੋ"


# --- what the agent learns from ----------------------------------------------

def test_performance_is_split_by_recipient_state(db):
    t = WhatsAppTemplate(template_id=uuid.uuid4().hex, name="Punjab Campaign",
                         body="ਸਤਿ ਸ੍ਰੀ ਅਕਾਲ", status="APPROVED")
    c = WhatsAppCampaign(campaign_id=uuid.uuid4().hex, name="c", template_id=t.template_id,
                         data_source_type="scraped", status="COMPLETED")
    db.add_all([t, c])
    db.flush()
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    for i, (state, delivered) in enumerate([("Punjab", True), ("Punjab", False), ("Haryana", True)]):
        phone = f"+91900000000{i}"
        db.add(Business(business_id=f"B{i}", job_id="J1", name="x", phone=phone, category="c",
                        state=state, source_query="q", dedup_key=f"k{i}"))
        r = WhatsAppCampaignRecipient(recipient_id=f"R{i}", campaign_id=c.campaign_id, phone=phone,
                                      status="SENT", sent_at=now,
                                      delivered_at=now if delivered else None)
        db.add(r)
    db.add(WhatsAppLinkClick(click_id="K1", campaign_id=c.campaign_id, recipient_id="R0",
                             target_url="https://kiosk.eko.in"))
    db.commit()

    [perf] = template_studio.template_performance(db)
    assert perf["sent"] == 3 and perf["delivered"] == 2 and perf["visitors"] == 1
    states = {s["state"]: s for s in perf["by_state"]}
    assert states["Punjab"]["sent"] == 2 and states["Punjab"]["visitors"] == 1
    assert states["Haryana"]["sent"] == 1
    assert perf["language"] == "pa"


# --- the real renderer -------------------------------------------------------

def test_poster_html_carries_every_rule():
    html = template_studio.poster_renderer.build_html(PA_POSTER, "pa", PNG, "image/png")
    assert "Noto Sans Gurmukhi" in html
    assert creative_brief.PHONE in html and creative_brief.SIGNUP_URL in html
    assert "ਗਾਹਕ ਸੇਵਾ ਕੇਂਦਰ" in html and "Customer Service Point" in html
    assert "#fbb11b" in html  # the Eko logo
    assert '<span class="hl">ਕਾਰੋਬਾਰ ਵਧਾਓ</span>' in html


# --- models the key cannot use -----------------------------------------------

def test_unusable_models_fall_back_and_photo_failure_keeps_the_copy(db, monkeypatch):
    """A free-tier key: Pro has no quota and no image model works at all."""
    from src.services import gemini_client as gc

    monkeypatch.setenv("GEMINI_API_KEY", "k")
    monkeypatch.setattr(gc, "_dead_models", set())
    monkeypatch.setattr(gc.GeminiClient, "available_models",
                        lambda self: ["gemini-3.1-pro-preview", "gemini-3.8-flash", "gemini-3-pro-image"])
    calls = []

    def fake_post(self, model, payload, timeout):
        calls.append(model)
        if model in ("gemini-3.1-pro-preview", "gemini-3-pro-image"):
            raise gc.GeminiError(f"Gemini ({model}) refused the request: Quota exceeded ... limit: 0, model: x")
        return {"candidates": [{"content": {"parts": [{"text": json.dumps({"variants": [PA_VARIANT]})}]}}]}

    monkeypatch.setattr(gc.GeminiClient, "_post", fake_post)
    monkeypatch.setattr(template_studio, "GeminiClient", gc.GeminiClient)

    [draft] = generate(db)
    assert calls[:2] == ["gemini-3.1-pro-preview", "gemini-3.8-flash"]
    assert draft.status == template_studio.GENERATION_FAILED
    assert "billing" in draft.generation["error"]
    # The writing survived, so the draft can be finished once photos work.
    assert draft.body == PA_VARIANT["body"]
    assert draft.generation["poster"]["cta"] == PA_POSTER["cta"]
    assert draft.generation["models"]["text"] == "gemini-3.8-flash"


def test_an_unsupported_claim_is_sent_back_for_repair(db):
    # The first real round offered "cash deposit", which is not a listed service.
    FakeGemini.unsupported = [["ਜਮ੍ਹਾਂ — cash deposit is not a listed service"], []]
    [draft] = generate(db)
    assert len(FakeGemini.prompts) == 2  # the round, then one repair
    assert "cash deposit is not a listed service" in FakeGemini.prompts[1]
    assert draft.generation["copy_warnings"] == []


def test_a_claim_still_unsupported_after_repair_is_shown_to_the_reviewer(db):
    FakeGemini.unsupported = [["guaranteed ₹50,000"], ["guaranteed ₹50,000"]]
    [draft] = generate(db)
    assert draft.status == template_studio.AWAITING_APPROVAL
    assert draft.generation["copy_warnings"] == ["unsupported claim: guaranteed ₹50,000"]


# --- angles ------------------------------------------------------------------

def test_a_round_gets_distinct_angles_least_tried_first():
    angles = template_studio.assign_angles(3, {"extra_income": 2, "community_respect": 1})
    assert len(set(angles)) == 3
    assert "extra_income" not in angles and "community_respect" not in angles
    assert angles[0] == "trust_in_sbi"  # untried, first on the menu


def test_angles_rotate_across_rounds_for_a_state(db):
    [first] = generate(db)
    [second] = generate(db)
    assert first.generation["angle_key"] == "extra_income"
    assert second.generation["angle_key"] == "community_respect"
    # The assignment is in the prompt, spelled out.
    assert "community_respect:" in FakeGemini.prompts[-1]


def test_escaped_newlines_from_the_model_are_cleaned(db):
    variant = copy.deepcopy(PA_VARIANT)
    # A backslash followed by n, as the model wrote it — not a line break.
    variant["body"] = variant["body"].replace("\n\n", "\\n", 1)
    assert "\\n" in variant["body"]
    FakeGemini.variants = [variant]
    [draft] = generate(db)
    assert "\\n" not in draft.body
    assert draft.body.startswith("*ਸਤਿ ਸ੍ਰੀ ਅਕਾਲ ਜੀ* 🙏\n")


def test_a_busy_model_is_set_aside_for_later_calls(monkeypatch):
    from src.services import gemini_client as gc

    monkeypatch.setenv("GEMINI_API_KEY", "k")
    monkeypatch.setattr(gc, "_dead_models", set())
    monkeypatch.setattr(gc, "_busy_until", {})
    monkeypatch.setattr(gc.GeminiClient, "available_models",
                        lambda self: ["gemini-3.8-flash", "gemini-3.5-flash"])
    calls = []

    def fake_post(self, model, payload, timeout):
        calls.append(model)
        if model == "gemini-3.8-flash":
            raise gc.GeminiError("Gemini (gemini-3.8-flash) refused the request: This model is currently experiencing high demand.")
        return {"candidates": [{"content": {"parts": [{"text": "{}"}]}}]}

    monkeypatch.setattr(gc.GeminiClient, "_post", fake_post)
    client = gc.GeminiClient()
    client.generate_json("a")
    client.generate_json("b")
    assert calls == ["gemini-3.8-flash", "gemini-3.5-flash", "gemini-3.5-flash"]
