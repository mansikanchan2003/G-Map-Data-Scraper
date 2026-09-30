from sqlalchemy import Column, String, Integer, Float, DateTime, ForeignKey, JSON, func

from src.database import Base


class CampaignInsight(Base):
    """
    The saved report for one campaign: how it did and what might have worked.

    Recomputed when the campaign finishes and whenever it is refreshed, since
    delivery and read reports keep arriving from Meta for days afterwards.
    """
    __tablename__ = "campaign_insights"

    campaign_id = Column(String(32), ForeignKey("whatsapp_campaigns.campaign_id", ondelete="CASCADE"),
                         primary_key=True)
    metrics = Column(JSON, nullable=True)
    breakdowns = Column(JSON, nullable=True)
    suggestions = Column(JSON, nullable=True)
    # Response rate relative to all campaigns at the time: +0.5 is 50% better.
    vs_all_campaigns = Column(Float, nullable=True)
    computed_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class InsightSnapshot(Base):
    """
    What the playbook concluded at one moment.

    One is written after every campaign, so the record of what has been
    learned — and how firmly — builds up over time rather than being
    overwritten each time it is recomputed.
    """
    __tablename__ = "insight_snapshots"

    snapshot_id = Column(String(32), primary_key=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
    trigger = Column(String(40), nullable=False)  # campaign_finished | manual
    campaign_id = Column(String(32), ForeignKey("whatsapp_campaigns.campaign_id", ondelete="SET NULL"),
                         nullable=True)
    campaigns = Column(Integer, nullable=False, default=0)
    recipients = Column(Integer, nullable=False, default=0)
    responses = Column(Integer, nullable=False, default=0)
    playbook = Column(JSON, nullable=True)
