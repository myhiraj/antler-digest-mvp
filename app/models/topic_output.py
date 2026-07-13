from pydantic import BaseModel
from datetime import datetime, date
from typing import List


class TopicOutput(BaseModel):
    topic_id: str
    date: date
    summary_text: str
    sources_used: List[str]
    generated_at: datetime
    model_used: str = "claude-sonnet-4-6"
    chunk_count: int = 0
    companies_enriched: List[str] = []
