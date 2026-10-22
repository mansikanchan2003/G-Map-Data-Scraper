"""AutoGMap's calculated views kept in tables (report_store.py)."""
import uuid
from datetime import timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.database import Base
from src.models import (  # noqa: F401  (registers the tables on Base)
    ActionItem, AttentionTicket, DispositionDaily, DispositionMix, FollowUp, GoalDaily, LeadAlert, NumberUsageDaily,
    WhatsAppConversation,
)
from src.models.whatsapp import WhatsAppCampaign, WhatsAppCampaignRecipient
from src.services import business_context, inbox, report_store

engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base.metadata.create_all(bind=engine)

PHONE = "+919000000077"


@pytest.fixture
def db(monkeypatch, tmp_path):
    monkeypatch.setattr(business_context, "CONTEXT_FILE", str(tmp_path / "none.json"))
    s = Session()
    now = inbox.now()
    s.add(WhatsAppCampaign(campaign_id="c1", name="Gujarat October", data_source_type="upload",
                           status="COMPLETED", total_contacts=50))
    s.add(WhatsAppCampaignRecipient(recipient_id=uuid.uuid4().hex, campaign_id="c1", phone=PHONE, name="Arshad",
                                    status="READ", sent_at=now - timedelta(days=2), delivered_at=now - timedelta(days=2)))
    s.add(WhatsAppConversation(phone=PHONE, profile_name="Arshad", last_message_at=now, last_inbound_at=now,
                               disposition="ni_investment", disposition_at=now, disposition_by="mansi@eko.co.in"))
    s.add(FollowUp(followup_id=uuid.uuid4().hex, phone=PHONE, disposition="lang_barrier", purpose="choose_language",
                   owner="human", wants="task", due_at=now - timedelta(days=3), status="scheduled",
                   task="Reassign the lead to someone who speaks their language", created_by="mansi@eko.co.in",
                   created_at=now - timedelta(days=3)))
    s.add(AttentionTicket(phone=PHONE, question="Is this real?", raised_at=now - timedelta(hours=2)))
    s.commit()
    yield s
    s.rollback()
    for model in (ActionItem, DispositionMix, DispositionDaily, NumberUsageDaily, GoalDaily, LeadAlert,
                  FollowUp, AttentionTicket, WhatsAppConversation, WhatsAppCampaignRecipient, WhatsAppCampaign):
        s.query(model).delete()
    s.commit()
    s.close()


def test_every_calculated_view_is_written_to_its_table(db):
    out = report_store.refresh(db)
    assert None not in out.values(), out

    items = {i.source: i for i in db.query(ActionItem).all()}
    assert items["followup"].bucket == "overdue" and items["followup"].owner == "human"
    assert items["ticket"].bucket == "today" and items["ticket"].text.startswith("Answer their question")

    mix = db.query(DispositionMix).filter(DispositionMix.dimension == "campaign").one()
    assert (mix.value, mix.leads, mix.sent, mix.replied) == ("Gujarat October", 1, 1, 1)

    day = db.query(DispositionDaily).filter(DispositionDaily.disposition == "ni_investment").one()
    assert day.chats == 1 and day.group == "negative"

    assert db.query(NumberUsageDaily).count() >= 1
    goal = db.query(GoalDaily).one()
    assert "lead_list" not in goal.details
    assert {a.check for a in db.query(LeadAlert).all()} >= {"task_overdue"}


def test_a_refresh_replaces_the_copies_and_keeps_one_row_per_day(db):
    report_store.refresh(db)
    db.query(FollowUp).update({"status": "done"})
    db.commit()
    report_store.refresh(db)
    assert db.query(ActionItem).filter(ActionItem.source == "followup").count() == 0
    assert db.query(GoalDaily).count() == 1


def test_one_table_failing_leaves_the_others(db, monkeypatch):
    def broken(db, now):
        raise RuntimeError("boom")
    monkeypatch.setitem(report_store.STORES, "goal_daily", broken)
    out = report_store.refresh(db)
    assert out["goal_daily"] is None
    assert out["action_items"] == 2
