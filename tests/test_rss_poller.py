import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from datetime import datetime, timezone
from email.utils import format_datetime

import os
os.environ.setdefault("MONGODB_URI", "mongodb://localhost:27017")
os.environ.setdefault("VOYAGE_API_KEY", "test-voyage-key")
os.environ.setdefault("POSTMARK_WEBHOOK_TOKEN", "test-secret")

from app.jobs.rss_poller import _poll_feed, poll_rss_feeds, RSS_FEEDS


def _make_entry(title: str, summary: str, published: datetime) -> MagicMock:
    entry = MagicMock()
    entry.get = lambda key, default=None: {
        "title": title,
        "summary": summary,
        "published": format_datetime(published),
    }.get(key, default)
    return entry


def _make_feed(entries):
    feed = MagicMock()
    feed.entries = entries
    return feed


@pytest.mark.asyncio
@patch("app.jobs.rss_poller.embed_chunks", return_value=[])
@patch("app.jobs.rss_poller.chunk_text", return_value=[])
@patch("app.jobs.rss_poller.save_chunks", new_callable=AsyncMock)
@patch("app.jobs.rss_poller.save_document", new_callable=AsyncMock)
@patch("app.jobs.rss_poller.document_exists", new_callable=AsyncMock, return_value=False)
@patch("app.jobs.rss_poller.set_last_polled", new_callable=AsyncMock)
@patch("app.jobs.rss_poller.get_last_polled", new_callable=AsyncMock, return_value=None)
@patch("app.jobs.rss_poller.feedparser.parse")
async def test_new_entry_ingested(
    mock_parse, mock_get, mock_set, mock_exists, mock_save, mock_save_chunks, mock_chunk, mock_embed
):
    pub = datetime(2026, 6, 25, 9, 0, 0, tzinfo=timezone.utc)
    mock_parse.return_value = _make_feed([_make_entry("Article A", "Body of article A", pub)])

    await _poll_feed("https://example.com/feed", "menap_general", "test_source")

    mock_save.assert_awaited_once()
    doc = mock_save.call_args[0][0]
    assert doc.source == "test_source"
    assert doc.source_type == "rss"
    assert doc.topic_id == "menap_general"
    mock_set.assert_awaited_once()


@pytest.mark.asyncio
@patch("app.jobs.rss_poller.embed_chunks", return_value=[])
@patch("app.jobs.rss_poller.chunk_text", return_value=[])
@patch("app.jobs.rss_poller.save_chunks", new_callable=AsyncMock)
@patch("app.jobs.rss_poller.save_document", new_callable=AsyncMock)
@patch("app.jobs.rss_poller.document_exists", new_callable=AsyncMock, return_value=False)
@patch("app.jobs.rss_poller.set_last_polled", new_callable=AsyncMock)
@patch("app.jobs.rss_poller.get_last_polled", new_callable=AsyncMock)
@patch("app.jobs.rss_poller.feedparser.parse")
async def test_entry_older_than_last_polled_skipped(
    mock_parse, mock_get, mock_set, mock_exists, mock_save, mock_save_chunks, mock_chunk, mock_embed
):
    last_poll = datetime(2026, 6, 17, 10, 0, 0, tzinfo=timezone.utc)
    old_pub = datetime(2026, 6, 17, 8, 0, 0, tzinfo=timezone.utc)
    mock_get.return_value = last_poll
    mock_parse.return_value = _make_feed([_make_entry("Old Article", "Old body", old_pub)])

    await _poll_feed("https://example.com/feed", "menap_general", "test_source")

    mock_save.assert_not_awaited()
    mock_set.assert_awaited_once()


@pytest.mark.asyncio
@patch("app.jobs.rss_poller.save_document", new_callable=AsyncMock)
@patch("app.jobs.rss_poller.document_exists", new_callable=AsyncMock, return_value=True)
@patch("app.jobs.rss_poller.set_last_polled", new_callable=AsyncMock)
@patch("app.jobs.rss_poller.get_last_polled", new_callable=AsyncMock, return_value=None)
@patch("app.jobs.rss_poller.feedparser.parse")
async def test_duplicate_entry_skipped(mock_parse, mock_get, mock_set, mock_exists, mock_save):
    pub = datetime(2026, 6, 17, 9, 0, 0, tzinfo=timezone.utc)
    mock_parse.return_value = _make_feed([_make_entry("Dupe", "Same body", pub)])

    await _poll_feed("https://example.com/feed", "global_vc", "test_source")

    mock_save.assert_not_awaited()


@pytest.mark.asyncio
@patch("app.jobs.rss_poller.save_document", new_callable=AsyncMock)
@patch("app.jobs.rss_poller.document_exists", new_callable=AsyncMock, return_value=False)
@patch("app.jobs.rss_poller.set_last_polled", new_callable=AsyncMock)
@patch("app.jobs.rss_poller.get_last_polled", new_callable=AsyncMock, return_value=None)
@patch("app.jobs.rss_poller.feedparser.parse")
async def test_entry_with_no_body_skipped(mock_parse, mock_get, mock_set, mock_exists, mock_save):
    entry = MagicMock()
    entry.get = lambda key, default=None: {"title": "No body", "summary": "", "published": ""}.get(key, default)
    mock_parse.return_value = _make_feed([entry])

    await _poll_feed("https://example.com/feed", "global_vc", "test_source")

    mock_save.assert_not_awaited()


@pytest.mark.asyncio
@patch("app.jobs.rss_poller._poll_feed", new_callable=AsyncMock)
async def test_poll_rss_feeds_calls_all_feeds(mock_poll):
    await poll_rss_feeds()
    assert mock_poll.call_count == len(RSS_FEEDS)
    called_sources = {call.args[2] for call in mock_poll.call_args_list}
    expected_sources = {f["source"] for f in RSS_FEEDS}
    assert called_sources == expected_sources


def test_all_five_feeds_configured():
    sources = {f["source"] for f in RSS_FEEDS}
    assert "wamda" in sources
    assert "menabytes" in sources
    assert "mena_startup_digest" in sources
    assert "not_boring" in sources
    assert "crunchbase" in sources


def test_menabytes_url_has_rss_suffix():
    mb = next(f for f in RSS_FEEDS if f["source"] == "menabytes")
    assert mb["url"].endswith("/rss/")
