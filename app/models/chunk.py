from pydantic import BaseModel
from typing import List, Optional


class Chunk(BaseModel):
    document_id: str
    topic_id: str
    text: str
    embedding: Optional[List[float]] = None
    chunk_index: int
