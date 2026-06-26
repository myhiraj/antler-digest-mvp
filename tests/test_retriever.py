import os
import pytest
import pytest_asyncio
from unittest.mock import MagicMock, patch, AsyncMock

os.environ.setdefault("MONGODB_URI", "mongodb://localhost:27017")
os.environ.setdefault("VOYAGE_API_KEY", "test-voyage-key")
os.environ.setdefault("POSTMARK_WEBHOOK_TOKEN", "test-token")
os.environ.setdefault("ANTHROPIC_API_KEY", "test-anthropic-key")

from app.models.chunk import Chunk


def _fake_embedding(dim: int = 1024) -> list:
    return [0.1] * dim


def _make_chunk_doc(**kwargs) -> dict:
    defaults = {
        "document_id": "doc123",
        "topic_id": "menap_general",
        "text": "Some chunk text about startups.",
        "chunk_index": 0,
    }
    defaults.update(kwargs)
    return defaults


def _make_async_cursor(docs: list):
    async def _aiter(self):
        for doc in docs:
            yield doc

    cursor = MagicMock()
    cursor.__aiter__ = _aiter
    return cursor


@pytest.mark.asyncio
async def test_retrieve_chunks_returns_chunk_objects():
    docs = [_make_chunk_doc(chunk_index=i) for i in range(3)]

    with patch("app.services.retriever._voyage_client") as mock_voyage, \
         patch("app.services.retriever._chunks") as mock_col:

        mock_voyage.embed.return_value = MagicMock(embeddings=[_fake_embedding()])
        mock_col.aggregate.return_value = _make_async_cursor(docs)

        from app.services.retriever import retrieve_chunks
        results = await retrieve_chunks("menap_general", "test query")

    assert len(results) == 3
    assert all(isinstance(r, Chunk) for r in results)


@pytest.mark.asyncio
async def test_retrieve_chunks_filters_by_topic_id():
    with patch("app.services.retriever._voyage_client") as mock_voyage, \
         patch("app.services.retriever._chunks") as mock_col:

        mock_voyage.embed.return_value = MagicMock(embeddings=[_fake_embedding()])
        mock_col.aggregate.return_value = _make_async_cursor([])

        from app.services.retriever import retrieve_chunks
        await retrieve_chunks("menap_general", "test query")

        pipeline = mock_col.aggregate.call_args[0][0]
        vs_filter = pipeline[0]["$vectorSearch"]["filter"]
        assert vs_filter["topic_id"] == {"$eq": "menap_general"}
        assert vs_filter["used_in_digest"] == {"$eq": False}
        assert "$gte" in vs_filter["ingested_at"]


@pytest.mark.asyncio
async def test_retrieve_chunks_empty_result_returns_empty_list():
    with patch("app.services.retriever._voyage_client") as mock_voyage, \
         patch("app.services.retriever._chunks") as mock_col:

        mock_voyage.embed.return_value = MagicMock(embeddings=[_fake_embedding()])
        mock_col.aggregate.return_value = _make_async_cursor([])

        from app.services.retriever import retrieve_chunks
        results = await retrieve_chunks("global_vc", "test query")

    assert results == []


@pytest.mark.asyncio
async def test_retrieve_chunks_passes_num_candidates():
    with patch("app.services.retriever._voyage_client") as mock_voyage, \
         patch("app.services.retriever._chunks") as mock_col:

        mock_voyage.embed.return_value = MagicMock(embeddings=[_fake_embedding()])
        mock_col.aggregate.return_value = _make_async_cursor([])

        from app.services.retriever import retrieve_chunks
        await retrieve_chunks("menap_general", "test query", num_candidates=50)

        pipeline = mock_col.aggregate.call_args[0][0]
        assert pipeline[0]["$vectorSearch"]["numCandidates"] == 50


@pytest.mark.asyncio
async def test_retrieve_chunks_strips_id_field():
    doc = _make_chunk_doc()
    doc["_id"] = "some-mongo-id"

    with patch("app.services.retriever._voyage_client") as mock_voyage, \
         patch("app.services.retriever._chunks") as mock_col:

        mock_voyage.embed.return_value = MagicMock(embeddings=[_fake_embedding()])
        mock_col.aggregate.return_value = _make_async_cursor([doc])

        from app.services.retriever import retrieve_chunks
        results = await retrieve_chunks("menap_general", "test query")

    assert len(results) == 1
    assert not hasattr(results[0], "_id")


@pytest.mark.asyncio
async def test_retrieve_chunks_uses_query_input_type():
    with patch("app.services.retriever._voyage_client") as mock_voyage, \
         patch("app.services.retriever._chunks") as mock_col:

        mock_voyage.embed.return_value = MagicMock(embeddings=[_fake_embedding()])
        mock_col.aggregate.return_value = _make_async_cursor([])

        from app.services.retriever import retrieve_chunks
        await retrieve_chunks("menap_general", "some query")

        call_kwargs = mock_voyage.embed.call_args
        assert call_kwargs.kwargs.get("input_type") == "query" or \
               (len(call_kwargs.args) >= 3 and call_kwargs.args[2] == "query") or \
               "query" in str(call_kwargs)
