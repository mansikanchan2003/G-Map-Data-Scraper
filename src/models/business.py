from sqlalchemy import Column, String, Float, Boolean, DateTime, ForeignKey, Text, and_, func, or_
from sqlalchemy.orm import relationship
from src.database import Base

class Business(Base):
    __tablename__ = "businesses"

    business_id = Column(String(16), primary_key=True, index=True)
    job_id = Column(String(16), ForeignKey("jobs.job_id"), nullable=False, index=True)
    name = Column(String(500), nullable=False)
    address = Column(Text, nullable=True)
    phone = Column(String(20), nullable=True, index=True)
    email = Column(String(200), nullable=True)
    email_source_url = Column(String(500), nullable=True)
    email_enrichment_status = Column(String(100), nullable=True)
    email_enriched_at = Column(DateTime(timezone=True), nullable=True)
    website = Column(String(500), nullable=True)
    google_maps_url = Column(Text, nullable=True)
    place_id = Column(String(100), nullable=True)
    category = Column(String(200), nullable=False, index=True)
    district = Column(String(100), nullable=True)
    # Mirrors the location's tehsil alongside district/state/officename so an
    # audience can be filtered without joining back through jobs.
    tehsil = Column(String(100), nullable=True, index=True)
    state = Column(String(100), nullable=True)
    officename = Column(String(200), nullable=True)
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    distance_km = Column(Float, nullable=True)
    source_query = Column(Text, nullable=False)
    dedup_key = Column(String(200), nullable=False, unique=True)
    is_valid = Column(Boolean, nullable=False, default=True, index=True)
    validation_errors = Column(Text, nullable=True)
    discovered_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    job = relationship("Job")


# A business someone can be reached on: it has a phone number or an email.
#
# A listing with only a website is saved before its email is looked for, so
# for a minute or two a row exists with neither. Everything that shows or
# hands out businesses uses this, so such a row is never seen while it waits,
# nor if the job is interrupted before it can be removed.
CONTACTABLE = or_(
    and_(Business.phone.isnot(None), Business.phone != ""),
    and_(Business.email.isnot(None), Business.email != ""),
)
