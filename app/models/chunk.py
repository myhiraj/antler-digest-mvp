from datetime import datetime
from pydantic import BaseModel, Field
from typing import List, Optional


class Chunk(BaseModel):
    document_id: str
    topic_id: str
    text: str
    embedding: Optional[List[float]] = None
    chunk_index: int
    ingested_at: datetime = Field(default_factory=datetime.utcnow)
    used_in_digest: bool = False
