from sqlalchemy import Column, String, Integer, Float, DateTime, Text, func
from src.database import Base

class RunLog(Base):
    __tablename__ = "run_log"

    run_id = Column(String(36), primary_key=True, index=True)
    trigger_source = Column(String(20), nullable=False)
    status = Column(String(20), nullable=False, index=True)
    jobs_attempted = Column(Integer, nullable=False, default=0)
    jobs_completed = Column(Integer, nullable=False, default=0)
    jobs_failed = Column(Integer, nullable=False, default=0)
    businesses_discovered = Column(Integer, nullable=False, default=0)
    businesses_new = Column(Integer, nullable=False, default=0)
    businesses_updated = Column(Integer, nullable=False, default=0)
    businesses_duplicate = Column(Integer, nullable=False, default=0)
    duration_seconds = Column(Float, nullable=True)
    error_summary = Column(Text, nullable=True)
    started_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
