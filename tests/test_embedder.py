import os
os.environ.setdefault("MONGODB_URI", "mongodb://localhost:27017")
os.environ.setdefault("VOYAGE_API_KEY", "test-voyage-key")
os.environ.setdefault("POSTMARK_WEBHOOK_TOKEN", "test-secret")

from unittest.mock import MagicMock, patch
from app.models.chunk import Chunk
from app.services import embedder

VOYAGE_3_DIM = 1024


def _make_chunks(n: int) -> list[Chunk]:
    return [
        Chunk(document_id="doc1", topic_id="menap_general", text=f"chunk text {i}", chunk_index=i)
        for i in range(n)
    ]


def _mock_voyage_result(n: int):
    result = MagicMock()
    result.embeddings = [[0.1] * VOYAGE_3_DIM for _ in range(n)]
    return result


def test_embed_chunks_populates_embeddings():
    chunks = _make_chunks(3)
    mock_result = _mock_voyage_result(3)
    with patch.object(embedder._client, "embed", return_value=mock_result) as mock_embed:
        out = embedder.embed_chunks(chunks)
    mock_embed.assert_called_once_with([c.text for c in chunks], model="voyage-3")
    assert all(c.embedding is not None for c in out)


def test_embed_chunks_correct_dimension():
    chunks = _make_chunks(2)
    with patch.object(embedder._client, "embed", return_value=_mock_voyage_result(2)):
        out = embedder.embed_chunks(chunks)
    for chunk in out:
        assert len(chunk.embedding) == VOYAGE_3_DIM


def test_embed_chunks_preserves_order():
    chunks = _make_chunks(4)
    embeddings = [[float(i)] * VOYAGE_3_DIM for i in range(4)]
    result = MagicMock()
    result.embeddings = embeddings
    with patch.object(embedder._client, "embed", return_value=result):
        out = embedder.embed_chunks(chunks)
    for i, chunk in enumerate(out):
        assert chunk.embedding[0] == float(i)


def test_embed_chunks_empty_list_skips_api():
    with patch.object(embedder._client, "embed") as mock_embed:
        out = embedder.embed_chunks([])
    mock_embed.assert_not_called()
    assert out == []


def test_embed_chunks_returns_same_chunk_objects():
    chunks = _make_chunks(2)
    with patch.object(embedder._client, "embed", return_value=_mock_voyage_result(2)):
        out = embedder.embed_chunks(chunks)
    # mutates in place and returns the same list
    assert out is chunks
