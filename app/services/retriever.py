import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import List

import motor.motor_asyncio
import voyageai

from app.config import settings
from app.models.chunk import Chunk

logger = logging.getLogger(__name__)

_voyage_client = voyageai.Client(api_key=settings.voyage_api_key)

_mongo_client = motor.motor_asyncio.AsyncIOMotorClient(settings.mongodb_uri_with_tls)
_db = _mongo_client["vc_digest"]
_chunks = _db["chunks"]

VECTOR_INDEX_NAME = "chunks_embedding_vector_index"
DEFAULT_LIMIT = 12
DEFAULT_NUM_CANDIDATES = 120


async def retrieve_chunks(
    topic_id: str,
    query: str,
    limit: int = DEFAULT_LIMIT,
    num_candidates: int = DEFAULT_NUM_CANDIDATES,
) -> List[Chunk]:
    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(
        None,
        lambda: _voyage_client.embed([query], model="voyage-3", input_type="query"),
    )
    query_embedding = result.embeddings[0]

    pipeline = [
        {
            "$vectorSearch": {
                "index": VECTOR_INDEX_NAME,
                "path": "embedding",
                "queryVector": query_embedding,
                "numCandidates": num_candidates,
                "limit": limit,
                "filter": {
                    "topic_id": {"$eq": topic_id},
                    "used_in_digest": {"$eq": False},
                    "ingested_at": {"$gte": datetime.now(timezone.utc) - timedelta(days=7)},
                },
            }
        },
        {
            "$project": {
                "_id": 0,
                "embedding": 0,
            }
        },
    ]

    results: List[Chunk] = []
    async for doc in _chunks.aggregate(pipeline):
        results.append(Chunk(**doc))

    if not results:
        logger.info("retrieve_chunks: no results for topic_id=%r", topic_id)

    return results
