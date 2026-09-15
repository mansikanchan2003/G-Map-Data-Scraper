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
    jobs_total: int = 0
    jobs_retried: int = 0
    jobs_recovered: int = 0
    email_enriched: int = 0
    email_found: int = 0
    email_not_found: int = 0
    email_failed: int = 0
    errors_count: int = 0

    model_config = ConfigDict(from_attributes=True)
