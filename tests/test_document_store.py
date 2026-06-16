import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone

import os
os.environ.setdefault("MONGODB_URI", "mongodb://localhost:27017")
os.environ.setdefault("VOYAGE_API_KEY", "test-voyage-key")
os.environ.setdefault("POSTMARK_WEBHOOK_TOKEN", "test-secret")

from app.models.document import Document
from app.models.chunk import Chunk
from app.services import document_store


def _make_doc(**kwargs) -> Document:
    defaults = dict(
        source="hello@digitaldigest.me",
        source_type="email",
        topic_id="menap_general",
        raw_text="Some newsletter text.",
        clean_text="Some newsletter text.",
        content_hash="abc123",
        ingested_at=datetime.now(timezone.utc),
    )
    return Document(**{**defaults, **kwargs})


@pytest.mark.asyncio
async def test_document_exists_returns_true_when_found():
    mock_col = AsyncMock()
    mock_col.find_one = AsyncMock(return_value={"_id": "some-id"})
    with patch.object(document_store, "_documents", mock_col):
        result = await document_store.document_exists("abc123")
    assert result is True
    mock_col.find_one.assert_awaited_once_with({"content_hash": "abc123"}, {"_id": 1})


@pytest.mark.asyncio
async def test_document_exists_returns_false_when_not_found():
    mock_col = AsyncMock()
    mock_col.find_one = AsyncMock(return_value=None)
    with patch.object(document_store, "_documents", mock_col):
        result = await document_store.document_exists("notfound")
    assert result is False


@pytest.mark.asyncio
async def test_save_document_inserts_and_returns_id():
    mock_result = MagicMock()
    mock_result.inserted_id = "deadbeef"
    mock_col = AsyncMock()
    mock_col.insert_one = AsyncMock(return_value=mock_result)
    with patch.object(document_store, "_documents", mock_col):
        doc = _make_doc()
        returned_id = await document_store.save_document(doc)
    assert returned_id == "deadbeef"
    mock_col.insert_one.assert_awaited_once()
    inserted = mock_col.insert_one.call_args[0][0]
    assert inserted["content_hash"] == "abc123"


@pytest.mark.asyncio
async def test_reforward_same_email_skips_insert():
    """Re-forwarding the same email must not insert a second document."""
    content_hash = "same-hash-both-times"
    doc = _make_doc(content_hash=content_hash)

    mock_col = AsyncMock()
    mock_col.find_one = AsyncMock(return_value={"_id": "existing-id"})
    mock_col.insert_one = AsyncMock()

    with patch.object(document_store, "_documents", mock_col):
        already_exists = await document_store.document_exists(content_hash)
        if not already_exists:
            await document_store.save_document(doc)

    mock_col.insert_one.assert_not_awaited()


@pytest.mark.asyncio
async def test_save_chunks_inserts_all():
    chunks = [
        Chunk(document_id="doc1", topic_id="menap_general", text="chunk a", chunk_index=0),
        Chunk(document_id="doc1", topic_id="menap_general", text="chunk b", chunk_index=1),
    ]
    mock_col = AsyncMock()
    mock_col.insert_many = AsyncMock()
    with patch.object(document_store, "_chunks", mock_col):
        await document_store.save_chunks(chunks)
    mock_col.insert_many.assert_awaited_once()
    inserted = mock_col.insert_many.call_args[0][0]
    assert len(inserted) == 2


@pytest.mark.asyncio
async def test_save_chunks_noop_on_empty():
    mock_col = AsyncMock()
    with patch.object(document_store, "_chunks", mock_col):
        await document_store.save_chunks([])
    mock_col.insert_many.assert_not_awaited()
