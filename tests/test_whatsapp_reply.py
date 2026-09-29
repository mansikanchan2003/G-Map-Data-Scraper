"""
Answering a callback request with a typed message.

Meta accepts a free-form message only within 24 hours of the recipient's last
message to us, and refuses it afterwards with code 131047. These tests hold
the line the user sees: the window is enforced here, before anything is sent,
and a refusal by Meta is recorded rather than swallowed.
"""
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.database import Base
from src.models import (  # noqa: F401  (registers the tables on Base)
    WhatsAppButtonClick, WhatsAppCampaign, WhatsAppCampaignRecipient,
    WhatsAppReply,
)
from src.routers import whatsapp as wa

engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base.metadata.create_all(bind=engine)

PHONE = "+919000000001"


class FakeUser:
    email = "admin@eko.co.in"


@pytest.fixture
def db():
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        for model in (WhatsAppReply, WhatsAppButtonClick,
                      WhatsAppCampaignRecipient, WhatsAppCampaign):
            session.query(model).delete()
        session.commit()
        session.close()


def make_click(session, *, age_hours: float) -> str:
    """A tap that happened `age_hours` ago, with its recipient and campaign."""
    campaign_id = uuid.uuid4().hex
    recipient_id = uuid.uuid4().hex
    click_id = uuid.uuid4().hex
    session.add(WhatsAppCampaign(
        campaign_id=campaign_id, name="Test", data_source_type="scraped",
        status="COMPLETED", total_contacts=1,
    ))
    session.add(WhatsAppCampaignRecipient(
        recipient_id=recipient_id, campaign_id=campaign_id,
        phone=PHONE, status="SENT",
    ))
    session.add(WhatsAppButtonClick(
        click_id=click_id, campaign_id=campaign_id, recipient_id=recipient_id,
        button_text="Call me back",
        clicked_at=datetime.now(timezone.utc) - timedelta(hours=age_hours),
    ))
    session.commit()
    return click_id


class StubMeta:
    """Stands in for the Cloud API. Records what it was asked to send."""
    sent = []
    result = (True, "wamid.SENT", "200", None, None)

    def send_text_message(self, to_phone, body):
        StubMeta.sent.append((to_phone, body))
        return StubMeta.result


@pytest.fixture(autouse=True)
def stub_meta(monkeypatch):
    StubMeta.sent = []
    StubMeta.result = (True, "wamid.SENT", "200", None, None)
    monkeypatch.setattr(wa, "MetaWhatsAppService", StubMeta)


def test_reply_sends_and_is_recorded(db):
    click_id = make_click(db, age_hours=1)

    out = wa.reply_to_lead(click_id, wa.ReplyRequest(message="  Calling you now  "),
                           db=db, user=FakeUser())

    assert out.status == "SENT"
    # Trimmed before sending: trailing whitespace is not part of the message.
    assert StubMeta.sent == [(PHONE, "Calling you now")]
    assert out.sent_by == "admin@eko.co.in"

    stored = db.query(WhatsAppReply).filter(WhatsAppReply.click_id == click_id).one()
    assert stored.body == "Calling you now"
    assert stored.provider_message_id == "wamid.SENT"


def test_reply_refused_once_the_window_has_closed(db):
    click_id = make_click(db, age_hours=25)

    with pytest.raises(wa.HTTPException) as exc:
        wa.reply_to_lead(click_id, wa.ReplyRequest(message="Hello"),
                         db=db, user=FakeUser())

    assert exc.value.status_code == 409
    # Nothing may reach Meta: the refusal is ours, made before the call.
    assert StubMeta.sent == []
    assert "template" in exc.value.detail.lower()
    assert db.query(WhatsAppReply).count() == 0


def test_window_is_open_right_up_to_24_hours(db):
    click_id = make_click(db, age_hours=23.9)

    out = wa.reply_to_lead(click_id, wa.ReplyRequest(message="Still in time"),
                           db=db, user=FakeUser())

    assert out.status == "SENT"


def test_a_refusal_by_meta_is_kept_with_its_reason(db):
    click_id = make_click(db, age_hours=1)
    StubMeta.result = (False, None, "400", "Meta API rejection: Re-engagement message", "131047")

    with pytest.raises(wa.HTTPException) as exc:
        wa.reply_to_lead(click_id, wa.ReplyRequest(message="Hello"),
                         db=db, user=FakeUser())

    assert exc.value.status_code == 502
    # Kept rather than discarded: a reply that failed silently is worse than
    # one visibly marked failed.
    stored = db.query(WhatsAppReply).filter(WhatsAppReply.click_id == click_id).one()
    assert stored.status == "FAILED"
    assert "Re-engagement" in stored.error_reason


def test_an_empty_message_is_rejected(db):
    click_id = make_click(db, age_hours=1)

    with pytest.raises(wa.HTTPException) as exc:
        wa.reply_to_lead(click_id, wa.ReplyRequest(message="   "),
                         db=db, user=FakeUser())

    assert exc.value.status_code == 400
    assert StubMeta.sent == []


def test_unknown_click_is_a_404(db):
    with pytest.raises(wa.HTTPException) as exc:
        wa.reply_to_lead("nosuchclick", wa.ReplyRequest(message="Hello"),
                         db=db, user=FakeUser())

    assert exc.value.status_code == 404
