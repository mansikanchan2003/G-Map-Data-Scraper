from pydantic import BaseModel, ConfigDict
from datetime import datetime
from typing import Optional

class RunLogResponse(BaseModel):
    run_id: str
    trigger_source: str
    status: str
    jobs_attempted: int
    jobs_completed: int
    jobs_failed: int
    businesses_discovered: int
    businesses_new: int
    businesses_updated: int
    businesses_duplicate: int
    duration_seconds: Optional[float]
    error_summary: Optional[str]
    started_at: datetime
    completed_at: Optional[datetime]

    model_config = ConfigDict(from_attributes=True)
