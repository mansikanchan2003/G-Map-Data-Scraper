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
    """Full internal schema — includes email-enrichment metadata.
    Used by export services and internal tooling."""
    business_id: str
    job_id: str
    place_id: Optional[str] = None
    source_query: str
    dedup_key: str
    validation_errors: Optional[str] = None
    discovered_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class BusinessPublicResponse(BaseModel):
    """User-facing schema for GET /api/v1/businesses.
    Exposes exactly the nine intended public fields.
    Internal email-enrichment metadata is intentionally excluded."""
    name: str
    address: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    website: Optional[str] = None
    category: str
    district: Optional[str] = None
    state: Optional[str] = None
    verified: bool

    model_config = ConfigDict(from_attributes=True)

    @classmethod
    def from_orm_business(cls, biz: object) -> "BusinessPublicResponse":
        return cls(
            name=biz.name,
            address=biz.address,
            phone=biz.phone,
            email=biz.email,
            website=biz.website,
            category=biz.category,
            district=biz.district,
            state=biz.state,
            verified=biz.is_valid,
        )
