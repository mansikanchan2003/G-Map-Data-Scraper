from pydantic import BaseModel, ConfigDict
from datetime import datetime
from typing import Optional

class CategoryBase(BaseModel):
    category_name: str
    persona: Optional[str] = None

class CategoryResponse(CategoryBase):
    category_id: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
