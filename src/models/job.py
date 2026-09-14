from sqlalchemy import Column, String, Integer, DateTime, ForeignKey, Text, func
from sqlalchemy.orm import relationship
from src.database import Base

class Job(Base):
    __tablename__ = "jobs"

    job_id = Column(String(16), primary_key=True, index=True)
    location_id = Column(String(12), ForeignKey("locations.location_id"), nullable=False)
    category_id = Column(String(12), ForeignKey("categories.category_id"), nullable=False)
    status = Column(String(20), nullable=False, default="PENDING", index=True)
    search_query = Column(Text, nullable=False)
    attempt_count = Column(Integer, nullable=False, default=0)
    max_retries = Column(Integer, nullable=False, default=3)
    listings_found = Column(Integer, nullable=True)
    businesses_saved = Column(Integer, nullable=True)
    error_message = Column(Text, nullable=True)
    blocked_reason = Column(String(100), nullable=True)
    last_attempt_at = Column(DateTime(timezone=True), nullable=True, index=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    location = relationship("Location")
    category = relationship("Category")
