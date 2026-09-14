from pydantic import BaseModel, ConfigDict
from datetime import datetime
from typing import Optional
from .location import LocationResponse
from .category import CategoryResponse

class JobBase(BaseModel):
    status: str
    search_query: str
    attempt_count: int
    max_retries: int
    listings_found: Optional[int] = None
    businesses_saved: Optional[int] = None
    error_message: Optional[str] = None
    blocked_reason: Optional[str] = None
    last_attempt_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

class JobResponse(JobBase):
    job_id: str
    location_id: str
    category_id: str
    created_at: datetime
    updated_at: datetime
    location: Optional[LocationResponse] = None
    category: Optional[CategoryResponse] = None

    model_config = ConfigDict(from_attributes=True)
