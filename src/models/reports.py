"""
AutoGMap's calculated views kept as tables, so the team can query them with
SQL (the user, 2026-10-22). The screens work these out from the records;
report_store.py writes the same results here every 15 minutes. The records
stay the source: these are copies, replaced on each refresh, except the
per-day tables, which keep every day's last figures.
"""
from sqlalchemy import Boolean, Column, Date, DateTime, Float, Integer, JSON, String

from src.database import Base


class ActionItem(Base):
    """The action items queue: every open item, overdue, due today or upcoming."""
    __tablename__ = "action_items"

    item_id = Column(String(64), primary_key=True)
    source = Column(String(20), nullable=False)  # followup | ticket
    phone = Column(String(20), nullable=False, index=True)
    name = Column(String(200), nullable=True)
    owner = Column(String(30), nullable=False, index=True)
    owner_label = Column(String(300), nullable=True)
    text = Column(String(500), nullable=True)
    result = Column(String(300), nullable=True)
    disposition_label = Column(String(120), nullable=True)
    due_at = Column(DateTime(timezone=True), nullable=True, index=True)
    bucket = Column(String(10), nullable=False, index=True)  # overdue | today | upcoming
    refreshed_at = Column(DateTime(timezone=True), nullable=False)


class DispositionMix(Base):
    """How many leads stand at each disposition, by campaign, template and state."""
    __tablename__ = "disposition_mix"

    row_id = Column(String(64), primary_key=True)
    dimension = Column(String(20), nullable=False, index=True)  # campaign | template | state
    value = Column(String(255), nullable=False)
    disposition_label = Column(String(120), nullable=False)
    group = Column(String(20), nullable=True)
    leads = Column(Integer, nullable=False, default=0)
    # Everyone this campaign, template or state reached, and how many wrote back.
    sent = Column(Integer, nullable=False, default=0)
    replied = Column(Integer, nullable=False, default=0)
    refreshed_at = Column(DateTime(timezone=True), nullable=False)


class DispositionDaily(Base):
    """Each day (IST), how many chats stood at each disposition at that day's last refresh."""
    __tablename__ = "disposition_daily"

    day = Column(Date, primary_key=True)
    disposition = Column(String(60), primary_key=True)
    disposition_label = Column(String(120), nullable=True)
    category = Column(String(40), nullable=True)
    group = Column(String(20), nullable=True)
    chats = Column(Integer, nullable=False, default=0)
    refreshed_at = Column(DateTime(timezone=True), nullable=False)


class NumberUsageDaily(Base):
    """Each day (IST), what AutoGMap and the other apps sent from the shared number."""
    __tablename__ = "number_usage_daily"

    day = Column(Date, primary_key=True)
    autogmap = Column(Integer, nullable=False, default=0)
    others = Column(Integer, nullable=False, default=0)
    others_by_category = Column(JSON, nullable=True)
    others_delivered = Column(Integer, nullable=False, default=0)
    others_read = Column(Integer, nullable=False, default=0)
    others_cost_inr = Column(Float, nullable=False, default=0.0)
    refreshed_at = Column(DateTime(timezone=True), nullable=False)


class GoalDaily(Base):
    """Each day (IST), the lead goal the agent set and how far AutoGMap had got."""
    __tablename__ = "goal_daily"

    day = Column(Date, primary_key=True)
    target = Column(Integer, nullable=True)
    leads = Column(Integer, nullable=True)
    still_needed = Column(Integer, nullable=True)
    days_left = Column(Integer, nullable=True)
    on_track = Column(Boolean, nullable=True)
    messages_sent = Column(Integer, nullable=True)
    leads_per_1000 = Column(Float, nullable=True)
    # Everything else the Goal section shows that day, without names or phones.
    details = Column(JSON, nullable=True)
    refreshed_at = Column(DateTime(timezone=True), nullable=False)


class LeadAlert(Base):
    """The Dashboard alerts: each lead with a missing step, disposition or action item."""
    __tablename__ = "lead_alerts"

    alert_id = Column(String(64), primary_key=True)
    check = Column(String(40), nullable=False, index=True)
    label = Column(String(200), nullable=True)
    severity = Column(String(20), nullable=True)
    group = Column(String(40), nullable=True, index=True)
    phone = Column(String(20), nullable=False, index=True)
    name = Column(String(200), nullable=True)
    at = Column(DateTime(timezone=True), nullable=True)
    detail = Column(String(500), nullable=True)
    refreshed_at = Column(DateTime(timezone=True), nullable=False)
