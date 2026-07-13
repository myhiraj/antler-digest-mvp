import asyncio
import logging
from typing import Any, Dict, Optional

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

BASE_URL = "https://api.harmonic.ai"
REQUEST_TIMEOUT = 15.0


async def fetch_company(domain: str) -> Optional[Dict[str, Any]]:
    """Look up a company by website domain. Returns the full raw Harmonic
    payload, or None if the key is unset, the lookup fails, or no company
    is found for the domain."""
    if not settings.harmonic_api_key:
        logger.warning("fetch_company: HARMONIC_API_KEY not set, skipping domain=%r", domain)
        return None

    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
        try:
            response = await client.post(
                f"{BASE_URL}/companies",
                params={"website_domain": domain},
                headers={"apikey": settings.harmonic_api_key},
            )
        except httpx.HTTPError:
            logger.exception("fetch_company: request failed for domain=%r", domain)
            return None

    if response.status_code == 404:
        logger.info("fetch_company: no company found for domain=%r", domain)
        return None

    if response.status_code != 200:
        logger.warning(
            "fetch_company: unexpected status=%d for domain=%r body=%r",
            response.status_code,
            domain,
            response.text[:500],
        )
        return None

    data = response.json()
    if not data:
        return None

    return data


async def fetch_companies(domains: list[str], max_concurrency: int = 5) -> Dict[str, Dict[str, Any]]:
    """Look up multiple companies by domain, in parallel with bounded
    concurrency to stay well under Harmonic's 10 req/s rate limit. Returns
    a dict of domain -> raw payload, omitting domains that failed or had
    no match."""
    semaphore = asyncio.Semaphore(max_concurrency)

    async def _bounded_fetch(domain: str):
        async with semaphore:
            return domain, await fetch_company(domain)

    results = await asyncio.gather(*(_bounded_fetch(d) for d in domains))
    return {domain: payload for domain, payload in results if payload is not None}
