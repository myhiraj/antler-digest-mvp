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


@pytest.mark.asyncio
async def test_generate_daily_digest_calls_both_topics():
    with patch("app.jobs.digest_job.retrieve_chunks", new_callable=AsyncMock) as mock_retrieve, \
         patch("app.jobs.digest_job.summarize_topic", new_callable=AsyncMock) as mock_summarize:

        mock_retrieve.return_value = [_fake_chunk()]
        mock_summarize.side_effect = lambda tid, _chunks: _fake_output(tid)

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
         patch("app.jobs.digest_job.summarize_topic", new_callable=AsyncMock) as mock_summarize:

        mock_retrieve.return_value = chunks
        mock_summarize.side_effect = lambda tid, ch: _fake_output(tid)

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
         patch("app.jobs.digest_job.summarize_topic", new_callable=AsyncMock) as mock_summarize:

        mock_summarize.side_effect = lambda tid, ch: _fake_output(tid)

        from app.jobs.digest_job import generate_daily_digest
        await generate_daily_digest()  # must not raise

    assert call_count["n"] == 2
    assert mock_summarize.call_count == 1
    assert mock_summarize.call_args.args[0] == "global_vc"


@pytest.mark.asyncio
async def test_generate_daily_digest_uses_broad_query():
    with patch("app.jobs.digest_job.retrieve_chunks", new_callable=AsyncMock) as mock_retrieve, \
         patch("app.jobs.digest_job.summarize_topic", new_callable=AsyncMock) as mock_summarize:

        mock_retrieve.return_value = []
        mock_summarize.side_effect = lambda tid, ch: _fake_output(tid)

        from app.jobs.digest_job import generate_daily_digest
        await generate_daily_digest()

    for c in mock_retrieve.call_args_list:
        query = c.kwargs.get("query") or c.args[1]
        assert "funding" in query
        assert "startup" in query
