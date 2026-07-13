import logging
from datetime import date, datetime, timezone

from app.services.retriever import retrieve_chunks
from app.services.summarizer import summarize_topic, extract_companies
from app.services.harmonic import fetch_companies
from app.services.document_store import (
    mark_chunks_used,
    save_topic_output,
    get_cached_enrichments,
    save_company_enrichment,
)
from app.models.company_enrichment import CompanyEnrichment

logger = logging.getLogger(__name__)

TOPIC_IDS = ["menap_general", "global_vc"]
DIGEST_QUERY = (
    "VC funding startup investment raise seed Series A growth MENA "
    "ecosystem trends founder exit IPO"
)


async def _get_company_enrichment(chunks) -> dict:
    """Extract companies mentioned in the chunks and look them up in
    Harmonic, using a per-domain cache to avoid re-fetching unchanged
    data. Returns {domain: raw_payload}; never raises — enrichment
    failures should not block digest generation."""
    try:
        companies = await extract_companies(chunks)
    except Exception:
        logger.exception("extract_companies failed, continuing without enrichment")
        return {}

    domains = sorted({c["domain"] for c in companies if c.get("domain")})
    if not domains:
        return {}

    cached = await get_cached_enrichments(domains)
    missing = [d for d in domains if d not in cached]

    fresh = {}
    if missing:
        try:
            fresh = await fetch_companies(missing)
        except Exception:
            logger.exception("fetch_companies failed for domains=%r", missing)

        for domain, payload in fresh.items():
            await save_company_enrichment(
                CompanyEnrichment(
                    domain=domain,
                    payload=payload,
                    fetched_at=datetime.now(timezone.utc),
                )
            )

    return {**cached, **fresh}


async def generate_daily_digest() -> None:
    logger.info("Starting daily digest generation for %s", date.today().isoformat())
    for topic_id in TOPIC_IDS:
        try:
            chunks = await retrieve_chunks(topic_id, query=DIGEST_QUERY)
            logger.info("Retrieved %d chunks for topic_id=%r", len(chunks), topic_id)
            enrichment = await _get_company_enrichment(chunks)
            output = await summarize_topic(topic_id, chunks, enrichment)
            await mark_chunks_used(chunks)
            logger.info(
                "Digest generated: topic=%r chunks=%d companies_enriched=%d date=%s",
                topic_id,
                output.chunk_count,
                len(output.companies_enriched),
                output.date,
            )
        except Exception:
            logger.exception("Digest generation failed for topic_id=%r", topic_id)
    logger.info("Daily digest generation complete")
