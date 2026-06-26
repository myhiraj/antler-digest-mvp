import logging
from datetime import date

from app.services.retriever import retrieve_chunks
from app.services.summarizer import summarize_topic
from app.services.document_store import mark_chunks_used, save_topic_output

logger = logging.getLogger(__name__)

TOPIC_IDS = ["menap_general", "global_vc"]
DIGEST_QUERY = (
    "VC funding startup investment raise seed Series A growth MENA "
    "ecosystem trends founder exit IPO"
)


async def generate_daily_digest() -> None:
    logger.info("Starting daily digest generation for %s", date.today().isoformat())
    for topic_id in TOPIC_IDS:
        try:
            chunks = await retrieve_chunks(topic_id, query=DIGEST_QUERY)
            logger.info("Retrieved %d chunks for topic_id=%r", len(chunks), topic_id)
            output = await summarize_topic(topic_id, chunks)
            await save_topic_output(output)
            await mark_chunks_used(chunks)
            logger.info(
                "Digest generated: topic=%r chunks=%d date=%s",
                topic_id,
                output.chunk_count,
                output.date,
            )
        except Exception:
            logger.exception("Digest generation failed for topic_id=%r", topic_id)
    logger.info("Daily digest generation complete")
