from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional


class Document(BaseModel):
    source: str
    source_type: str  # "email" or "rss"
    topic_id: str
    raw_text: str
    clean_text: str
    content_hash: str
    ingested_at: datetime
    published_at: Optional[datetime] = None
