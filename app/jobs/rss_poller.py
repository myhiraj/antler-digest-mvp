import feedparser
import hashlib
import logging
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

from app.services.cleaner import clean_email
from app.services.document_store import document_exists, save_document, save_chunks
from app.services.chunker import chunk_text
from app.services.embedder import embed_chunks
from app.models.document import Document

logger = logging.getLogger(__name__)

RSS_FEEDS = [
    {"url": "https://www.wamda.com/feed", "topic_id": "menap_general", "source": "wamda"},
    {"url": "https://www.menabytes.com/feed/", "topic_id": "menap_general", "source": "menabytes"},
    {"url": "https://www.notboring.co/feed", "topic_id": "global_vc", "source": "not_boring"},
    {"url": "https://news.crunchbase.com/feed/", "topic_id": "global_vc", "source": "crunchbase"},
]


async def poll_rss_feeds() -> None:
    logger.info("Starting RSS poll")
    for feed_cfg in RSS_FEEDS:
        await _poll_feed(feed_cfg["url"], feed_cfg["topic_id"], feed_cfg["source"])
    logger.info("RSS poll complete")


async def _poll_feed(url: str, topic_id: str, source: str) -> None:
    feed = feedparser.parse(url)

    for entry in feed.entries:
        raw_text = entry.get("summary") or entry.get("content", [{}])[0].get("value", "")
        if not raw_text:
            continue

        content_hash = hashlib.sha256(raw_text.encode()).hexdigest()
        if await document_exists(content_hash):
            continue

        try:
            published_at = parsedate_to_datetime(entry.get("published", ""))
        except Exception:
            published_at = datetime.now(timezone.utc)

        clean_text = clean_email(raw_text)
        doc = Document(
            source=source,
            source_type="rss",
            topic_id=topic_id,
            raw_text=raw_text,
            clean_text=clean_text,
            content_hash=content_hash,
            ingested_at=datetime.now(timezone.utc),
            published_at=published_at,
        )

        await save_document(doc)

        chunks = chunk_text(doc)
        chunks = embed_chunks(chunks)
        await save_chunks(chunks)

        logger.info(f"Ingested RSS entry from {source}: {entry.get('title', '')}")
