import os
import pytest
from unittest.mock import AsyncMock, patch, call
from datetime import date

os.environ.setdefault("MONGODB_URI", "mongodb://localhost:27017")
os.environ.setdefault("VOYAGE_API_KEY", "test-voyage-key")
os.environ.setdefault("POSTMARK_WEBHOOK_TOKEN", "test-token")
os.environ.setdefault("ANTHROPIC_API_KEY", "test-anthropic-key")

from app.models.chunk import Chunk
from app.models.topic_output import TopicOutput
from datetime import datetime, timezone


def _fake_chunk(topic_id: str = "menap_general") -> Chunk:
    return Chunk(document_id="doc1", topic_id=topic_id, text="chunk text", chunk_index=0)


def _fake_output(topic_id: str) -> TopicOutput:
    return TopicOutput(
        topic_id=topic_id,
        date=date.today(),
        summary_text="## Digest",
        sources_used=["doc1"],
        generated_at=datetime.now(timezone.utc),
        chunk_count=1,
    )


def _patch_no_enrichment():
    """Patch extract_companies to return no companies, so
    _get_company_enrichment short-circuits without touching Harmonic."""
    return patch("app.jobs.digest_job.extract_companies", new_callable=AsyncMock, return_value=[])


def _patch_mark_chunks_used():
    """mark_chunks_used hits real Mongo if unmocked; every test here uses
    a fake document_id that was never actually saved, so the write is a
    no-op we don't need for these assertions."""
    return patch("app.jobs.digest_job.mark_chunks_used", new_callable=AsyncMock)


@pytest.mark.asyncio
async def test_generate_daily_digest_calls_both_topics():
    with patch("app.jobs.digest_job.retrieve_chunks", new_callable=AsyncMock) as mock_retrieve, \
         patch("app.jobs.digest_job.summarize_topic", new_callable=AsyncMock) as mock_summarize, \
         _patch_no_enrichment(), _patch_mark_chunks_used():

        mock_retrieve.return_value = [_fake_chunk()]
        mock_summarize.side_effect = lambda tid, _chunks, _enrichment=None: _fake_output(tid)

        from app.jobs.digest_job import generate_daily_digest
        await generate_daily_digest()

    assert mock_retrieve.call_count == 2
    assert mock_summarize.call_count == 2
    called_topics = [c.args[0] for c in mock_retrieve.call_args_list]
    assert "menap_general" in called_topics
    assert "global_vc" in called_topics


@pytest.mark.asyncio
async def test_generate_daily_digest_passes_chunks_to_summarizer():
    chunks = [_fake_chunk(), _fake_chunk()]

    with patch("app.jobs.digest_job.retrieve_chunks", new_callable=AsyncMock) as mock_retrieve, \
         patch("app.jobs.digest_job.summarize_topic", new_callable=AsyncMock) as mock_summarize, \
         _patch_no_enrichment(), _patch_mark_chunks_used():

        mock_retrieve.return_value = chunks
        mock_summarize.side_effect = lambda tid, ch, enrichment=None: _fake_output(tid)

        from app.jobs.digest_job import generate_daily_digest
        await generate_daily_digest()

    for c in mock_summarize.call_args_list:
        assert c.args[1] == chunks


@pytest.mark.asyncio
async def test_generate_daily_digest_continues_on_topic_failure():
    call_count = {"n": 0}

    async def flaky_retrieve(topic_id, query):
        call_count["n"] += 1
        if topic_id == "menap_general":
            raise RuntimeError("simulated failure")
        return [_fake_chunk(topic_id)]

    with patch("app.jobs.digest_job.retrieve_chunks", side_effect=flaky_retrieve), \
         patch("app.jobs.digest_job.summarize_topic", new_callable=AsyncMock) as mock_summarize, \
         _patch_no_enrichment(), _patch_mark_chunks_used():

        mock_summarize.side_effect = lambda tid, ch, enrichment=None: _fake_output(tid)

        from app.jobs.digest_job import generate_daily_digest
        await generate_daily_digest()  # must not raise

    assert call_count["n"] == 2
    assert mock_summarize.call_count == 1
    assert mock_summarize.call_args.args[0] == "global_vc"


@pytest.mark.asyncio
async def test_generate_daily_digest_uses_broad_query():
    with patch("app.jobs.digest_job.retrieve_chunks", new_callable=AsyncMock) as mock_retrieve, \
         patch("app.jobs.digest_job.summarize_topic", new_callable=AsyncMock) as mock_summarize, \
         _patch_no_enrichment(), _patch_mark_chunks_used():

        mock_retrieve.return_value = []
        mock_summarize.side_effect = lambda tid, ch, enrichment=None: _fake_output(tid)

        from app.jobs.digest_job import generate_daily_digest
        await generate_daily_digest()

    for c in mock_retrieve.call_args_list:
        query = c.kwargs.get("query") or c.args[1]
        assert "funding" in query
        assert "startup" in query


@pytest.mark.asyncio
async def test_generate_daily_digest_enriches_companies_from_harmonic():
    chunks = [_fake_chunk()]

    with patch("app.jobs.digest_job.retrieve_chunks", new_callable=AsyncMock) as mock_retrieve, \
         patch("app.jobs.digest_job.summarize_topic", new_callable=AsyncMock) as mock_summarize, \
         patch("app.jobs.digest_job.extract_companies", new_callable=AsyncMock) as mock_extract, \
         patch("app.jobs.digest_job.get_cached_enrichments", new_callable=AsyncMock) as mock_cache, \
         patch("app.jobs.digest_job.fetch_companies", new_callable=AsyncMock) as mock_fetch, \
         patch("app.jobs.digest_job.save_company_enrichment", new_callable=AsyncMock) as mock_save_enrichment, \
         _patch_mark_chunks_used():

        mock_retrieve.return_value = chunks
        mock_extract.return_value = [{"name": "Lean Technologies", "domain": "leantech.me"}]
        mock_cache.return_value = {}
        mock_fetch.return_value = {"leantech.me": {"name": "Lean Technologies", "headcount": 159}}
        mock_summarize.side_effect = lambda tid, ch, enrichment=None: _fake_output(tid)

        from app.jobs.digest_job import generate_daily_digest
        await generate_daily_digest()

    mock_fetch.assert_any_call(["leantech.me"])
    assert mock_save_enrichment.await_count == 2  # once per topic (menap_general, global_vc)
    for c in mock_summarize.call_args_list:
        assert c.args[2] == {"leantech.me": {"name": "Lean Technologies", "headcount": 159}}


@pytest.mark.asyncio
async def test_generate_daily_digest_uses_cache_before_fetching():
    chunks = [_fake_chunk()]
    cached_payload = {"name": "Lean Technologies", "headcount": 159}

    with patch("app.jobs.digest_job.retrieve_chunks", new_callable=AsyncMock) as mock_retrieve, \
         patch("app.jobs.digest_job.summarize_topic", new_callable=AsyncMock) as mock_summarize, \
         patch("app.jobs.digest_job.extract_companies", new_callable=AsyncMock) as mock_extract, \
         patch("app.jobs.digest_job.get_cached_enrichments", new_callable=AsyncMock) as mock_cache, \
         patch("app.jobs.digest_job.fetch_companies", new_callable=AsyncMock) as mock_fetch, \
         patch("app.jobs.digest_job.save_company_enrichment", new_callable=AsyncMock) as mock_save_enrichment, \
         _patch_mark_chunks_used():

        mock_retrieve.return_value = chunks
        mock_extract.return_value = [{"name": "Lean Technologies", "domain": "leantech.me"}]
        mock_cache.return_value = {"leantech.me": cached_payload}
        mock_summarize.side_effect = lambda tid, ch, enrichment=None: _fake_output(tid)

        from app.jobs.digest_job import generate_daily_digest
        await generate_daily_digest()

    mock_fetch.assert_not_called()
    mock_save_enrichment.assert_not_awaited()
    for c in mock_summarize.call_args_list:
        assert c.args[2] == {"leantech.me": cached_payload}


@pytest.mark.asyncio
async def test_generate_daily_digest_continues_when_enrichment_fails():
    chunks = [_fake_chunk()]

    with patch("app.jobs.digest_job.retrieve_chunks", new_callable=AsyncMock) as mock_retrieve, \
         patch("app.jobs.digest_job.summarize_topic", new_callable=AsyncMock) as mock_summarize, \
         patch("app.jobs.digest_job.extract_companies", new_callable=AsyncMock) as mock_extract, \
         _patch_mark_chunks_used():

        mock_retrieve.return_value = chunks
        mock_extract.side_effect = RuntimeError("Claude call failed")
        mock_summarize.side_effect = lambda tid, ch, enrichment=None: _fake_output(tid)

        from app.jobs.digest_job import generate_daily_digest
        await generate_daily_digest()  # must not raise

    assert mock_summarize.call_count == 2
    for c in mock_summarize.call_args_list:
        assert c.args[2] == {}
