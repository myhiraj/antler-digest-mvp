from datetime import datetime
from typing import Any, Dict
from pydantic import BaseModel, Field


class CompanyEnrichment(BaseModel):
    domain: str
    payload: Dict[str, Any]
    fetched_at: datetime = Field(default_factory=datetime.utcnow)
