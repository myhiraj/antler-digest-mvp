"""
One-off backfill for evidence silently dropped by notion_sync's _create_evidence
after the Industry/Source Summary properties were added to the Evidence
database, before those Notion columns existed (or before their names matched
exactly). Every write in that window failed with a 400 "not a property that
exists" — pages.create is atomic, so no partial Evidence rows were created;
the signals were just dropped after being logged.

Re-runs sync_to_notion over chunks with used_in_digest=True and
ingested_at >= --since, the same way scripts/backfill_notion.py seeds the
databases from scratch. Chunks from before --since are NOT reprocessed, since
their evidence was written successfully before this bug and re-running would
create duplicate Evidence rows for those.

Run once, after confirming the Evidence database's Industry and Source
Summary columns exist with those exact names:

    python scripts/backfill_notion_since.py --since 2026-08-25
"""
import argparse
import asyncio
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

import motor.motor_asyncio

from app.config import settings
from app.models.chunk import Chunk
from app.services.notion_sync import sync_to_notion

BATCH_SIZE = 20


async def _fetch_chunks_since(cutoff: datetime) -> list[Chunk]:
    client = motor.motor_asyncio.AsyncIOMotorClient(settings.mongodb_uri_with_tls)
    db = client["vc_digest"]
    cursor = db["chunks"].find(
        {"used_in_digest": True, "ingested_at": {"$gte": cutoff}}
    ).sort("ingested_at", 1)

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


async def main(cutoff: datetime) -> None:
    if not settings.notion_api_key or not settings.notion_themes_database_id or not settings.notion_evidence_database_id:
        print("NOTION_API_KEY / NOTION_THEMES_DATABASE_ID / NOTION_EVIDENCE_DATABASE_ID must be set first.")
        sys.exit(1)

    print(f"Fetching chunks with used_in_digest=True and ingested_at >= {cutoff.isoformat()}...")
    chunks = await _fetch_chunks_since(cutoff)
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
    print(
        "Note: this re-runs signal extraction/classification, which can produce "
        "different theme groupings than the original failed run and may create "
        "a few duplicate Evidence rows for signals that already succeeded "
        "earlier in the window. Spot-check the Evidence database afterward."
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--since",
        type=str,
        required=True,
        help="YYYY-MM-DD (UTC) — reprocess chunks ingested on or after this date.",
    )
    args = parser.parse_args()
    since_cutoff = datetime.strptime(args.since, "%Y-%m-%d").replace(tzinfo=timezone.utc)

    asyncio.run(main(since_cutoff))
