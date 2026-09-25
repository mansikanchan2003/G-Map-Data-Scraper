from pydantic import BaseModel, ConfigDict
from datetime import datetime
from typing import Optional

class LocationBase(BaseModel):
    pincode: str
    latitude: float
    longitude: float
    radius_km: float
    district: Optional[str] = None
    state: Optional[str] = None
    tehsil: Optional[str] = None
    anchor_name: Optional[str] = None
    source_dataset: str

class LocationResponse(LocationBase):
    location_id: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
