import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

os.environ.setdefault("MONGODB_URI", "mongodb://localhost:27017")
os.environ.setdefault("VOYAGE_API_KEY", "test-voyage-key")
os.environ.setdefault("POSTMARK_WEBHOOK_TOKEN", "test-token")
os.environ.setdefault("ANTHROPIC_API_KEY", "test-anthropic-key")

from app.models.chunk import Chunk
from app.models.topic_output import TopicOutput


def _make_chunk(document_id: str = "doc1", topic_id: str = "menap_general", index: int = 0) -> Chunk:
    return Chunk(
        document_id=document_id,
        topic_id=topic_id,
        text=f"Startup raised $5M in seed round. Investor led the round. [chunk {index}]",
        chunk_index=index,
    )


def _fake_message(text: str = "## Digest\n- bullet point") -> MagicMock:
    content_block = MagicMock()
    content_block.text = text
    msg = MagicMock()
    msg.content = [content_block]
    return msg


@pytest.mark.asyncio
async def test_summarize_topic_returns_topic_output():
    chunks = [_make_chunk()]
    with patch("app.services.summarizer._client") as mock_client, \
         patch("app.services.summarizer.document_store") as mock_store:

        mock_client.messages.create = AsyncMock(return_value=_fake_message())
        mock_store.save_topic_output = AsyncMock()

        from app.services.summarizer import summarize_topic
        result = await summarize_topic("menap_general", chunks)

    assert isinstance(result, TopicOutput)
    assert result.topic_id == "menap_general"
    assert len(result.summary_text) > 0


@pytest.mark.asyncio
async def test_summarize_topic_persists_to_store():
    chunks = [_make_chunk()]
    with patch("app.services.summarizer._client") as mock_client, \
         patch("app.services.summarizer.document_store") as mock_store:

        mock_client.messages.create = AsyncMock(return_value=_fake_message())
        mock_store.save_topic_output = AsyncMock()

        from app.services.summarizer import summarize_topic
        result = await summarize_topic("menap_general", chunks)

    mock_store.save_topic_output.assert_awaited_once_with(result)


@pytest.mark.asyncio
async def test_summarize_topic_includes_all_document_ids_in_sources_used():
    chunks = [
        _make_chunk(document_id="doc-a", index=0),
        _make_chunk(document_id="doc-b", index=1),
        _make_chunk(document_id="doc-c", index=2),
    ]
    with patch("app.services.summarizer._client") as mock_client, \
         patch("app.services.summarizer.document_store") as mock_store:

        mock_client.messages.create = AsyncMock(return_value=_fake_message())
        mock_store.save_topic_output = AsyncMock()

        from app.services.summarizer import summarize_topic
        result = await summarize_topic("menap_general", chunks)

    assert set(result.sources_used) == {"doc-a", "doc-b", "doc-c"}


@pytest.mark.asyncio
async def test_summarize_topic_deduplicates_sources():
    chunks = [
        _make_chunk(document_id="doc-a", index=0),
        _make_chunk(document_id="doc-b", index=1),
        _make_chunk(document_id="doc-a", index=2),
        _make_chunk(document_id="doc-b", index=3),
    ]
    with patch("app.services.summarizer._client") as mock_client, \
         patch("app.services.summarizer.document_store") as mock_store:

        mock_client.messages.create = AsyncMock(return_value=_fake_message())
        mock_store.save_topic_output = AsyncMock()

        from app.services.summarizer import summarize_topic
        result = await summarize_topic("menap_general", chunks)

    assert len(result.sources_used) == 2


@pytest.mark.asyncio
async def test_summarize_topic_empty_chunks_skips_api_call():
    with patch("app.services.summarizer._client") as mock_client, \
         patch("app.services.summarizer.document_store") as mock_store:

        mock_client.messages.create = AsyncMock()
        mock_store.save_topic_output = AsyncMock()

        from app.services.summarizer import summarize_topic
        result = await summarize_topic("menap_general", [])

    mock_client.messages.create.assert_not_called()
    assert "_No new content" in result.summary_text
    mock_store.save_topic_output.assert_awaited_once()


@pytest.mark.asyncio
async def test_user_prompt_contains_menap_section_for_menap_general():
    chunks = [_make_chunk(topic_id="menap_general")]
    captured = {}

    async def capture_create(**kwargs):
        captured["messages"] = kwargs["messages"]
        return _fake_message()

    with patch("app.services.summarizer._client") as mock_client, \
         patch("app.services.summarizer.document_store") as mock_store:

        mock_client.messages.create = capture_create
        mock_store.save_topic_output = AsyncMock()

        from app.services.summarizer import summarize_topic
        await summarize_topic("menap_general", chunks)

    user_content = captured["messages"][0]["content"]
    assert "MENA-Specific Highlights" in user_content


@pytest.mark.asyncio
async def test_user_prompt_does_not_contain_menap_section_for_global_vc():
    chunks = [_make_chunk(topic_id="global_vc")]
    captured = {}

    async def capture_create(**kwargs):
        captured["messages"] = kwargs["messages"]
        return _fake_message()

    with patch("app.services.summarizer._client") as mock_client, \
         patch("app.services.summarizer.document_store") as mock_store:

        mock_client.messages.create = capture_create
        mock_store.save_topic_output = AsyncMock()

        from app.services.summarizer import summarize_topic
        await summarize_topic("global_vc", chunks)

    user_content = captured["messages"][0]["content"]
    assert "MENA-Specific Highlights" not in user_content


@pytest.mark.asyncio
async def test_summarize_topic_sets_chunk_count():
    chunks = [_make_chunk(index=i) for i in range(5)]
    with patch("app.services.summarizer._client") as mock_client, \
         patch("app.services.summarizer.document_store") as mock_store:

        mock_client.messages.create = AsyncMock(return_value=_fake_message())
        mock_store.save_topic_output = AsyncMock()

        from app.services.summarizer import summarize_topic
        result = await summarize_topic("menap_general", chunks)

    assert result.chunk_count == 5


@pytest.mark.asyncio
async def test_summarize_topic_records_enriched_domains():
    chunks = [_make_chunk()]
    enrichment = {"leantech.me": {"name": "Lean Technologies", "headcount": 159}}
    with patch("app.services.summarizer._client") as mock_client, \
         patch("app.services.summarizer.document_store") as mock_store:

        mock_client.messages.create = AsyncMock(return_value=_fake_message())
        mock_store.save_topic_output = AsyncMock()

        from app.services.summarizer import summarize_topic
        result = await summarize_topic("menap_general", chunks, enrichment)

    assert result.companies_enriched == ["leantech.me"]


@pytest.mark.asyncio
async def test_summarize_topic_prompt_weaves_in_enrichment_facts():
    chunks = [_make_chunk()]
    enrichment = {"leantech.me": {"name": "Lean Technologies", "headcount": 159}}
    captured = {}

    async def capture_create(**kwargs):
        captured["messages"] = kwargs["messages"]
        return _fake_message()

    with patch("app.services.summarizer._client") as mock_client, \
         patch("app.services.summarizer.document_store") as mock_store:

        mock_client.messages.create = capture_create
        mock_store.save_topic_output = AsyncMock()

        from app.services.summarizer import summarize_topic
        await summarize_topic("menap_general", chunks, enrichment)

    user_content = captured["messages"][0]["content"]
    assert "Lean Technologies" in user_content
    assert "headcount=159" in user_content
    assert "do not list this data separately" in user_content.lower()


@pytest.mark.asyncio
async def test_summarize_topic_no_enrichment_section_when_empty():
    chunks = [_make_chunk()]
    captured = {}

    async def capture_create(**kwargs):
        captured["messages"] = kwargs["messages"]
        return _fake_message()

    with patch("app.services.summarizer._client") as mock_client, \
         patch("app.services.summarizer.document_store") as mock_store:

        mock_client.messages.create = capture_create
        mock_store.save_topic_output = AsyncMock()

        from app.services.summarizer import summarize_topic
        await summarize_topic("menap_general", chunks)

    user_content = captured["messages"][0]["content"]
    assert "Company data" not in user_content


@pytest.mark.asyncio
async def test_extract_companies_returns_tool_input():
    chunks = [_make_chunk()]
    tool_block = MagicMock()
    tool_block.type = "tool_use"
    tool_block.name = "extract_companies"
    tool_block.input = {"companies": [{"name": "Lean Technologies", "domain": "leantech.me"}]}
    message = MagicMock()
    message.content = [tool_block]

    with patch("app.services.summarizer._client") as mock_client:
        mock_client.messages.create = AsyncMock(return_value=message)

        from app.services.summarizer import extract_companies
        result = await extract_companies(chunks)

    assert result == [{"name": "Lean Technologies", "domain": "leantech.me"}]


@pytest.mark.asyncio
async def test_extract_companies_empty_chunks_skips_api_call():
    with patch("app.services.summarizer._client") as mock_client:
        mock_client.messages.create = AsyncMock()

        from app.services.summarizer import extract_companies
        result = await extract_companies([])

    mock_client.messages.create.assert_not_called()
    assert result == []
