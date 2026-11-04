"""When to call each lead after the bot's last message, and what to talk about (4 Nov 2026)."""
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.database import Base
from src.models import (  # noqa: F401  (registers the tables on Base)
    Business, WhatsAppCampaign, WhatsAppCampaignRecipient, WhatsAppTemplate,
)
from src.models.app_setting import AppSetting
from src.models.inbox import (ChatActivity, FollowUp, OnboardingDocument, WhatsAppConversation, WhatsAppMessage)
from src.services import call_plan, onboarding_bot as bot

engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base.metadata.create_all(bind=engine)

IST = timezone(timedelta(hours=5, minutes=30))
NOW = datetime(2026, 11, 4, 10, 0, tzinfo=IST)        # Wednesday, 10 AM
PHONE = "+919800000001"


@pytest.fixture
def db():
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        for model in (OnboardingDocument, ChatActivity, FollowUp, WhatsAppMessage, WhatsAppConversation,
                      WhatsAppCampaignRecipient, WhatsAppCampaign, WhatsAppTemplate, AppSetting):
            session.query(model).delete()
        session.commit()
        session.close()


def lead(db, step=bot.AWAIT_EDUCATION, **data):
    c = WhatsAppConversation(phone=PHONE, profile_name="Asha", bot_step=step,
                             bot_data={"lang": "gu", **data}, last_inbound_at=NOW - timedelta(days=1))
    db.add(c)
    db.commit()
    return c


def msg(db, direction, at, status=None, body="ok", kind="text"):
    db.add(WhatsAppMessage(message_id=uuid.uuid4().hex, phone=PHONE, direction=direction, kind=kind, body=body,
                           status=status, sent_by="bot" if direction == "OUT" else None,
                           created_at=at.astimezone(timezone.utc)))   # SQLite keeps no zone: store UTC
    db.commit()


def plan(db, conv, window=11):
    return call_plan.for_lead(db, conv, NOW, fallback_window=window)


def at_ist(p):
    return datetime.fromisoformat(p["call_at"]).astimezone(IST)


def test_read_and_not_answered_is_called_two_hours_later_in_the_hours_people_answer(db):
    c = lead(db)
    msg(db, "IN", NOW - timedelta(days=1), body="Interested")
    msg(db, "OUT", NOW - timedelta(minutes=30), status="READ")     # 9:30, read
    p = plan(db, c)
    assert p["call"] and at_ist(p) == datetime(2026, 11, 4, 11, 30, tzinfo=IST)
    assert p["after_message"] == "2 ghante" and "padh liya" in p["why"][0]


def test_unread_waits_longer_and_moves_to_the_next_good_hours(db):
    c = lead(db)
    msg(db, "OUT", NOW + timedelta(hours=5), status="DELIVERED")    # 3 PM, not read
    p = plan(db, c)
    # 3 PM + 4 hours is 7 PM, past 11 AM–1 PM: tomorrow at 11.
    assert at_ist(p) == datetime(2026, 11, 5, 11, 0, tzinfo=IST)
    assert "padha nahi" in p["why"][0]


def test_a_message_whatsapp_could_not_deliver_is_followed_by_a_call_soon(db):
    c = lead(db)
    msg(db, "OUT", NOW + timedelta(hours=1), status="FAILED")       # 11 AM
    p = plan(db, c)
    assert at_ist(p) == datetime(2026, 11, 4, 12, 0, tzinfo=IST) and "sirf call" in p["why"][0]


def test_their_own_reply_hours_set_the_time(db):
    c = lead(db)
    for d in (3, 2, 1):
        msg(db, "IN", datetime(2026, 11, 4 - d, 18, 15, tzinfo=IST))
    msg(db, "OUT", NOW - timedelta(minutes=30), status="READ")
    p = plan(db, c)
    assert at_ist(p).hour in (17, 18) and "aksar" in p["why"][1]


def test_no_call_once_they_answer_or_hand_over(db):
    c = lead(db)
    msg(db, "OUT", NOW - timedelta(hours=3), status="READ")
    msg(db, "IN", NOW - timedelta(hours=1), body="haan")
    assert plan(db, c)["call"] is False
    c.documents_submitted_at = NOW
    db.commit()
    assert "Eko Acquisition" in plan(db, c)["why"]


def test_no_call_after_the_team_recorded_one(db):
    c = lead(db)
    msg(db, "OUT", NOW - timedelta(hours=3), status="READ")
    c.disposition, c.disposition_by = "busy_later", "kavya@eko.co.in"
    c.disposition_at = (NOW - timedelta(hours=1)).astimezone(timezone.utc)
    db.commit()
    p = plan(db, c)
    assert p["call"] is False and "kavya" in p["why"]


def test_a_callback_time_they_asked_for_is_kept(db):
    c = lead(db)
    c.disposition = "busy_at_time"
    msg(db, "OUT", NOW - timedelta(hours=1), status="READ")
    asked = datetime(2026, 11, 4, 16, 45, tzinfo=IST)
    db.add(FollowUp(followup_id=uuid.uuid4().hex, phone=PHONE, disposition="busy_at_time", purpose="callback_due",
                    owner="bot", wants="whatsapp_call", due_at=asked.astimezone(timezone.utc), status="scheduled",
                    created_by="t"))
    db.commit()
    p = plan(db, c)
    assert at_ist(p) == asked and p["goal"] == "Unke bataye time par call back karein"


def test_what_to_talk_about_follows_where_they_stopped(db):
    c = lead(db, step=bot.AWAIT_UPLOAD, education="grad", can_invest=True,
             coverage={"pincode": "360001", "district": "Rajkot", "state": "Gujarat", "served": True})
    db.add(OnboardingDocument(document_id=uuid.uuid4().hex, phone=PHONE, doc_type="pan", original_name="pan.pdf",
                              stored_path="x", content_type="application/pdf", size_bytes=1))
    msg(db, "IN", NOW - timedelta(days=1), body="Documents kaise upload karne hai?")
    msg(db, "OUT", NOW - timedelta(hours=3), status="READ")
    p = plan(db, c)
    assert p["goal"] == "Documents upload karne mein madad karein" and p["language"] == "Gujarati"
    assert "PAN" not in p["points"][0] and "Aadhaar" in p["points"][0] and "Photo" in p["points"][0]
    assert p["known"] == ["PIN 360001 (Rajkot, Gujarat)", "Padhai: Graduate", "₹3–5 lakh invest kar sakte hain"]
    assert p["their_questions"] == ["Documents kaise upload karne hai?"]
    assert any("Fixed income" in a for a in p["avoid"])
    assert "No answer" in p["record"]["no_answer"]


def test_a_trust_concern_comes_before_the_step(db):
    c = lead(db, step=bot.AWAIT_INVEST)
    c.disposition = "int_trust"
    msg(db, "OUT", NOW - timedelta(hours=3), status="READ")
    p = plan(db, c)
    assert p["goal"].startswith("Unka shak door") and any("kiosk.eko.in" in x for x in p["points"])
    assert any("₹3–5 lakh" in x for x in p["points"])        # the step's points follow
