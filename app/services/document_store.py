import motor.motor_asyncio
from app.config import settings
from app.models.document import Document
from app.models.chunk import Chunk
from app.models.topic_output import TopicOutput
from typing import List, Optional
from datetime import datetime, timezone

_client = motor.motor_asyncio.AsyncIOMotorClient(settings.mongodb_uri_with_tls)
_db = _client["vc_digest"]
_documents = _db["documents"]
_chunks = _db["chunks"]
_poll_state = _db["poll_state"]
_topic_outputs = _db["topic_outputs"]


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
    if not doc:
        return None
    ts = doc.get("last_polled_at")
    if ts and ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return ts


async def set_last_polled(source: str, ts: datetime) -> None:
    await _poll_state.update_one(
        {"source": source},
        {"$set": {"last_polled_at": ts}},
        upsert=True,
    )


async def save_topic_output(output: TopicOutput) -> None:
    data = output.model_dump()
    # MongoDB has no native date type — store as midnight UTC datetime
    data["date"] = datetime(output.date.year, output.date.month, output.date.day, tzinfo=timezone.utc)
    await _topic_outputs.update_one(
        {"topic_id": output.topic_id, "date": data["date"]},
        {"$set": data},
        upsert=True,
    )


async def get_latest_topic_output(topic_id: str) -> Optional[TopicOutput]:
    doc = await _topic_outputs.find_one({"topic_id": topic_id}, sort=[("date", -1)])
    if doc is None:
        return None
    doc.pop("_id", None)
    if isinstance(doc.get("date"), datetime):
        doc["date"] = doc["date"].date()
    return TopicOutput(**doc)


async def mark_chunks_used(chunks: List[Chunk]) -> None:
    if not chunks:
        return
    ops = [
        {"document_id": c.document_id, "chunk_index": c.chunk_index}
        for c in chunks
    ]
    await _chunks.update_many(
        {"$or": ops},
        {"$set": {"used_in_digest": True}},
    )
