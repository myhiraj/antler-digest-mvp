"""
One-off backfill of the Notion Signals & Themes databases from chunks already
stored in MongoDB, so the databases aren't empty on day one.

Run once, after the Notion integration is configured (NOTION_API_KEY,
NOTION_THEMES_DATABASE_ID, NOTION_EVIDENCE_DATABASE_ID in .env) and before the
daily digest job starts calling notion_sync.sync_to_notion on its own:

    python scripts/backfill_notion.py

Processes chunks oldest-first, grouped by topic_id and batched by day, calling
the same notion_sync.sync_to_notion() the daily job uses — including the
Uncategorized-bucket review — so a theme created from an early chunk is in
place to catch a later, related one.
"""
import asyncio
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

import motor.motor_asyncio

from app.config import settings
from app.models.chunk import Chunk
from app.services.notion_sync import sync_to_notion

BATCH_SIZE = 20


async def _fetch_all_chunks() -> list[Chunk]:
    client = motor.motor_asyncio.AsyncIOMotorClient(settings.mongodb_uri_with_tls)
    db = client["vc_digest"]
    cursor = db["chunks"].find({}).sort("ingested_at", 1)

    chunks = []
    async for doc in cursor:
        doc.pop("_id", None)
        chunks.append(Chunk(**doc))
    return chunks


def _group_by_topic_and_day(chunks: list[Chunk]) -> dict[str, list[list[Chunk]]]:
    by_topic: dict[str, list[Chunk]] = defaultdict(list)
    for chunk in chunks:
        by_topic[chunk.topic_id].append(chunk)

    batches_by_topic: dict[str, list[list[Chunk]]] = {}
    for topic_id, topic_chunks in by_topic.items():
        by_day: dict[str, list[Chunk]] = defaultdict(list)
        for chunk in topic_chunks:
            day_key = chunk.ingested_at.date().isoformat()
            by_day[day_key].append(chunk)

        batches: list[list[Chunk]] = []
        for day_key in sorted(by_day.keys()):
            day_chunks = by_day[day_key]
            for i in range(0, len(day_chunks), BATCH_SIZE):
                batches.append(day_chunks[i : i + BATCH_SIZE])
        batches_by_topic[topic_id] = batches

    return batches_by_topic


async def main() -> None:
    if not settings.notion_api_key or not settings.notion_themes_database_id or not settings.notion_evidence_database_id:
        print("NOTION_API_KEY / NOTION_THEMES_DATABASE_ID / NOTION_EVIDENCE_DATABASE_ID must be set in .env first.")
        sys.exit(1)

    print("Fetching all chunks from MongoDB...")
    chunks = await _fetch_all_chunks()
    print(f"Fetched {len(chunks)} chunks.")

    if not chunks:
        print("Nothing to backfill.")
        return

    batches_by_topic = _group_by_topic_and_day(chunks)

    total_batches = 0
    for topic_id, batches in batches_by_topic.items():
        print(f"\nTopic {topic_id!r}: {len(batches)} batches, processing oldest-first...")
        for i, batch in enumerate(batches):
            print(f"  batch {i + 1}/{len(batches)} ({len(batch)} chunks)...")
            await sync_to_notion(topic_id, batch)
            total_batches += 1

    print(f"\nBackfill complete. {total_batches} batches processed across {len(batches_by_topic)} topics.")
    print("Spot-check the Notion page before letting the daily job start layering on top.")


if __name__ == "__main__":
    asyncio.run(main())
