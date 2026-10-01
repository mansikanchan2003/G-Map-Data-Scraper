"""
Templates read back out of a sheet of written-out messages.

The derivation has to be right before anything else matters: a wrong guess
would send someone wording that was never written for them. So the cases
here are mostly about what it must refuse.
"""
import uuid
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.database import Base
from src.models.whatsapp import WhatsAppCampaign, WhatsAppCampaignRecipient, WhatsAppTemplate
from src.services import sheet_templates as st
from src.services.sheet_templates import DerivationError, derive


def rows(*messages, **columns):
    out = []
    for i, m in enumerate(messages):
        row = {"phone": f"91980000000{i}", "message": m}
        row.update({k: v[i] for k, v in columns.items()})
        out.append(row)
    return out


class TestDerive:
    def test_varying_columns_become_variables(self):
        d = derive(rows(
            "Hi Ramesh Kumar, your balance is Rs 500 as of today.",
            "Hi Priya Singh, your balance is Rs 750 as of today.",
            name=["Ramesh Kumar", "Priya Singh"], amount=["500", "750"],
        ), "message", "phone")
        assert d["body"] == "Hi {{name}}, your balance is Rs {{amount}} as of today."
        assert d["variables"] == ["name", "amount"]
        assert d["columns"] == {"name": "name", "amount": "amount"}
        assert d["examples"] == {"name": "Ramesh Kumar", "amount": "500"}

    def test_headers_become_placeholder_names(self):
        d = derive([
            {"Mobile": "1", "Text": "Dear Ram, pay by 5 Oct please.", "Due Date": "5 Oct", "Customer Name": "Ram"},
            {"Mobile": "2", "Text": "Dear Sita, pay by 9 Oct please.", "Due Date": "9 Oct", "Customer Name": "Sita"},
        ], "Text", "Mobile")
        assert d["body"] == "Dear {{customer_name}}, pay by {{due_date}} please."
        assert d["columns"] == {"customer_name": "Customer Name", "due_date": "Due Date"}

    def test_a_column_that_never_changes_stays_fixed_text(self):
        d = derive(rows(
            "Hi Ram, the Delhi office is open.", "Hi Sita, the Delhi office is open.",
            name=["Ram", "Sita"], city=["Delhi", "Delhi"],
        ), "message", "phone")
        assert d["body"] == "Hi {{name}}, the Delhi office is open."

    def test_a_short_value_inside_a_longer_word_is_left_alone(self):
        d = derive(rows(
            "Hi Ram, Ramesh will call you.", "Hi Om, Ramesh will call you.",
            name=["Ram", "Om"],
        ), "message", "phone")
        assert d["body"] == "Hi {{name}}, Ramesh will call you."

    def test_longer_values_are_placed_before_shorter_ones_inside_them(self):
        d = derive(rows(
            "Hello Ramesh Kumar (Ramesh), welcome.", "Hello Priya Singh (Priya), welcome.",
            full=["Ramesh Kumar", "Priya Singh"], first=["Ramesh", "Priya"],
        ), "message", "phone")
        assert d["body"] == "Hello {{full}} ({{first}}), welcome."

    def test_messages_worded_differently_are_refused(self):
        with pytest.raises(DerivationError, match="Rows 2 and 3"):
            derive(rows(
                "Hi Ram, your order shipped today.", "Hi Sita, your order arrives tomorrow.",
                name=["Ram", "Sita"],
            ), "message", "phone")

    def test_starting_with_a_variable_is_refused(self):
        with pytest.raises(DerivationError, match="begins with a variable"):
            derive(rows("Ram, your order shipped.", "Sita, your order shipped.",
                        name=["Ram", "Sita"]), "message", "phone")

    def test_ending_with_a_variable_is_refused(self):
        with pytest.raises(DerivationError, match="ends with a variable"):
            derive(rows("Your agent is Ram", "Your agent is Sita",
                        name=["Ram", "Sita"]), "message", "phone")

    def test_an_empty_message_is_refused(self):
        with pytest.raises(DerivationError, match="Row 3 has no message"):
            derive(rows("Hi Ram, hello.", "", name=["Ram", "Sita"]), "message", "phone")

    def test_identical_messages_make_a_template_with_no_variables(self):
        d = derive(rows("Our office is closed tomorrow.", "Our office is closed tomorrow."),
                   "message", "phone")
        assert d["body"] == "Our office is closed tomorrow." and d["variables"] == []

    def test_a_link_column_does_not_collide_with_the_tracking_link(self):
        d = derive(rows("Hi, see https://a.in/1 today.", "Hi, see https://a.in/2 today.",
                        link=["https://a.in/1", "https://a.in/2"]), "message", "phone")
        assert d["body"] == "Hi, see {{link_value}} today."

    def test_indic_text(self):
        d = derive(rows("नमस्ते राम, आपका खाता तैयार है।", "नमस्ते सीता, आपका खाता तैयार है।",
                        नाम=["राम", "सीता"]), "message", "phone")
        key = st.column_key("नाम")
        assert d["body"] == "नमस्ते {{%s}}, आपका खाता तैयार है।" % key


def test_matching_ignores_punctuation_and_emoji_but_not_words():
    a = "Hi {{name}}, your balance is ready! 🎉"
    assert st.normalise(a) == st.normalise("Hi {{name}} your balance is ready.")
    assert st.normalise(a) != st.normalise("Hi {{amount}}, your balance is ready!")
    assert st.normalise(a) != st.normalise("Hi {{name}}, your bill is ready!")


def test_parameters_lose_newlines():
    assert st.clean_parameter("line one\nline two\t\tend") == "line one line two end"


# ---------------------------------------------------------------------------
# The round against Meta
# ---------------------------------------------------------------------------

@pytest.fixture
def db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    st._last_refresh = 0.0
    yield session
    session.close()


SHEET = rows("Hi Ram, your kit ships on Monday.", "Hi Sita, your kit ships on Tuesday.",
             name=["Ram", "Sita"], day=["Monday", "Tuesday"])


def fake_meta(state):
    """A stand-in WABA: submissions land PENDING, listing reports `state`."""
    def submit(self, template, category="MARKETING"):
        state.setdefault("submitted", []).append(template.meta_template_name)
        template.status = "PENDING"
        template.category = category
        self.db.commit()
        return {"status": "success", "meta_template_name": template.meta_template_name}

    def listing(self):
        return {"status": "success", "templates": [
            {"name": n, "language": "en_US", "status": state.get("status", "PENDING"),
             "category": "MARKETING", "rejected_reason": state.get("reason")}
            for n in state.get("submitted", [])
        ]}
    return submit, listing


def run(db, state, sheet=SHEET):
    submit, listing = fake_meta(state)
    with patch("src.services.whatsapp_service.WhatsAppTemplateSubmissionService.submit", submit), \
         patch("src.services.meta_whatsapp_service.MetaWhatsAppService.list_message_templates", listing):
        return st.template_from_messages(db, sheet, "message", "phone", language="en_US",
                                         source_name="kits.xlsx")


def test_submits_once_then_follows_the_review(db):
    state = {}
    first = run(db, state)
    assert first["action"] == "created"
    assert first["template"].origin == "sheet"
    assert first["template"].body == "Hi {{name}}, your kit ships on {{day}}."
    assert first["template"].name == "From kits"

    again = run(db, state)
    assert again["action"] == "pending"
    assert len(state["submitted"]) == 1, "the same sheet must not be submitted twice"

    state["status"] = "APPROVED"
    assert run(db, state)["action"] == "ready"
    assert db.query(WhatsAppTemplate).count() == 1


def test_a_rejection_is_reported_with_metas_reason(db):
    state = {}
    run(db, state)
    state.update(status="REJECTED", reason="INVALID_FORMAT")
    out = run(db, state)
    assert out["action"] == "rejected"
    assert "invalid format" in out["reason"]
    assert len(state["submitted"]) == 1


def test_an_approved_template_with_the_same_wording_is_reused(db):
    db.add(WhatsAppTemplate(template_id="t1", name="Kits", status="APPROVED", origin="manual",
                            meta_template_name="kits_v1", language_code="en_US",
                            body="Hi {{name}} - your kit ships on {{day}}!",
                            buttons=[{"type": "URL", "text": "Apply now!", "url": "https://x/r/{{1}}"}]))
    db.commit()
    state = {"submitted": ["kits_v1"], "status": "APPROVED"}
    out = run(db, state)
    assert out["action"] == "ready" and out["template"].template_id == "t1"
    assert state["submitted"] == ["kits_v1"]


def test_the_same_wording_without_the_apply_button_is_not_reused(db):
    """It would send the message without the link the visit is tracked through."""
    db.add(WhatsAppTemplate(template_id="t1", name="Kits", status="APPROVED", origin="manual",
                            meta_template_name="kits_v1", language_code="en_US",
                            body="Hi {{name}}, your kit ships on {{day}}.", buttons=[]))
    db.commit()
    out = run(db, {"submitted": ["kits_v1"], "status": "APPROVED"})
    assert out["template"].template_id != "t1"


def test_a_refused_submission_is_retried_on_the_same_row(db):
    calls = []

    def refuse(self, template, category="MARKETING"):
        calls.append(template.meta_template_name)
        return {"status": "failed", "error": "Invalid parameter"}

    with patch("src.services.whatsapp_service.WhatsAppTemplateSubmissionService.submit", refuse), \
         patch("src.services.meta_whatsapp_service.MetaWhatsAppService.list_message_templates",
               lambda self: {"status": "success", "templates": []}):
        out = st.template_from_messages(db, SHEET, "message", "phone")
        assert out["action"] == "failed" and out["reason"] == "Invalid parameter"
        st.template_from_messages(db, SHEET, "message", "phone")
    assert db.query(WhatsAppTemplate).count() == 1
    assert calls[0] != calls[1], "a retry registers under a fresh name"


# ---------------------------------------------------------------------------
# Sending one
# ---------------------------------------------------------------------------

def sheet_template(db):
    t = WhatsAppTemplate(template_id=uuid.uuid4().hex, name="From kits", origin="sheet",
                         status="APPROVED", meta_template_name="auto_x", language_code="en_US",
                         body="Hi {{name}}, your kit ships on {{day}}.", buttons=[],
                         generation={"variables": ["name", "day"],
                                     "examples": {"name": "Ram", "day": "Monday"}})
    db.add(t)
    db.commit()
    return t


def test_meta_is_shown_the_sheets_own_example_values(db):
    from src.services.whatsapp_service import build_meta_components

    body = next(c for c in build_meta_components(sheet_template(db)) if c["type"] == "BODY")
    assert body["text"] == "Hi {{1}}, your kit ships on {{2}}."
    assert body["example"] == {"body_text": [["Ram", "Monday"]]}


def test_recipients_without_a_value_are_skipped(db):
    from src.services.whatsapp_service import WhatsAppCampaignService

    t = sheet_template(db)
    campaign = WhatsAppCampaignService(db).create_campaign_and_recipients(
        name="kits", template_id=t.template_id, account_id=None, data_source_type="upload",
        contacts=[
            {"phone": "9876543210", "name": "Ram", "variables": {"Name": "Ram", "Day": "Monday"}},
            {"phone": "9876543211", "name": "Sita", "variables": {"Name": "Sita"}},
        ],
    )
    recs = {r.phone: r for r in db.query(WhatsAppCampaignRecipient)
            .filter(WhatsAppCampaignRecipient.campaign_id == campaign.campaign_id)}
    assert recs["+919876543210"].status == "PENDING"
    assert recs["+919876543210"].variables == {"name": "Ram", "day": "Monday"}
    assert recs["+919876543211"].status == "SKIPPED"
    assert recs["+919876543211"].reason == "No value for {{day}}"
    assert campaign.pending_count == 1 and campaign.skipped_count == 1


def test_each_recipient_is_sent_their_own_values(db):
    from src.services.whatsapp_service import parameter_value, template_placeholders

    t = sheet_template(db)
    rec = WhatsAppCampaignRecipient(recipient_id="r", campaign_id="c", phone="+919876543210",
                                    name="Ram", variables={"name": "Ram", "day": "Mon\nday"})
    assert [parameter_value(rec, p) for p in template_placeholders(t)] == ["Ram", "Mon day"]


def test_older_templates_keep_only_name_and_link():
    from src.services.whatsapp_service import template_placeholders

    class T:
        origin = "manual"
        generation = None
        body = "Hi {{name}}, {{business}} - {{link}}"
    assert template_placeholders(T()) == ["{{name}}", "{{link}}"]


# ---------------------------------------------------------------------------
# The tracked link
# ---------------------------------------------------------------------------

def test_the_template_carries_a_tracked_apply_button(db, monkeypatch):
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://indev.eko.in/autogmap")
    out = run(db, {})
    t = out["template"]
    assert t.buttons == [{"type": "URL", "text": "Apply Now",
                          "url": "https://indev.eko.in/autogmap/r/{{1}}"}]
    assert t.generation["link_target"] == st.DEFAULT_LINK_TARGET
    assert t.generation["tracked"] is True


def test_without_a_public_url_the_button_opens_the_page_directly(db, monkeypatch):
    monkeypatch.delenv("PUBLIC_BASE_URL", raising=False)
    t = run(db, {})["template"]
    assert t.buttons[0]["url"] == st.DEFAULT_LINK_TARGET
    assert t.generation["tracked"] is False


def test_a_site_link_in_the_messages_becomes_the_tracked_link():
    d = derive(rows("Hi Ram, apply at https://kiosk.eko.in/signup. Thanks!",
                    "Hi Sita, apply at https://kiosk.eko.in/signup. Thanks!",
                    name=["Ram", "Sita"]), "message", "phone")
    assert d["body"] == "Hi {{name}}, apply at {{link}}. Thanks!"
    assert d["variables"] == ["name"] and d["tracked_link_in_body"] is True


def test_a_visit_is_recorded_and_lands_on_apply_now(db):
    from fastapi.testclient import TestClient
    from src.database import get_db
    from src.main import app
    from src.models.whatsapp import WhatsAppLinkClick

    t = sheet_template(db)
    t.generation = {**t.generation, "link_target": st.DEFAULT_LINK_TARGET}
    db.add(WhatsAppCampaign(campaign_id="c1", name="Kits Oct", data_source_type="upload",
                            template_id=t.template_id))
    db.add(WhatsAppCampaignRecipient(recipient_id="r1", campaign_id="c1", phone="+919876543210",
                                     tracking_token="tok123", status="SENT"))
    db.commit()

    app.dependency_overrides[get_db] = lambda: db
    try:
        res = TestClient(app).get("/r/tok123", follow_redirects=False,
                                  headers={"user-agent": "Mozilla/5.0 (Linux; Android 14) Mobile"})
    finally:
        app.dependency_overrides.pop(get_db, None)
    assert res.status_code == 302
    assert res.headers["location"] == (
        "https://kiosk.eko.in/?utm_source=AutoGMap&utm_medium=whatsapp"
        "&utm_campaign=Kits+Oct#apply-now")
    click = db.query(WhatsAppLinkClick).one()
    assert click.recipient_id == "r1" and click.automated_reason is None
