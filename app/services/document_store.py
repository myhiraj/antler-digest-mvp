import motor.motor_asyncio
from app.config import settings
from app.models.document import Document
from app.models.chunk import Chunk
from typing import List, Optional
from datetime import datetime, timezone

_client = motor.motor_asyncio.AsyncIOMotorClient(settings.mongodb_uri)
_db = _client["vc_digest"]
_documents = _db["documents"]
_chunks = _db["chunks"]
_poll_state = _db["poll_state"]


async def document_exists(content_hash: str) -> bool:
    doc = await _documents.find_one({"content_hash": content_hash}, {"_id": 1})
    return doc is not None


async def save_document(doc: Document) -> str:
    result = await _documents.insert_one(doc.model_dump())
    return str(result.inserted_id)


async def save_chunks(chunks: List[Chunk]) -> None:
    if not chunks:
        return
    await _chunks.insert_many([c.model_dump() for c in chunks])


async def get_last_polled(source: str) -> Optional[datetime]:
    doc = await _poll_state.find_one({"source": source})
    return doc["last_polled_at"] if doc else None


async def set_last_polled(source: str, ts: datetime) -> None:
    await _poll_state.update_one(
        {"source": source},
        {"$set": {"last_polled_at": ts}},
        upsert=True,
    )
