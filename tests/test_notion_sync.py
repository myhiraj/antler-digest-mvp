import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

os.environ.setdefault("MONGODB_URI", "mongodb://localhost:27017")
os.environ.setdefault("VOYAGE_API_KEY", "test-voyage-key")
os.environ.setdefault("POSTMARK_WEBHOOK_TOKEN", "test-token")
os.environ.setdefault("ANTHROPIC_API_KEY", "test-anthropic-key")
os.environ.setdefault("NOTION_API_KEY", "test-notion-key")
os.environ.setdefault("NOTION_THEMES_DATABASE_ID", "themes-db-id")
os.environ.setdefault("NOTION_EVIDENCE_DATABASE_ID", "evidence-db-id")

from app.models.chunk import Chunk
from app.services import notion_sync


def _make_chunk(topic_id: str = "menap_general", source_url: str = None, source_name: str = None) -> Chunk:
    return Chunk(
        document_id="doc1",
        topic_id=topic_id,
        text="Regulator announces new fintech licensing framework.",
        chunk_index=0,
        source_url=source_url,
        source_name=source_name,
    )


def _fake_tool_message(tool_name: str, tool_input: dict) -> MagicMock:
    block = MagicMock()
    block.type = "tool_use"
    block.name = tool_name
    block.input = tool_input
    msg = MagicMock()
    msg.content = [block]
    return msg


def _notion_page(page_id: str, title: str, category: str = "Policy & Regulation") -> dict:
    return {
        "id": page_id,
        "properties": {
            "Title": {"title": [{"plain_text": title}]},
            "Category": {"select": {"name": category}},
        },
    }


def _patch_notion_configured():
    """Notion-touching code checks settings.notion_*_database_id truthiness
    before doing anything. settings is a module-level singleton instantiated
    from os.environ the first time ANY test module imports app.config —
    whichever test file happens to import it first in the session wins, so
    relying on os.environ.setdefault above is not reliable for these fields.
    Patch them explicitly wherever the code branches on them, matching the
    pattern test_harmonic.py uses for harmonic_api_key."""
    return patch.multiple(
        notion_sync.settings,
        notion_themes_database_id="themes-db-id",
        notion_evidence_database_id="evidence-db-id",
    )


# ---------------------------------------------------------------------------
# extract_signals
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_extract_signals_returns_tool_input_with_source_fallback():
    chunks = [_make_chunk(source_url="https://example.com/a", source_name="wamda")]
    signal = {
        "category": "Policy & Regulation",
        "geography": "UAE",
        "title": "New fintech licensing framework",
        "excerpt": "Regulator announces new fintech licensing framework.",
    }
    message = _fake_tool_message("extract_signals", {"signals": [signal]})

    with patch("app.services.notion_sync._anthropic_client") as mock_client:
        mock_client.messages.create = AsyncMock(return_value=message)
        result = await notion_sync.extract_signals(chunks)

    assert result[0]["source_url"] == "https://example.com/a"
    assert result[0]["source_name"] == "wamda"
    assert result[0]["topic_id"] == "menap_general"


@pytest.mark.asyncio
async def test_extract_signals_empty_chunks_skips_api_call():
    with patch("app.services.notion_sync._anthropic_client") as mock_client:
        mock_client.messages.create = AsyncMock()
        result = await notion_sync.extract_signals([])

    mock_client.messages.create.assert_not_called()
    assert result == []


@pytest.mark.asyncio
async def test_extract_signals_returns_empty_on_error():
    chunks = [_make_chunk()]
    with patch("app.services.notion_sync._anthropic_client") as mock_client:
        mock_client.messages.create = AsyncMock(side_effect=RuntimeError("boom"))
        result = await notion_sync.extract_signals(chunks)  # must not raise

    assert result == []


# ---------------------------------------------------------------------------
# get_open_themes
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_open_themes_returns_title_and_category():
    with patch("app.services.notion_sync._notion_client") as mock_notion, _patch_notion_configured():
        mock_notion.databases.query = AsyncMock(
            return_value={"results": [_notion_page("t1", "Saudi fintech licensing")]}
        )
        result = await notion_sync.get_open_themes("menap_general")

    assert result == [{"id": "t1", "title": "Saudi fintech licensing", "category": "Policy & Regulation"}]


@pytest.mark.asyncio
async def test_get_open_themes_returns_empty_when_not_configured():
    with patch.object(notion_sync, "_notion_client", None):
        result = await notion_sync.get_open_themes("menap_general")
    assert result == []


@pytest.mark.asyncio
async def test_get_open_themes_returns_empty_on_query_error():
    with patch("app.services.notion_sync._notion_client") as mock_notion, _patch_notion_configured():
        mock_notion.databases.query = AsyncMock(side_effect=RuntimeError("boom"))
        result = await notion_sync.get_open_themes("menap_general")  # must not raise
    assert result == []


# ---------------------------------------------------------------------------
# classify_evidence
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_classify_evidence_returns_tool_input():
    candidates = [
        {"category": "Policy & Regulation", "geography": "UAE", "title": "x", "excerpt": "y"}
    ]
    open_themes = [{"id": "t1", "title": "Existing theme", "category": "Policy & Regulation"}]
    classification = {"signal_index": 0, "decision": "existing_theme", "theme_id": "t1"}
    message = _fake_tool_message("classify_evidence", {"classifications": [classification]})

    with patch("app.services.notion_sync._anthropic_client") as mock_client:
        mock_client.messages.create = AsyncMock(return_value=message)
        result = await notion_sync.classify_evidence(candidates, open_themes)

    assert result == [classification]


@pytest.mark.asyncio
async def test_classify_evidence_empty_candidates_skips_api_call():
    with patch("app.services.notion_sync._anthropic_client") as mock_client:
        mock_client.messages.create = AsyncMock()
        result = await notion_sync.classify_evidence([], [])

    mock_client.messages.create.assert_not_called()
    assert result == []


# ---------------------------------------------------------------------------
# sync_to_notion — decision routing
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sync_to_notion_skips_when_not_configured():
    chunks = [_make_chunk()]
    with patch.object(notion_sync, "_notion_client", None):
        await notion_sync.sync_to_notion("menap_general", chunks)  # must not raise, no-op


@pytest.mark.asyncio
async def test_sync_to_notion_links_evidence_to_existing_theme():
    chunks = [_make_chunk()]
    signal = {
        "category": "Policy & Regulation",
        "geography": "UAE",
        "title": "New fintech licensing framework",
        "excerpt": "...",
        "source_url": None,
        "source_name": None,
        "topic_id": "menap_general",
    }

    with patch("app.services.notion_sync._notion_client"), \
         patch("app.services.notion_sync.review_uncategorized", new_callable=AsyncMock), \
         patch("app.services.notion_sync.extract_signals", new_callable=AsyncMock, return_value=[signal]), \
         patch("app.services.notion_sync.get_open_themes", new_callable=AsyncMock,
               return_value=[{"id": "t1", "title": "Existing theme", "category": "Policy & Regulation"}]), \
         patch("app.services.notion_sync._ensure_uncategorized_theme", new_callable=AsyncMock, return_value="unc-id"), \
         patch("app.services.notion_sync.classify_evidence", new_callable=AsyncMock,
               return_value=[{"signal_index": 0, "decision": "existing_theme", "theme_id": "t1"}]), \
         patch("app.services.notion_sync._touch_theme", new_callable=AsyncMock) as mock_touch, \
         patch("app.services.notion_sync._create_evidence", new_callable=AsyncMock) as mock_create_evidence, \
         _patch_notion_configured():

        await notion_sync.sync_to_notion("menap_general", chunks)

    mock_touch.assert_awaited_once_with("t1")
    mock_create_evidence.assert_awaited_once_with(signal, "t1")


@pytest.mark.asyncio
async def test_sync_to_notion_creates_new_theme_when_flagged():
    chunks = [_make_chunk()]
    signal = {
        "category": "Ecosystem Move",
        "geography": "Global",
        "title": "New accelerator launched",
        "excerpt": "...",
        "source_url": None,
        "source_name": None,
        "topic_id": "menap_general",
    }

    with patch("app.services.notion_sync._notion_client"), \
         patch("app.services.notion_sync.review_uncategorized", new_callable=AsyncMock), \
         patch("app.services.notion_sync.extract_signals", new_callable=AsyncMock, return_value=[signal]), \
         patch("app.services.notion_sync.get_open_themes", new_callable=AsyncMock, return_value=[]), \
         patch("app.services.notion_sync._ensure_uncategorized_theme", new_callable=AsyncMock, return_value="unc-id"), \
         patch("app.services.notion_sync.classify_evidence", new_callable=AsyncMock,
               return_value=[{"signal_index": 0, "decision": "new_theme", "new_theme_title": "Accelerator wave"}]), \
         patch("app.services.notion_sync._create_theme", new_callable=AsyncMock, return_value="new-t1") as mock_create_theme, \
         patch("app.services.notion_sync._create_evidence", new_callable=AsyncMock) as mock_create_evidence, \
         _patch_notion_configured():

        await notion_sync.sync_to_notion("menap_general", chunks)

    mock_create_theme.assert_awaited_once()
    assert mock_create_theme.await_args.kwargs["title"] == "Accelerator wave"
    mock_create_evidence.assert_awaited_once_with(signal, "new-t1")


@pytest.mark.asyncio
async def test_sync_to_notion_routes_weak_match_to_uncategorized():
    chunks = [_make_chunk()]
    signal = {
        "category": "Market & Sector Trend",
        "geography": "Global",
        "title": "Ambiguous observation",
        "excerpt": "...",
        "source_url": None,
        "source_name": None,
        "topic_id": "menap_general",
    }

    with patch("app.services.notion_sync._notion_client"), \
         patch("app.services.notion_sync.review_uncategorized", new_callable=AsyncMock), \
         patch("app.services.notion_sync.extract_signals", new_callable=AsyncMock, return_value=[signal]), \
         patch("app.services.notion_sync.get_open_themes", new_callable=AsyncMock, return_value=[]), \
         patch("app.services.notion_sync._ensure_uncategorized_theme", new_callable=AsyncMock, return_value="unc-id"), \
         patch("app.services.notion_sync.classify_evidence", new_callable=AsyncMock,
               return_value=[{"signal_index": 0, "decision": "uncategorized"}]), \
         patch("app.services.notion_sync._create_theme", new_callable=AsyncMock) as mock_create_theme, \
         patch("app.services.notion_sync._create_evidence", new_callable=AsyncMock) as mock_create_evidence, \
         _patch_notion_configured():

        await notion_sync.sync_to_notion("menap_general", chunks)

    mock_create_theme.assert_not_awaited()
    mock_create_evidence.assert_awaited_once_with(signal, "unc-id")


@pytest.mark.asyncio
async def test_sync_to_notion_never_raises_on_internal_failure():
    chunks = [_make_chunk()]
    with patch("app.services.notion_sync._notion_client"), \
         patch("app.services.notion_sync.review_uncategorized", new_callable=AsyncMock,
               side_effect=RuntimeError("boom")), \
         _patch_notion_configured():
        await notion_sync.sync_to_notion("menap_general", chunks)  # must not raise


# ---------------------------------------------------------------------------
# review_uncategorized
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_review_uncategorized_skips_below_cluster_threshold():
    with patch("app.services.notion_sync._ensure_uncategorized_theme", new_callable=AsyncMock, return_value="unc-id"), \
         patch("app.services.notion_sync._notion_client") as mock_notion, \
         patch("app.services.notion_sync._anthropic_client") as mock_anthropic, \
         _patch_notion_configured():

        mock_notion.databases.query = AsyncMock(
            return_value={"results": [_notion_page("e1", "item one"), _notion_page("e2", "item two")]}
        )

        await notion_sync.review_uncategorized("menap_general")

    mock_anthropic.messages.create.assert_not_called()


@pytest.mark.asyncio
async def test_review_uncategorized_promotes_cluster_to_new_theme():
    items = [_notion_page(f"e{i}", f"item {i}") for i in range(3)]
    cluster = {
        "theme_title": "Emerging pattern",
        "category": "Market & Sector Trend",
        "evidence_ids": ["e0", "e1", "e2"],
    }

    with patch("app.services.notion_sync._ensure_uncategorized_theme", new_callable=AsyncMock, return_value="unc-id"), \
         patch("app.services.notion_sync._notion_client") as mock_notion, \
         patch("app.services.notion_sync._anthropic_client") as mock_anthropic, \
         patch("app.services.notion_sync._create_theme", new_callable=AsyncMock, return_value="new-theme-id") as mock_create_theme, \
         _patch_notion_configured():

        mock_notion.databases.query = AsyncMock(return_value={"results": items})
        mock_notion.pages.update = AsyncMock()
        mock_anthropic.messages.create = AsyncMock(
            return_value=_fake_tool_message("review_clusters", {"clusters": [cluster]})
        )

        await notion_sync.review_uncategorized("menap_general")

    mock_create_theme.assert_awaited_once()
    assert mock_notion.pages.update.await_count == 3
    for call in mock_notion.pages.update.await_args_list:
        assert call.kwargs["properties"]["Theme"]["relation"] == [{"id": "new-theme-id"}]
