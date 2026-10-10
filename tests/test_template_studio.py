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
    fact_prompts: list = []

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
            FakeGemini.fact_prompts.append(prompt)
            return {"unsupported": FakeGemini.unsupported.pop(0) if FakeGemini.unsupported else []}
        FakeGemini.prompts.append(prompt)
        return {"variants": copy.deepcopy(FakeGemini.variants)}

    def inspect_image(self, image, mime, question):
        check = FakeGemini.checks.pop(0) if FakeGemini.checks else GOOD_CHECK
        if isinstance(check, Exception):
            raise check
        return dict(check)

    last_used_image_model = "fake-image"
    # Images made, and how many more before the "allowance" runs out (None: no limit).
    images = 0
    allowance = None

    def generate_image(self, prompt, seed=None):
        from src.services.gemini_client import ImageUnavailable
        if FakeGemini.allowance is not None:
            if FakeGemini.allowance <= 0:
                raise ImageUnavailable("You have exceeded your free ZeroGPU quota. Try again in 1:00:00.",
                                       retry_after=3600)
            FakeGemini.allowance -= 1
        FakeGemini.images += 1
        return PNG


class FakeUser:
    email = "reviewer@eko.co.in"


@pytest.fixture
def db(monkeypatch, tmp_path):
    import src.database

    monkeypatch.setattr(src.database, "SessionLocal", TestingSessionLocal)
    monkeypatch.setattr(template_studio, "MEDIA_DIR", str(tmp_path))
    monkeypatch.setattr(template_studio, "GeminiClient", FakeGemini)
    monkeypatch.setattr(template_studio.poster_renderer, "render",
                        lambda poster, lang, photo, mime, layout="classic": b"\xff\xd8JPEG" + lang.encode())
    FakeGemini.prompts, FakeGemini.variants, FakeGemini.checks = [], [copy.deepcopy(PA_VARIANT)], []
    FakeGemini.unsupported, FakeGemini.fact_prompts = [], []
    FakeGemini.images, FakeGemini.allowance = 0, None

    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        from src.models import AppSetting
        from src.models.studio import StudioImagePrompt
        for model in (AppSetting, StudioImagePrompt, WhatsAppLinkClick, WhatsAppButtonClick, WhatsAppCampaignRecipient,
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


def test_a_photo_with_lettering_is_kept_for_the_reviewer_not_regenerated(db):
    # The free allowance is a few images a day, so a flawed photo is shown
    # with its problems and "New photo" asks for another.
    FakeGemini.checks = [{**GOOD_CHECK, "has_text": True, "issues": ["letters on the wall"]}, GOOD_CHECK]
    [draft] = generate(db)
    assert FakeGemini.images == 1
    assert draft.status == template_studio.AWAITING_APPROVAL
    assert draft.generation["photo_check"]["passed"] is False
    assert "letters on the wall" in draft.generation["photo_check"]["issues"]


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

class FakeG4F:
    """Stands in for g4f: answers per model name, recording the order tried."""

    def __init__(self, answers):
        self.answers, self.calls = answers, []
        self.chat = self
        self.completions = self

    def create(self, model, messages, **kwargs):
        self.calls.append(model)
        answer = self.answers.get(model)
        if isinstance(answer, Exception) or answer is None:
            raise answer or RuntimeError("no reply received (gate rejection)")
        msg = type("M", (), {"content": answer})()
        return type("R", (), {"choices": [type("C", (), {"message": msg})()]})()


def test_text_models_fall_back_and_photo_failure_keeps_the_copy(db, monkeypatch):
    """A model that does not answer is skipped; a photo failure keeps the copy."""
    from src.services import gemini_client as gc

    fake = FakeG4F({"llama-3.3-70b": "Here it is:\n```json\n" + json.dumps({"variants": [PA_VARIANT]}) + "\n```"})
    monkeypatch.setattr(gc, "G4FClient", lambda: fake)
    monkeypatch.setattr(template_studio, "GeminiClient", gc.GeminiClient)

    def no_photo(self, prompt, seed=None):
        raise gc.GeminiError("No free image model answered (tried: FLUX.1-dev, FLUX.1-schnell).")

    monkeypatch.setattr(gc.GeminiClient, "generate_image", no_photo)

    [draft] = generate(db)
    assert fake.calls[:2] == ["gemini-2.0-flash", "llama-3.3-70b"]
    assert draft.status == template_studio.GENERATION_FAILED
    assert "FLUX" in draft.generation["error"]
    # The writing survived, so the draft can be finished once photos work.
    assert draft.body == PA_VARIANT["body"]
    assert draft.generation["poster"]["cta"] == PA_POSTER["cta"]
    assert draft.generation["models"]["text"] == "llama-3.3-70b (via g4f)"


def test_no_made_up_draft_when_every_model_fails(monkeypatch):
    from src.services import gemini_client as gc

    monkeypatch.setattr(gc, "G4FClient", lambda: FakeG4F({}))
    with pytest.raises(gc.GeminiError, match="No free text model answered"):
        gc.GeminiClient().generate_json("write")


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


def test_grammar_examples_are_approved_templates_in_the_same_language(monkeypatch):
    hindi = "*सादर नमस्कार* 🙏\n\n🏦 *Eko लेकर आया है आपके लिए SBI से जुड़कर अपना Kiosk Business शुरू करने का अवसर!* " * 2
    approved = [
        {"name": "hindi_campaign", "language": "en_US", "category": "MARKETING", "body": hindi},
        # The same campaign resubmitted under another name: shown once.
        {"name": "hindi_campaign_v2", "language": "hi", "category": "MARKETING", "body": hindi + " धन्यवाद।"},
        {"name": "punjabi_campaign", "language": "pa", "category": "MARKETING",
         "body": "*ਸਤਿਕਾਰ ਸਹਿਤ ਨਮਸਕਾਰ ਜੀ* 🙏 ਤੁਸੀਂ ਆਪਣੇ ਇਲਾਕੇ ਵਿੱਚ SBI CSP ਖੋਲ੍ਹ ਸਕਦੇ ਹੋ ਅਤੇ ਲੋਕਾਂ ਨੂੰ ਬੈਂਕਿੰਗ ਸੇਵਾਵਾਂ ਦੇ ਸਕਦੇ ਹੋ।" * 2},
        {"name": "hinglish", "language": "hi", "category": "MARKETING",
         "body": "Namaste {{1}} ji! Aapke paas total {{2}} accounts hain jisme average balance Rs {{3}} hai. " * 2},
        {"name": "testing", "language": "en", "category": "MARKETING", "body": "Hello {{1}}, this is a test run."},
    ]
    monkeypatch.setattr(template_studio, "_approved_from_meta", lambda: approved)

    assert template_studio.approved_examples(None, "hi") == [hindi + " धन्यवाद।"]
    assert len(template_studio.approved_examples(None, "pa")) == 1
    # Marathi shares the script but not the grammar, so Hindi is not offered.
    assert template_studio.approved_examples(None, "mr") == []
    assert template_studio.approved_examples(None, "gu") == []


def test_grammar_examples_reach_the_prompt(db):
    generate(db)
    assert "HOW EKO WRITES Punjabi" in FakeGemini.prompts[0]


# --- the photo carries the phrase, or the poster is typeset -------------------

PHRASE = "ਆਪਣਾ ਕਾਰੋਬਾਰ ਵਧਾਓ"  # headline_line2


def with_phrase(monkeypatch, reads):
    """A variant with an image phrase, and a checker that reads `reads` in turn."""
    FakeGemini.variants = [{**copy.deepcopy(PA_VARIANT), "image_phrase": PHRASE}]
    FakeGemini.checks = [{**GOOD_CHECK, "sign_text": r, "other_text": ""} for r in reads]
    monkeypatch.setattr(template_studio.poster_renderer, "render_photo_with_logo",
                        lambda photo, mime: b"\xff\xd8LOGO")


def test_a_photo_whose_sign_reads_the_phrase_is_used_as_it_is(db, monkeypatch):
    with_phrase(monkeypatch, [PHRASE])
    [draft] = generate(db)
    gen = draft.generation
    assert draft.status == template_studio.AWAITING_APPROVAL
    assert gen["image_mode"] == "photo_text"
    assert gen["text_photo_attempts"][0]["passed"] is True
    assert f'reads exactly: "{PHRASE}"' in gen["text_photo_prompt"]


def test_a_misspelt_sign_falls_back_to_the_typeset_poster(db, monkeypatch):
    # One vowel sign wrong is a misspelling, and is not accepted.
    with_phrase(monkeypatch, ["ਆਪਣਾ ਕਾਰੋਬਾਰ ਵਧਾ"])
    [draft] = generate(db)
    gen = draft.generation
    assert gen["image_mode"] == "typeset"
    assert [a["passed"] for a in gen["text_photo_attempts"]] == [False]
    assert gen["text_photo_attempts"][0]["read"] == "ਆਪਣਾ ਕਾਰੋਬਾਰ ਵਧਾ"
    assert draft.header_content  # the typeset poster
    # One try at the sign, one plain photo: a draft costs at most two images.
    assert FakeGemini.images == 2


def test_an_image_phrase_must_come_from_the_copy(db):
    variant = {**copy.deepcopy(PA_VARIANT), "image_phrase": "ਕੁਝ ਹੋਰ ਸ਼ਬਦ"}
    assert "image_phrase is not copied exactly from the headline or body" in template_studio.validate_copy(variant, "pa")


# --- learning from its own mistakes ------------------------------------------

def test_a_reviewer_correction_reaches_the_next_round(db):
    [draft] = generate(db)
    corrected = draft.body.replace("ਸ਼ੁਰੂ ਕਰੋ।", "ਖੋਲ੍ਹੋ।")
    template_studio.update_draft(db, draft, corrected, None, None, None)
    generate(db)
    prompt = FakeGemini.prompts[-1]
    assert "MISTAKES IN YOUR EARLIER DRAFTS" in prompt
    assert "a reviewer corrected it to" in prompt and "ਖੋਲ੍ਹੋ।" in prompt


def test_problems_found_in_a_first_attempt_reach_the_next_round(db):
    bad = copy.deepcopy(PA_VARIANT)
    bad["body"] = bad["body"].replace("*SBI CSP*", "**SBI CSP**")
    FakeGemini.variants = [bad]
    generate(db)
    FakeGemini.variants = [copy.deepcopy(PA_VARIANT)]
    generate(db)
    assert "double asterisks" in FakeGemini.prompts[-1].split("MISTAKES IN YOUR EARLIER DRAFTS")[1]


# --- waiting for the free image allowance -------------------------------------

from datetime import datetime as _dt, timedelta as _td, timezone as _tz  # noqa: E402
from src.services import photo_queue  # noqa: E402


def test_a_spent_allowance_parks_the_draft_with_its_copy(db):
    FakeGemini.allowance = 0
    [draft] = generate(db)
    gen = draft.generation
    assert draft.status == template_studio.PHOTO_PENDING
    assert draft.body == PA_VARIANT["body"] and gen["poster"]["cta"] == PA_POSTER["cta"]
    # Hugging Face said an hour; the retry is set just past it.
    retry_at = _dt.fromisoformat(gen["photo_retry_at"])
    assert _td(minutes=60) < retry_at - _dt.now(_tz.utc) < _td(minutes=63)
    # Still a draft: kept out of the Templates list and the campaign picker.
    assert template_studio.PHOTO_PENDING in template_studio.DRAFT_STATUSES


def test_the_queue_finishes_a_waiting_draft_once_the_allowance_returns(db):
    FakeGemini.allowance = 0
    [draft] = generate(db)
    assert photo_queue.tick(db) == 0  # not due yet

    FakeGemini.allowance = 5
    later = _dt.now(_tz.utc) + _td(hours=2)
    assert photo_queue.tick(db, now=later) == 1
    db.expire_all()
    draft = db.get(WhatsAppTemplate, draft.template_id)
    assert draft.status == template_studio.AWAITING_APPROVAL
    assert draft.header_content
    assert "photo_retry_at" not in draft.generation and "error" not in draft.generation


def test_a_sign_photo_already_tried_is_not_made_again_after_the_wait(db, monkeypatch):
    with_phrase(monkeypatch, ["ਗਲਤ"])
    FakeGemini.allowance = 1  # enough for the sign photo, not the plain one
    [draft] = generate(db)
    assert draft.status == template_studio.PHOTO_PENDING
    assert len(draft.generation["text_photo_attempts"]) == 1

    FakeGemini.allowance, FakeGemini.images = 5, 0
    photo_queue.tick(db, now=_dt.now(_tz.utc) + _td(hours=2))
    db.expire_all()
    draft = db.get(WhatsAppTemplate, draft.template_id)
    assert draft.status == template_studio.AWAITING_APPROVAL
    assert draft.generation["image_mode"] == "typeset"
    assert FakeGemini.images == 1  # only the plain photo


def test_the_queue_stops_at_the_first_draft_still_without_an_allowance(db, monkeypatch):
    FakeGemini.allowance = 0
    generate(db)
    generate(db)
    calls = []
    real = template_studio.run_new_photo
    monkeypatch.setattr(photo_queue.studio, "run_new_photo",
                        lambda tid, fresh=True: (calls.append(tid), real(tid, fresh)))
    assert photo_queue.tick(db, now=_dt.now(_tz.utc) + _td(hours=2)) == 1
    assert len(calls) == 1


def test_asking_for_a_new_photo_without_allowance_keeps_the_poster_in_review(db):
    [draft] = generate(db)
    header = draft.header_content
    FakeGemini.allowance = 0
    template_studio.run_new_photo(draft.template_id)
    db.expire_all()
    draft = db.get(WhatsAppTemplate, draft.template_id)
    assert draft.status == template_studio.AWAITING_APPROVAL
    assert draft.header_content == header
    assert "allowance" in draft.generation["error"]


def test_a_draft_waiting_too_long_fails_and_says_why(db):
    FakeGemini.allowance = 0
    [draft] = generate(db)
    for _ in range(template_studio.MAX_PHOTO_WAITS):
        photo_queue.tick(db, now=_dt.now(_tz.utc) + _td(days=3))
    db.expire_all()
    draft = db.get(WhatsAppTemplate, draft.template_id)
    assert draft.status == template_studio.GENERATION_FAILED
    assert "waiting" in draft.generation["error"]
    assert draft.body  # the copy is still there for "Retry photo"


def test_a_restart_settles_drafts_left_generating(db):
    FakeGemini.allowance = 0
    [with_copy] = generate(db)
    with_copy.status = template_studio.GENERATING  # its photo task died with the process
    [no_copy] = template_studio.create_placeholders(db, "Punjab", 1, None)
    db.commit()
    assert photo_queue.recover_after_restart(db) == 2
    assert with_copy.status == template_studio.PHOTO_PENDING
    assert no_copy.status == template_studio.GENERATION_FAILED and "restart" in no_copy.generation["error"]


def test_retry_after_is_read_from_hugging_faces_message():
    from src.services.gemini_client import _retry_after
    assert _retry_after("You have exceeded your free ZeroGPU quota. Try again in 2:05:30.") == 7530
    assert _retry_after("You have exceeded your ZeroGPU runs limit.") is None


# --- the fact check reads only what can make a claim --------------------------

def test_poster_labels_are_not_sent_to_the_fact_check(db):
    generate(db)
    sent = FakeGemini.fact_prompts[0].split("COPY:")[1]
    # Fixed labels came back as "unsupported claims" every round.
    for label in ("bank_name", "sign_title", "cta", "benefits_title", "phone_label", "web_label"):
        assert PA_POSTER[label] not in sent, label
    # The text that can promise something is still read.
    for field in ("callout", "subline", "opportunity_text"):
        assert PA_POSTER[field] in sent, field
    assert all(b["text"] in sent for b in PA_POSTER["benefits"])
    assert "are names, not claims" in FakeGemini.fact_prompts[0]


# --- a cut-off answer from the vision model -----------------------------------

class SeqG4F:
    """A g4f stand-in answering each call with the next of `answers`."""

    def __init__(self, answers):
        self.answers, self.calls = list(answers), 0
        self.chat = self.completions = self

    def create(self, model, messages, **kwargs):
        self.calls += 1
        msg = type("M", (), {"content": self.answers.pop(0)})()
        return type("R", (), {"choices": [type("C", (), {"message": msg})()]})()


def test_a_cut_off_vision_answer_is_asked_again(monkeypatch):
    from src.services import gemini_client as gc

    fake = SeqG4F(['```json\n{"sign_text": "ਆਪਣਾ ਕਾਰ', '{"sign_text": "ਆਪਣਾ ਕਾਰੋਬਾਰ ਵਧਾਓ", "issues": []}'])
    monkeypatch.setattr(gc, "G4FClient", lambda: fake)
    check = gc.GeminiClient().inspect_image(PNG, "image/png", "read the sign")
    assert check["sign_text"] == "ਆਪਣਾ ਕਾਰੋਬਾਰ ਵਧਾਓ"
    assert fake.calls == 2


def test_two_unreadable_vision_answers_give_up(monkeypatch):
    from src.services import gemini_client as gc

    monkeypatch.setattr(gc, "G4FClient", lambda: SeqG4F(['{"sign_text": "ਆ', "sorry"]))
    with pytest.raises(gc.GeminiError, match="could not be read"):
        gc.GeminiClient().inspect_image(PNG, "image/png", "read the sign")


def test_an_unread_sign_is_recorded_as_unchecked_not_misspelt(db, monkeypatch):
    from src.services.gemini_client import GeminiError

    with_phrase(monkeypatch, [])
    FakeGemini.checks = [GeminiError("the free vision model's answer could not be read"), GOOD_CHECK]
    [draft] = generate(db)
    [attempt] = draft.generation["text_photo_attempts"]
    assert attempt["checked"] is False and attempt["passed"] is False
    assert draft.generation["image_mode"] == "typeset"


def test_a_phrase_edited_out_of_the_copy_is_not_printed(db, monkeypatch):
    with_phrase(monkeypatch, [PHRASE])
    [draft] = generate(db)
    poster = {**draft.generation["poster"], "headline_line2": "ਨਵੀਂ ਲਾਈਨ ਇੱਥੇ"}
    draft.generation = {**draft.generation, "poster": poster}
    db.commit()
    FakeGemini.images = 0
    template_studio.run_new_photo(draft.template_id)
    db.expire_all()
    draft = db.get(WhatsAppTemplate, draft.template_id)
    # No sign attempt for a phrase no longer in the copy: just the plain photo.
    assert FakeGemini.images == 1
    assert draft.generation["image_mode"] == "typeset"


# --- keeping track of which image prompts work --------------------------------

from src.models.studio import StudioImagePrompt  # noqa: E402
from src.services import image_prompts  # noqa: E402


def records(db, **where):
    db.expire_all()
    q = db.query(StudioImagePrompt).order_by(StudioImagePrompt.created_at, StudioImagePrompt.prompt_id)
    return [r for r in q.all() if all(getattr(r, k) == v for k, v in where.items())]


def add_record(db, kind="plain", style="documentary", passed=True, outcome="in_review", **kw):
    db.add(StudioImagePrompt(prompt_id=uuid.uuid4().hex, created_at=_dt.now(_tz.utc), kind=kind,
                             style=style, prompt="p",
                             scene=kw.pop("scene", f"scene {uuid.uuid4().hex[:6]}"), passed=passed,
                             checked=True, outcome=outcome, **kw))
    db.commit()


def test_every_photo_is_recorded_with_its_prompt_and_verdict(db):
    [draft] = generate(db)
    [r] = records(db)
    assert r.template_id == draft.template_id and r.kind == "plain"
    assert r.prompt == draft.generation["photo_prompt"] and r.scene == PA_VARIANT["photo_scene"]
    assert r.style in image_prompts.STYLES and isinstance(r.seed, int)
    assert r.passed and r.outcome == "in_review" and r.media_id == draft.generation["photo_media_id"]


def test_a_gibberish_sign_is_recorded_with_what_it_said(db, monkeypatch):
    with_phrase(monkeypatch, ["ਦੋਰ ਸਵੇ"])
    generate(db)
    [sign] = records(db, kind="sign")
    assert sign.gibberish and not sign.passed and sign.outcome == "unused"
    assert 'came out as "ਦੋਰ ਸਵੇ"' in sign.note and sign.phrase == PHRASE


def test_the_reviewers_verdict_is_recorded(db, monkeypatch):
    monkeypatch.setenv("MOCK_WHATSAPP_API", "true")
    [kept] = generate(db)
    studio_router.approve_draft(kept.template_id, None, db=db, user=FakeUser())
    assert [r.outcome for r in records(db, template_id=kept.template_id)] == ["kept"]

    [redone] = generate(db)
    template_studio.run_new_photo(redone.template_id)
    assert [r.outcome for r in records(db, template_id=redone.template_id)] == ["replaced", "in_review"]

    [dropped] = generate(db)
    studio_router.reject_draft(dropped.template_id, studio_router.RejectRequest(reason="dull photo"),
                               db=db, user=FakeUser())
    assert [r.outcome for r in records(db, template_id=dropped.template_id)] == ["draft_rejected"]


def test_the_style_with_the_better_record_is_used(db):
    # Untried, both score the same and the one the team liked goes first.
    assert image_prompts.choose_style(db, "plain") == "short"
    add_record(db, style="short", passed=False, outcome="unused")
    # One failure: the untried style is tried before it is used again.
    assert image_prompts.choose_style(db, "plain") == "documentary"
    add_record(db, style="documentary", passed=True, outcome="kept")
    add_record(db, style="documentary", passed=True, outcome="replaced")  # the reviewer disliked it
    add_record(db, style="documentary", passed=True, outcome="kept")
    assert image_prompts.choose_style(db, "plain") == "documentary"
    [draft] = generate(db)
    assert draft.generation["photo_style"] == "documentary"


def test_signs_are_skipped_while_they_keep_coming_out_wrong(db, monkeypatch):
    for _ in range(5):
        add_record(db, kind="sign", passed=False, outcome="unused", gibberish=True)
    with_phrase(monkeypatch, [PHRASE])
    [draft] = generate(db)
    assert draft.generation["sign_skipped"] is True
    assert FakeGemini.images == 1, "no image spent on a sign"
    # Tried again once a few plain photos have been made since.
    for _ in range(image_prompts.RETEST_EVERY - 2):
        add_record(db)
    assert image_prompts.sign_worth_trying(db)


def test_the_next_round_is_told_what_worked_and_what_failed(db):
    add_record(db, scene="A woman operator hands a passbook to a farmer", outcome="kept")
    add_record(db, kind="sign", scene="A crowded kiosk at dusk", phrase="ਆਪਣਾ ਕਾਰੋਬਾਰ ਵਧਾਓ", passed=False,
               outcome="unused", gibberish=True, note='sign came out as "ਦੋਰ ਸਵੇ" instead of "ਆਪਣਾ ਕਾਰੋਬਾਰ ਵਧਾਓ"')
    generate(db)
    prompt = FakeGemini.prompts[-1]
    section = prompt.split("PHOTOS SO FAR")[1]
    assert 'WORKED: "A woman operator hands a passbook to a farmer" (clean photo, kept by the reviewer)' in section
    assert 'FAILED: "A crowded kiosk at dusk"' in section and 'came out as "ਦੋਰ ਸਵੇ"' in section
    assert "0 of 1 came out spelled right" in section


def test_no_photo_section_before_any_photo(db):
    generate(db)
    assert "PHOTOS SO FAR" not in FakeGemini.prompts[0]


def test_the_record_is_shown_on_the_studio_page(db):
    generate(db)
    out = studio_router.image_prompt_record(db=db)
    assert {s["style"] for s in out["styles"]} == set(image_prompts.STYLES)
    assert sum(s["chosen_next"] for s in out["styles"] if s["kind"] == "plain") == 1
    assert out["recent"][0]["prompt"].startswith(("A candid", "Candid"))


# --- Odia, and how the kiosk must look ----------------------------------------

def test_odisha_is_written_in_odia_and_registered_as_en_us():
    assert creative_brief.language_for_state("Odisha") == "or"
    assert creative_brief.LANGUAGES["or"]["script"] == "Odia"
    # Meta lists no Odia; the template is registered under en_US, as the
    # team's Hindi ones were, and still written and checked in Odia.
    assert creative_brief.meta_language("or") == "en_US"
    assert creative_brief.meta_language("hi") == "hi"
    assert creative_brief.script_problems("ବ୍ୟବସାୟ ବଢ଼ାନ୍ତୁ", "or") == []
    assert creative_brief.script_problems("व्यापार", "or")  # Devanagari in an Odia template


def test_an_odia_draft_is_submitted_to_meta_as_en_us(db, monkeypatch):
    monkeypatch.setenv("MOCK_WHATSAPP_API", "true")
    from src.services.whatsapp_service import WhatsAppTemplateSubmissionService

    sent = {}
    real = WhatsAppTemplateSubmissionService.submit

    def spy(self, template, category="MARKETING"):
        sent["before"] = template.language_code
        out = real(self, template, category)
        sent["after"] = template.language_code
        return out

    monkeypatch.setattr(WhatsAppTemplateSubmissionService, "submit", spy)
    t = WhatsAppTemplate(template_id=uuid.uuid4().hex, name="Odisha Studio x", language_code="or",
                         category="MARKETING", body="ନମସ୍କାର, +91 7291988625", status="AWAITING_APPROVAL",
                         origin="agent", generation={})
    db.add(t)
    db.commit()
    template_studio.approve(db, t, "reviewer@eko.co.in")
    assert sent == {"before": "or", "after": "en_US"}


@pytest.mark.parametrize("kind_phrase", [None, "ਆਪਣਾ ਕਾਰੋਬਾਰ ਵਧਾਓ"])
def test_every_image_prompt_asks_for_a_professional_operator_and_a_real_csp_wall(kind_phrase):
    for style in image_prompts.STYLES:
        prompt = image_prompts.build(style, "A scene.", "Punjab", kind_phrase, "pa" if kind_phrase else None)
        assert "professional attire" in prompt and "saree, kurti or salwar suit" in prompt
        assert "Not a sage, monk, priest or holy man" in prompt
        assert "SBI-blue banners" in prompt and "out of focus" in prompt


def test_a_sage_looking_operator_fails_the_photo_check(db):
    FakeGemini.checks = [{**GOOD_CHECK, "operator_professional": False}]
    [draft] = generate(db)
    assert draft.generation["photo_check"]["passed"] is False
    [r] = records(db)
    assert not r.passed and "did not look like a professional" in r.note


# --- the day's image allowance ------------------------------------------------

def test_the_allowance_counts_down_and_says_when_it_resets(db, monkeypatch):
    monkeypatch.setattr(image_prompts, "DAILY_IMAGE_LIMIT", 5)
    now = _dt.now(_tz.utc)
    a = image_prompts.allowance(db, now)
    assert (a["used"], a["remaining"], a["reached"], a["resets_at"]) == (0, 5, False, None)

    first = now - _td(hours=3)
    db.add(StudioImagePrompt(prompt_id=uuid.uuid4().hex, created_at=first, kind="plain", style="short", prompt="p"))
    db.commit()
    a = image_prompts.allowance(db, now)
    assert (a["used"], a["remaining"]) == (1, 4)

    for i in range(4):
        add_record(db)
    a = image_prompts.allowance(db, now + _td(minutes=1))
    assert a["reached"] and a["remaining"] == 0
    # Hugging Face's day starts with the first image and lasts 24 hours.
    assert _dt.fromisoformat(a["resets_at"]) == first + _td(hours=24)
    # Past it, the day starts again.
    assert image_prompts.allowance(db, first + _td(hours=25))["remaining"] == 5


def test_a_refusal_from_hugging_face_shows_its_own_reset_time(db, monkeypatch):
    monkeypatch.setattr(image_prompts, "DAILY_IMAGE_LIMIT", 5)
    FakeGemini.allowance = 0  # the fake refuses: "Try again in 1:00:00"
    generate(db)
    a = image_prompts.allowance(db)
    assert a["reached"] and a["refused_by_provider"]
    left = _dt.fromisoformat(a["resets_at"]) - _dt.now(_tz.utc)
    assert _td(minutes=55) < left <= _td(hours=1)


# --- drafts that do not all look alike ----------------------------------------

from src.services import variety  # noqa: E402


def test_variants_of_a_round_get_different_layouts_shots_and_shapes(db):
    plans = variety.plan(db, 3)
    for key in ("layout", "shot", "shape"):
        assert len({p[key] for p in plans}) == 3, key
    assert {p["operator"] for p in plans} == {"man", "woman"}


def test_the_next_round_uses_what_was_used_least(db):
    first = generate(db)[0].generation
    second = generate(db)[0].generation
    assert first["layout"] != second["layout"]
    assert first["shot"] != second["shot"]
    assert first["shape"] != second["shape"]


def test_the_layout_shot_and_operator_reach_the_poster_and_the_photo(db, monkeypatch):
    used = []
    monkeypatch.setattr(template_studio.poster_renderer, "render",
                        lambda poster, lang, photo, mime, layout="classic": used.append(layout) or b"\xff\xd8P")
    [draft] = generate(db)
    gen = draft.generation
    assert used == [gen["layout"]]
    assert variety.SHOTS[gen["shot"]] in gen["photo_prompt"]
    assert variety.OPERATORS[gen["operator"]] in gen["photo_prompt"]


def test_the_writer_is_told_each_variants_shape_and_what_not_to_repeat(db):
    generate(db)
    prompt = FakeGemini.prompts[-1]
    assert "MAKE EACH VARIANT DIFFERENT" in prompt and "message shape:" in prompt
    generate(db)
    prompt = FakeGemini.prompts[-1]
    headline = f'{PA_POSTER["headline_line1"]} / {PA_POSTER["headline_line2"]}'
    assert "HEADLINES ALREADY USED" in prompt and headline in prompt
