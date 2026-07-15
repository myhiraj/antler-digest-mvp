from datetime import datetime
from typing import List
from pydantic import BaseModel, Field


class Subscriber(BaseModel):
    slack_user_id: str
    topic_ids: List[str] = []
    subscribed_at: datetime = Field(default_factory=datetime.utcnow)
