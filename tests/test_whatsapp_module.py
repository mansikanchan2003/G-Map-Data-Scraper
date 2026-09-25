import os
import json
import hmac
import hashlib
import time
import pytest
from unittest.mock import patch, MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.main import app
from src.database import get_db

# --- Setup App for Webhook Tests ---
# Mock DB for webhook so it doesn't try to connect to postgres
def override_get_db():
    yield MagicMock()

app.dependency_overrides[get_db] = override_get_db
client = TestClient(app)

@pytest.fixture
def mock_env():
    with patch.dict(os.environ, {
        "META_APP_SECRET": "test_secret_123",
        "WHATSAPP_META_MAX_RETRIES": "3",
        "WHATSAPP_META_INITIAL_BACKOFF_SECONDS": "0.01" # fast for tests
    }):
        yield

@pytest.fixture(autouse=True)
def mock_preflight():
    """
    execute_campaign() validates the template against the Meta WABA before
    sending. Default it to "approved" so send-path tests are unaffected;
    the pre-flight behaviour itself is covered by its own tests.
    """
    with patch(
        "src.services.meta_whatsapp_service.MetaWhatsAppService.find_approved_template",
        return_value={"ok": True, "error": None, "available": ["hello_world (en_US)"]},
    ) as m:
        yield m


def generate_signature(payload: bytes, secret: str) -> str:
    return "sha256=" + hmac.new(secret.encode('utf-8'), payload, hashlib.sha256).hexdigest()

# --- Webhook Tests ---

def test_webhook_missing_signature(mock_env):
    response = client.post("/api/v1/whatsapp/webhook", json={"test": "payload"})
    assert response.status_code == 403
    assert "Missing or malformed signature" in response.json()["detail"]

def test_webhook_malformed_signature(mock_env):
    response = client.post("/api/v1/whatsapp/webhook", json={"test": "payload"}, headers={"X-Hub-Signature-256": "invalid_format"})
    assert response.status_code == 403
    assert "Missing or malformed signature" in response.json()["detail"]

def test_webhook_invalid_signature(mock_env):
    payload_bytes = json.dumps({"test": "payload"}).encode('utf-8')
    invalid_signature = generate_signature(payload_bytes, "wrong_secret")
    response = client.post(
        "/api/v1/whatsapp/webhook",
        content=payload_bytes,
        headers={"X-Hub-Signature-256": invalid_signature}
    )
    assert response.status_code == 403
    assert "Invalid signature" in response.json()["detail"]

def test_webhook_valid_signature(mock_env):
    payload_bytes = json.dumps({"test": "payload"}).encode('utf-8')
    valid_signature = generate_signature(payload_bytes, "test_secret_123")
    response = client.post(
        "/api/v1/whatsapp/webhook",
        content=payload_bytes,
        headers={"X-Hub-Signature-256": valid_signature}
    )
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


# --- Retry Tests ---
from src.services.whatsapp_service import WhatsAppCampaignService
from src.models.whatsapp import WhatsAppCampaign, WhatsAppCampaignRecipient, WhatsAppTemplate


@pytest.fixture
def mock_db_session():
    mock_db = MagicMock()
    mock_campaign = MagicMock()
    mock_campaign.campaign_id = "camp1"
    mock_campaign.status = "PENDING"
    mock_campaign.template_id = "temp1"

    mock_template = MagicMock()
    mock_template.template_id = "temp1"
    mock_template.name = "hello_world"
    mock_template.meta_template_name = None
    mock_template.language_code = "en_US"
    mock_template.body = "hello {{name}}"

    mock_recipient = MagicMock()
    mock_recipient.recipient_id = "rec1"
    mock_recipient.campaign_id = "camp1"
    mock_recipient.status = "PENDING"
    mock_recipient.phone = "+919999999999"
    mock_recipient.name = "Test"

    q_rec = MagicMock()
    q_rec.filter.return_value.with_for_update.return_value.limit.return_value.all.side_effect = [[mock_recipient], []]
    q_rec.filter.return_value.all.return_value = [mock_recipient]

    # Setup the query chain for db
    def query_side_effect(model):
        q = MagicMock()
        if model == WhatsAppCampaign:
            q.filter.return_value.first.return_value = mock_campaign
            return q
        elif model == WhatsAppTemplate:
            q.filter.return_value.first.return_value = mock_template
            return q
        elif model == WhatsAppCampaignRecipient:
            return q_rec
        return q

    mock_db.query.side_effect = query_side_effect
    return mock_db, mock_campaign, mock_recipient

@patch("src.services.whatsapp_service.time.sleep", return_value=None)
@patch("src.database.SessionLocal")
def test_immediate_success(mock_session_local, mock_sleep, mock_db_session, mock_env):
    mock_db, camp, rec = mock_db_session
    mock_session_local.return_value = mock_db

    service = WhatsAppCampaignService(mock_db)
    with patch.object(service.meta_service, 'send_template_message', return_value=(True, "msg1", "200", None, None)) as mock_send:
        service.execute_campaign("camp1")
        assert mock_send.call_count == 1
        assert rec.status == "SENT"

@patch("src.services.whatsapp_service.time.sleep", return_value=None)
@patch("src.database.SessionLocal")
def test_transient_500_then_success(mock_session_local, mock_sleep, mock_db_session, mock_env):
    mock_db, camp, rec = mock_db_session
    mock_session_local.return_value = mock_db

    service = WhatsAppCampaignService(mock_db)
    with patch.object(service.meta_service, 'send_template_message', side_effect=[
        (False, None, "500", "Server Error", None),
        (True, "msg2", "200", None, None)
    ]) as mock_send:
        service.execute_campaign("camp1")
        assert mock_send.call_count == 2
        assert rec.status == "SENT"

@patch("src.services.whatsapp_service.time.sleep", return_value=None)
@patch("src.database.SessionLocal")
def test_repeated_transient_until_limit(mock_session_local, mock_sleep, mock_db_session, mock_env):
    mock_db, camp, rec = mock_db_session
    mock_session_local.return_value = mock_db

    service = WhatsAppCampaignService(mock_db)
    # limit is 3 retries (4 total attempts)
    with patch.object(service.meta_service, 'send_template_message', side_effect=[
        (False, None, "503", "Service Unavailable", None),
        (False, None, "429", "Rate Limit", None),
        (False, None, None, "Network Timeout", None),
        (False, None, "502", "Bad Gateway", None),
    ]) as mock_send:
        service.execute_campaign("camp1")
        assert mock_send.call_count == 4
        assert rec.status == "FAILED"
        assert mock_sleep.call_count >= 3 # sleep called for backoff

@patch("src.services.whatsapp_service.time.sleep", return_value=None)
@patch("src.database.SessionLocal")
def test_permanent_400_no_retry(mock_session_local, mock_sleep, mock_db_session, mock_env):
    mock_db, camp, rec = mock_db_session
    mock_session_local.return_value = mock_db

    service = WhatsAppCampaignService(mock_db)
    with patch.object(service.meta_service, 'send_template_message', return_value=(False, None, "400", "Bad Request", None)) as mock_send:
        service.execute_campaign("camp1")
        assert mock_send.call_count == 1
        assert rec.status == "FAILED"

@patch("src.services.whatsapp_service.time.sleep", return_value=None)
@patch("src.database.SessionLocal")
def test_permanent_401_no_retry(mock_session_local, mock_sleep, mock_db_session, mock_env):
    mock_db, camp, rec = mock_db_session
    mock_session_local.return_value = mock_db

    service = WhatsAppCampaignService(mock_db)
    with patch.object(service.meta_service, 'send_template_message', return_value=(False, None, "401", "Unauthorized", None)) as mock_send:
        service.execute_campaign("camp1")
        assert mock_send.call_count == 1
        assert rec.status == "FAILED"

# --- Template Payload Tests ---
@patch("src.services.whatsapp_service.time.sleep", return_value=None)
@patch("src.database.SessionLocal")
def test_template_payload_image_header(mock_session_local, mock_sleep, mock_db_session, mock_env):
    mock_db, camp, rec = mock_db_session
    # Change campaign update to return 1 (claimed)
    mock_db.query.return_value.filter.return_value.update.return_value = 1

    template = mock_db.query.side_effect(WhatsAppTemplate).filter().first()
    template.header_type = "IMAGE"
    template.header_content = "http://example.com/img.jpg"

    mock_session_local.return_value = mock_db
    service = WhatsAppCampaignService(mock_db)

    with patch.object(service.meta_service, 'send_template_message', return_value=(True, "msg1", "200", None, None)) as mock_send:
        service.execute_campaign("camp1")

        args, kwargs = mock_send.call_args
        components = kwargs.get("components")

        header_comp = [c for c in components if c["type"] == "header"][0]
        assert header_comp["parameters"][0]["type"] == "image"
        assert header_comp["parameters"][0]["image"]["link"] == "http://example.com/img.jpg"

@patch("src.services.whatsapp_service.time.sleep", return_value=None)
@patch("src.database.SessionLocal")
def test_template_payload_missing_media(mock_session_local, mock_sleep, mock_db_session, mock_env):
    mock_db, camp, rec = mock_db_session
    mock_db.query.return_value.filter.return_value.update.return_value = 1

    template = mock_db.query.side_effect(WhatsAppTemplate).filter().first()
    template.header_type = "VIDEO"
    template.header_content = None # Missing

    mock_session_local.return_value = mock_db
    service = WhatsAppCampaignService(mock_db)

    with patch.object(service.meta_service, 'send_template_message') as mock_send:
        service.execute_campaign("camp1")
        assert mock_send.call_count == 0
        assert camp.status == "FAILED"

@patch("src.services.whatsapp_service.time.sleep", return_value=None)
@patch("src.database.SessionLocal")
def test_template_payload_buttons(mock_session_local, mock_sleep, mock_db_session, mock_env):
    mock_db, camp, rec = mock_db_session
    mock_db.query.return_value.filter.return_value.update.return_value = 1

    template = mock_db.query.side_effect(WhatsAppTemplate).filter().first()
    template.header_type = "NONE"
    template.buttons = [
        {"type": "URL", "text": "Visit", "url": "dynamic1"},
        {"type": "QUICK_REPLY", "text": "ReplyMe"}
    ]

    mock_session_local.return_value = mock_db
    service = WhatsAppCampaignService(mock_db)

    with patch.object(service.meta_service, 'send_template_message', return_value=(True, "msg1", "200", None, None)) as mock_send:
        service.execute_campaign("camp1")

        args, kwargs = mock_send.call_args
        components = kwargs.get("components")

        url_btn = components[1]
        assert url_btn["type"] == "button"
        assert url_btn["sub_type"] == "url"
        assert url_btn["parameters"][0]["text"] == "dynamic1"

        qr_btn = components[2]
        assert qr_btn["sub_type"] == "quick_reply"
        assert qr_btn["parameters"][0]["payload"] == "ReplyMe"

@patch("src.services.whatsapp_service.time.sleep", return_value=None)
@patch("src.database.SessionLocal")
def test_template_payload_unsupported_button(mock_session_local, mock_sleep, mock_db_session, mock_env):
    mock_db, camp, rec = mock_db_session
    mock_db.query.return_value.filter.return_value.update.return_value = 1

    template = mock_db.query.side_effect(WhatsAppTemplate).filter().first()
    template.buttons = [{"type": "INVALID_TYPE"}]

    mock_session_local.return_value = mock_db
    service = WhatsAppCampaignService(mock_db)

    with patch.object(service.meta_service, 'send_template_message') as mock_send:
        service.execute_campaign("camp1")
        assert mock_send.call_count == 0
        assert camp.status == "FAILED"

@patch("src.services.whatsapp_service.time.sleep", return_value=None)
@patch("src.database.SessionLocal")
def test_campaign_concurrency_lock(mock_session_local, mock_sleep, mock_db_session, mock_env):
    mock_db, camp, rec = mock_db_session
    # First worker claims it
    mock_db.query.return_value.filter.return_value.update.return_value = 1

    mock_session_local.return_value = mock_db
    service = WhatsAppCampaignService(mock_db)
    with patch.object(service.meta_service, 'send_template_message', return_value=(True, "msg1", "200", None, None)) as mock_send:
        service.execute_campaign("camp1")
        assert mock_send.call_count == 1

    # Second worker tries to claim
    mock_db.query.return_value.filter.return_value.update.return_value = 0
    with patch.object(service.meta_service, 'send_template_message', return_value=(True, "msg2", "200", None, None)) as mock_send2:
        service.execute_campaign("camp1")
        assert mock_send2.call_count == 0 # Exits early


# --- Meta template pre-flight -------------------------------------------------
# A local template that was never approved in the Meta WABA used to be
# discovered one rejected send at a time (Meta error #132001). The campaign now
# validates once up front and sends nothing.

@patch("src.services.whatsapp_service.time.sleep", return_value=None)
@patch("src.database.SessionLocal")
def test_unapproved_template_sends_nothing(mock_session_local, mock_sleep, mock_db_session, mock_env, mock_preflight):
    mock_db, camp, rec = mock_db_session
    mock_session_local.return_value = mock_db
    mock_preflight.return_value = {
        "ok": False,
        "error": "Template 'TestRun' with language 'en_US' is not an approved template in this WhatsApp Business Account.",
        "available": ["hello_world (en_US)"],
    }

    service = WhatsAppCampaignService(mock_db)
    with patch.object(service.meta_service, 'send_template_message') as mock_send:
        service.execute_campaign("camp1")

    assert mock_send.call_count == 0, "no message may be sent when the template is not approved"
    assert camp.status == "FAILED"


@patch("src.services.whatsapp_service.time.sleep", return_value=None)
@patch("src.database.SessionLocal")
def test_unapproved_template_persists_reason(mock_session_local, mock_sleep, mock_db_session, mock_env, mock_preflight):
    mock_db, camp, rec = mock_db_session
    mock_session_local.return_value = mock_db
    mock_preflight.return_value = {
        "ok": False,
        "error": "Template 'TestRun' with language 'en_US' is not an approved template in this WhatsApp Business Account.",
        "available": ["hello_world (en_US)"],
    }

    service = WhatsAppCampaignService(mock_db)
    with patch.object(service.meta_service, 'send_template_message'):
        service.execute_campaign("camp1")

    logged = [c.args[0] for c in mock_db.add.call_args_list if c.args]
    failures = [o for o in logged if getattr(o, "status", None) == "ERROR"]
    assert failures, "the campaign-level failure must be persisted as a log row"
    assert "not an approved template" in failures[0].error_reason
    assert failures[0].provider_code == "132001"
    assert failures[0].recipient_id is None


@patch("src.services.whatsapp_service.time.sleep", return_value=None)
@patch("src.database.SessionLocal")
def test_send_uses_meta_template_name_and_language(mock_session_local, mock_sleep, mock_db_session, mock_env):
    """The name registered with Meta wins over the local display name."""
    mock_db, camp, rec = mock_db_session
    mock_session_local.return_value = mock_db
    mock_db.query(WhatsAppTemplate).filter().first().meta_template_name = "hello_world"
    mock_db.query(WhatsAppTemplate).filter().first().language_code = "en_GB"

    service = WhatsAppCampaignService(mock_db)
    with patch.object(service.meta_service, 'send_template_message',
                      return_value=(True, "msg1", "200", None, None)) as mock_send:
        service.execute_campaign("camp1")

    kwargs = mock_send.call_args.kwargs
    assert kwargs["template_name"] == "hello_world"
    assert kwargs["language_code"] == "en_GB"


def test_meta_credentials_are_never_logged(caplog, mock_env):
    """A Meta rejection echoing the token back must be redacted before logging."""
    import logging
    from src.services.meta_whatsapp_service import MetaWhatsAppService

    with patch.dict(os.environ, {"META_ACCESS_TOKEN": "SECRET_TOKEN_VALUE",
                                 "META_PHONE_NUMBER_ID": "123",
                                 "MOCK_WHATSAPP_API": "false"}):
        service = MetaWhatsAppService()
        fake = MagicMock()
        fake.status_code = 401
        fake.json.return_value = {"error": {"message": "Bad token SECRET_TOKEN_VALUE", "code": 190}}

        with caplog.at_level(logging.ERROR):
            with patch("src.services.meta_whatsapp_service.requests.post", return_value=fake):
                ok, msg_id, status, reason, code = service.send_template_message(
                    to_phone="+919999999999", template_name="hello_world")

    assert ok is False
    assert code == "190"
    assert "SECRET_TOKEN_VALUE" not in reason
    assert "SECRET_TOKEN_VALUE" not in caplog.text


# --- Link click attribution -------------------------------------------------
# WhatsApp never reports clicks on a link inside a message body, and a URL that
# is identical for everyone cannot say who opened it. Each recipient therefore
# gets their own token, and only real requests to the redirect are counted.

def test_unique_and_repeated_visits_are_counted_per_recipient():
    from src.routers.whatsapp import _visit_counts

    class Row(tuple):
        pass

    # (campaign_id, recipient_id, clicks) -- r1 opened 3x, r2 once, r3 twice
    rows = [("c1", "r1", 3), ("c1", "r2", 1), ("c1", "r3", 2)]

    db = MagicMock()
    db.query.return_value.filter.return_value.group_by.return_value.all.return_value = rows

    counts = _visit_counts(db, ["c1"])
    assert counts["c1"]["unique"] == 3, "three distinct recipients opened the link"
    assert counts["c1"]["repeated"] == 3, "3x + 1x + 2x leaves 2 + 0 + 1 repeats"
    assert counts["c1"]["total"] == 6


def test_campaign_with_no_clicks_reports_zero():
    from src.routers.whatsapp import _visit_counts

    db = MagicMock()
    db.query.return_value.filter.return_value.group_by.return_value.all.return_value = []

    counts = _visit_counts(db, ["c1"])
    assert counts["c1"] == {"unique": 0, "repeated": 0, "total": 0}


def test_unknown_token_redirects_without_recording():
    """A stale or forged token must still land somewhere, and record nothing."""
    from src.routers.tracking import follow_campaign_link

    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None
    request = MagicMock()
    request.headers = {}
    request.client = None

    response = follow_campaign_link("deadbeef", request, db)
    assert response.status_code == 302
    db.add.assert_not_called()


def test_click_is_recorded_for_a_known_token():
    from src.routers.tracking import follow_campaign_link

    recipient = MagicMock()
    recipient.campaign_id = "c1"
    recipient.recipient_id = "r1"

    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = recipient
    request = MagicMock()
    request.headers = {"user-agent": "Mozilla/5.0", "x-forwarded-for": "203.0.113.9"}
    request.client = None

    with patch.dict(os.environ, {"CAMPAIGN_LINK_TARGET_URL": "https://kiosk.eko.in/?utm_source=WhatsApp+Campaign"}):
        response = follow_campaign_link("goodtoken", request, db)

    assert response.status_code == 302
    db.add.assert_called_once()
    recorded = db.add.call_args.args[0]
    assert recorded.campaign_id == "c1"
    assert recorded.recipient_id == "r1"
    # The raw address is never stored.
    assert recorded.ip_hash and "203.0.113.9" not in recorded.ip_hash


# --- Per-recipient tracking link in the body --------------------------------

def test_placeholders_are_ordered_by_appearance():
    """Meta matches parameters positionally, so order must follow the text."""
    from src.services.whatsapp_service import ordered_placeholders

    assert ordered_placeholders("Hi {{name}}, open {{link}}") == ["{{name}}", "{{link}}"]
    assert ordered_placeholders("Open {{link}} — {{name}}") == ["{{link}}", "{{name}}"]
    assert ordered_placeholders("no placeholders here") == []


def test_tracking_link_uses_the_public_base_url():
    from src.services.whatsapp_service import tracking_link_for

    with patch.dict(os.environ, {"PUBLIC_BASE_URL": "https://link.eko.in/"}):
        assert tracking_link_for("abc123") == "https://link.eko.in/r/abc123"


def test_tracking_link_falls_back_to_the_plain_destination():
    """
    Until the redirect is reachable from the internet, messages must still
    carry a link that works -- an unreachable tracking URL would be worse
    than no tracking at all.
    """
    from src.services.whatsapp_service import tracking_link_for

    with patch.dict(os.environ, {
        "PUBLIC_BASE_URL": "",
        "CAMPAIGN_LINK_TARGET_URL": "https://kiosk.eko.in/?utm_source=WhatsApp+Campaign",
    }):
        assert tracking_link_for("abc123") == "https://kiosk.eko.in/?utm_source=WhatsApp+Campaign"


def test_submission_numbers_every_placeholder():
    from src.services.whatsapp_service import build_meta_components

    template = MagicMock()
    template.header_type = None
    template.header_content = None
    template.body = "Namaste {{name}}, apply here: {{link}}"
    template.footer = None
    template.buttons = []

    body = [c for c in build_meta_components(template) if c["type"] == "BODY"][0]
    assert body["text"] == "Namaste {{1}}, apply here: {{2}}"
    assert len(body["example"]["body_text"][0]) == 2


# --- Template deletion ------------------------------------------------------
# Deleting a template that any campaign had used failed with a bare 500:
# campaigns referenced it with a plain foreign key. Campaign history has to
# outlive the template, so the reference is cleared instead of blocking.

def test_campaign_template_link_clears_on_delete():
    from src.models.whatsapp import WhatsAppCampaign

    fk = list(WhatsAppCampaign.__table__.c.template_id.foreign_keys)[0]
    assert fk.ondelete == "SET NULL", (
        "deleting a template must clear the campaign's link, not block the delete "
        "or remove the campaign"
    )


def test_delete_reports_a_reason_instead_of_a_bare_500():
    import inspect
    from src.routers import whatsapp as wa_router

    source = inspect.getsource(wa_router.delete_template)
    assert "rollback" in source, "a failed delete must not leave the session dirty"
    assert "409" in source, "a blocked delete should be a conflict with an explanation"
    assert "campaigns_unlinked" in source, "the caller should learn what the delete affected"


# --- Campaign audience selection --------------------------------------------

def test_audience_geo_filters_combine():
    """State, district and tehsil narrow the pool together, and All is a no-op."""
    from src.routers.audience import _geo_filtered, AudienceFilters
    from src.models import Business

    q = MagicMock()
    q.filter.return_value = q

    _geo_filtered(q, AudienceFilters(state="All", district="All", tehsil="All"))
    assert q.filter.call_count == 0, "'All' must not restrict anything"

    q.reset_mock()
    _geo_filtered(q, AudienceFilters(state="Haryana", district="SIRSA", tehsil="Ellenabad"))
    assert q.filter.call_count == 3, "each chosen level adds a condition"


def test_only_sent_recipients_count_as_contacted():
    """
    A recipient that was skipped or failed never received anything. Counting
    them as contacted would quietly shrink every later audience.
    """
    import inspect
    from src.routers import audience

    source = inspect.getsource(audience._contacted_phones)
    assert '"SENT"' in source
    assert "FAILED" not in source and "SKIPPED" not in source
