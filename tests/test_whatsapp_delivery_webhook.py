"""
Delivery events and quick-reply taps arriving from Meta.

Meta delivers these out of order and repeats them until acknowledged, so the
handlers have to be idempotent and monotonic. These tests hold that line: a
redelivered earlier event must never undo a later one, and a tap must never be
counted twice.
"""
import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.database import Base
from src.models import (  # noqa: F401  (registers the tables on Base)
    WhatsAppButtonClick, WhatsAppCampaign, WhatsAppCampaignRecipient,
)
from src.routers.whatsapp import _apply_inbound_message, _apply_status_event

engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base.metadata.create_all(bind=engine)

MSG_ID = "wamid.TEST"


@pytest.fixture
def db():
    session = TestingSessionLocal()
    campaign_id = uuid.uuid4().hex
    session.add(WhatsAppCampaign(
        campaign_id=campaign_id, name="Test", data_source_type="scraped",
        status="COMPLETED", total_contacts=1,
    ))
    session.add(WhatsAppCampaignRecipient(
        recipient_id=uuid.uuid4().hex, campaign_id=campaign_id,
        phone="+919000000000", status="SENT", provider_message_id=MSG_ID,
        sent_at=datetime.now(timezone.utc),
    ))
    session.commit()
    try:
        yield session
    finally:
        # These rows are committed, so a rollback will not remove them. Left
        # behind, the next test's lookup by MSG_ID finds this test's recipient.
        session.rollback()
        session.query(WhatsAppButtonClick).filter(
            WhatsAppButtonClick.campaign_id == campaign_id
        ).delete(synchronize_session=False)
        session.query(WhatsAppCampaignRecipient).filter(
            WhatsAppCampaignRecipient.campaign_id == campaign_id
        ).delete(synchronize_session=False)
        session.query(WhatsAppCampaign).filter(
            WhatsAppCampaign.campaign_id == campaign_id
        ).delete(synchronize_session=False)
        session.commit()
        session.close()


def recipient(db):
    return db.query(WhatsAppCampaignRecipient).filter(
        WhatsAppCampaignRecipient.provider_message_id == MSG_ID
    ).first()


def status_event(stage, ts="1700000000", **extra):
    return {"id": MSG_ID, "status": stage, "timestamp": ts, **extra}


class TestStatusEvents:
    def test_delivered_then_read_keeps_both_stamps(self, db):
        _apply_status_event(db, status_event("delivered", "1700000000"))
        _apply_status_event(db, status_event("read", "1700000060"))
        db.flush()

        r = recipient(db)
        # The whole point: a read message must still count as delivered.
        assert r.delivered_at is not None
        assert r.read_at is not None
        assert r.read_at > r.delivered_at
        assert r.status == "READ"

    def test_read_without_a_delivered_event_still_counts_as_delivered(self, db):
        # Meta sometimes skips the delivered event; leaving it blank would
        # undercount deliveries against a message that demonstrably arrived.
        _apply_status_event(db, status_event("read", "1700000060"))
        db.flush()

        r = recipient(db)
        assert r.read_at is not None
        assert r.delivered_at == r.read_at

    def test_late_delivered_does_not_drag_status_back_from_read(self, db):
        _apply_status_event(db, status_event("read", "1700000060"))
        _apply_status_event(db, status_event("delivered", "1700000000"))
        db.flush()

        assert recipient(db).status == "READ"

    def test_repeated_delivered_does_not_move_the_stamp(self, db):
        _apply_status_event(db, status_event("delivered", "1700000000"))
        db.flush()
        first = recipient(db).delivered_at

        _apply_status_event(db, status_event("delivered", "1700009999"))
        db.flush()

        assert recipient(db).delivered_at == first

    def test_failure_records_code_and_is_terminal(self, db):
        _apply_status_event(db, status_event(
            "failed",
            errors=[{"code": 131049, "title": "Per-user marketing limit",
                     "error_data": {"details": "not delivered"}}],
        ))
        db.flush()

        r = recipient(db)
        assert r.status == "FAILED"
        assert r.failure_code == "131049"
        assert "131049" in r.reason
        assert r.failed_at is not None

    def test_a_later_delivered_cannot_revive_a_failed_send(self, db):
        _apply_status_event(db, status_event("failed", errors=[]))
        _apply_status_event(db, status_event("delivered", "1700009999"))
        db.flush()

        assert recipient(db).status == "FAILED"

    def test_event_for_an_unknown_message_is_ignored(self, db):
        _apply_status_event(db, {"id": "wamid.SOMEONE_ELSE", "status": "read"})
        db.flush()
        assert db.query(WhatsAppButtonClick).count() == 0
        assert recipient(db).read_at is None


class TestButtonClicks:
    def tap(self, inbound_id="wamid.IN1", text="Apply now"):
        return {
            "id": inbound_id,
            "type": "button",
            "timestamp": "1700000120",
            "context": {"id": MSG_ID},
            "button": {"text": text, "payload": "APPLY"},
        }

    def test_quick_reply_tap_is_recorded_against_the_recipient(self, db):
        _apply_inbound_message(db, self.tap())
        db.flush()

        click = db.query(WhatsAppButtonClick).one()
        assert click.button_text == "Apply now"
        assert click.button_payload == "APPLY"
        assert click.recipient_id == recipient(db).recipient_id

    def test_a_redelivered_tap_is_not_counted_twice(self, db):
        _apply_inbound_message(db, self.tap())
        db.flush()
        _apply_inbound_message(db, self.tap())
        db.flush()

        assert db.query(WhatsAppButtonClick).count() == 1

    def test_two_distinct_taps_both_count(self, db):
        _apply_inbound_message(db, self.tap("wamid.IN1", "Yes"))
        _apply_inbound_message(db, self.tap("wamid.IN2", "Call me"))
        db.flush()

        assert db.query(WhatsAppButtonClick).count() == 2

    def test_a_plain_text_reply_is_not_a_button_click(self, db):
        _apply_inbound_message(db, {
            "id": "wamid.IN9", "type": "text", "timestamp": "1700000120",
            "context": {"id": MSG_ID}, "text": {"body": "hello"},
        })
        db.flush()

        assert db.query(WhatsAppButtonClick).count() == 0

    def test_a_tap_with_no_context_cannot_be_attributed(self, db):
        # Without context.id there is nothing tying the tap to a campaign
        # message, and guessing by phone number would attribute it to whichever
        # campaign happened to be last.
        _apply_inbound_message(db, {
            "id": "wamid.IN8", "type": "button", "timestamp": "1700000120",
            "button": {"text": "Yes", "payload": "Y"},
        })
        db.flush()

        assert db.query(WhatsAppButtonClick).count() == 0


class TestWebhookEndpoint:
    """
    The HTTP surface Meta will actually call.

    These run the real endpoint, so they prove the handshake and the signature
    check work before the webhook is ever pointed at a public URL.
    """

    @pytest.fixture
    def client(self, monkeypatch):
        from fastapi.testclient import TestClient

        from src.database import get_db
        from src.main import app

        monkeypatch.setenv("META_APP_SECRET", "test_app_secret")
        monkeypatch.setenv("META_WEBHOOK_VERIFY_TOKEN", "test_verify_token")

        def override_db():
            session = TestingSessionLocal()
            try:
                yield session
            finally:
                session.close()

        app.dependency_overrides[get_db] = override_db
        yield TestClient(app)
        app.dependency_overrides.pop(get_db, None)

    def signed(self, client, payload):
        import hashlib
        import hmac
        import json as jsonlib

        body = jsonlib.dumps(payload).encode()
        digest = hmac.new(b"test_app_secret", body, hashlib.sha256).hexdigest()
        return client.post(
            "/api/v1/whatsapp/webhook",
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-Hub-Signature-256": f"sha256={digest}",
            },
        )

    def test_verification_handshake_echoes_the_challenge(self, client):
        res = client.get(
            "/api/v1/whatsapp/webhook",
            params={
                "hub.mode": "subscribe",
                "hub.challenge": "31415",
                "hub.verify_token": "test_verify_token",
            },
        )
        assert res.status_code == 200
        assert res.json() == 31415

    def test_verification_rejects_a_wrong_token(self, client):
        res = client.get(
            "/api/v1/whatsapp/webhook",
            params={
                "hub.mode": "subscribe",
                "hub.challenge": "31415",
                "hub.verify_token": "not_the_token",
            },
        )
        assert res.status_code == 403

    def test_a_correctly_signed_event_is_applied(self, client, db):
        res = self.signed(client, {
            "entry": [{"changes": [{"value": {"statuses": [
                {"id": MSG_ID, "status": "read", "timestamp": "1700000600"}
            ]}}]}]
        })
        assert res.status_code == 200

        db.expire_all()
        r = recipient(db)
        assert r.read_at is not None
        assert r.delivered_at is not None

    def test_an_unsigned_request_is_rejected(self, client):
        res = client.post("/api/v1/whatsapp/webhook", json={"entry": []})
        assert res.status_code == 403

    def test_a_forged_signature_is_rejected(self, client, db):
        import json as jsonlib

        body = jsonlib.dumps({"entry": [{"changes": [{"value": {"statuses": [
            {"id": MSG_ID, "status": "read", "timestamp": "1700000600"}
        ]}}]}]}).encode()
        res = client.post(
            "/api/v1/whatsapp/webhook",
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-Hub-Signature-256": "sha256=" + "0" * 64,
            },
        )
        assert res.status_code == 403

        db.expire_all()
        assert recipient(db).read_at is None

    def test_a_payload_that_cannot_be_applied_is_still_acknowledged(self, client):
        # Meta redelivers anything it does not get a 200 for, so an unusable
        # payload must not turn into a retry loop.
        res = self.signed(client, {"entry": [{"changes": [{"value": {}}]}]})
        assert res.status_code == 200
