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
        session.rollback()
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
