from pydantic import BaseModel, ConfigDict, computed_field
from datetime import datetime
from typing import Optional

class BusinessBase(BaseModel):
    name: str
    address: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    email_source_url: Optional[str] = None
    email_enrichment_status: Optional[str] = None
    email_enriched_at: Optional[datetime] = None
    website: Optional[str] = None
    google_maps_url: Optional[str] = None
    category: str
    district: Optional[str] = None
    state: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    distance_km: Optional[float] = None
    is_valid: bool
    
    @computed_field
    @property
    def verified(self) -> bool:
        return self.is_valid

class BusinessResponse(BusinessBase):
    business_id: str
    job_id: str
    place_id: Optional[str] = None
    source_query: str
    dedup_key: str
    validation_errors: Optional[str] = None
    discovered_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
