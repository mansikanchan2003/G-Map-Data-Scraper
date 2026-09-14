from sqlalchemy import Column, String, Float, DateTime, func
from src.database import Base

class Location(Base):
    __tablename__ = "locations"

    location_id = Column(String(12), primary_key=True, index=True)
    pincode = Column(String(10), nullable=False, index=True)
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    radius_km = Column(Float, nullable=False, default=20.0)
    district = Column(String(100), nullable=True)
    state = Column(String(100), nullable=True)
    tehsil = Column(String(100), nullable=True)
    anchor_name = Column(String(200), nullable=True)
    pin_basis = Column(String(50), nullable=True)
    coordinate_precision = Column(String(20), nullable=True)
    source_dataset = Column(String(50), nullable=False, default='geocoded_locations')
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
