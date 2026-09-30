from sqlalchemy import Column, String, Integer, DateTime, JSON, Text, func

from src.database import Base


class DiscoveryRound(Base):
    """
    One autopilot round: a single state, several batches run back to back.

    Each batch in the plan is one tehsil and its own set of categories, so a
    round spreads across the state instead of draining one town. The plan is
    saved before anything runs, which is what lets a restart — a deploy, a
    crash — pick the round up where it stopped rather than start another.
    """
    __tablename__ = "discovery_rounds"

    round_id = Column(String(32), primary_key=True)
    state = Column(String(100), nullable=False, index=True)
    # ACTIVE while batches remain, COMPLETED when all have run, ABANDONED if
    # nothing was left to run in it.
    status = Column(String(20), nullable=False, default="ACTIVE", index=True)
    # [{batch, location_id, anchor, district, tehsil, categories, job_ids,
    #   status, run_id, started_at, completed_at, jobs_completed,
    #   businesses_saved}]
    plan = Column(JSON, nullable=False)
    batches_done = Column(Integer, nullable=False, default=0)
    note = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
