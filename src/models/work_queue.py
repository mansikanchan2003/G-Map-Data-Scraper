from sqlalchemy import JSON, Column, DateTime, String, Text, func

from src.database import Base


class QueuedTask(Base):
    """
    Work the API hands to another container (Phase 1, 22 Nov 2026): a scraping batch
    or a single job, for the scraper. The database is the queue, so nothing new has
    to run on the server: the scraper claims the oldest QUEUED task, runs it, and
    writes back what came of it, which the API reads to answer a caller who waits.
    """
    __tablename__ = "queued_tasks"

    task_id = Column(String(32), primary_key=True)
    # "discovery_batch" or "run_job".
    kind = Column(String(40), nullable=False, index=True)
    payload = Column(JSON, nullable=False)
    # QUEUED, RUNNING, DONE or FAILED.
    status = Column(String(20), nullable=False, default="QUEUED", index=True)
    result = Column(JSON, nullable=True)
    error = Column(Text, nullable=True)
    # The container that claimed it (its hostname).
    claimed_by = Column(String(100), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
    started_at = Column(DateTime(timezone=True), nullable=True)
    finished_at = Column(DateTime(timezone=True), nullable=True)
