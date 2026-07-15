import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone

import os
os.environ.setdefault("MONGODB_URI", "mongodb://localhost:27017")
os.environ.setdefault("VOYAGE_API_KEY", "test-voyage-key")
os.environ.setdefault("POSTMARK_WEBHOOK_TOKEN", "test-secret")
os.environ.setdefault("ANTHROPIC_API_KEY", "test-anthropic-key")

from app.services import document_store

NOW = datetime.now(timezone.utc)


def _make_cursor(docs):
    async def gen():
        for d in docs:
            yield d
    mock = MagicMock()
    mock.find.return_value = gen()
    return mock


@pytest.mark.asyncio
async def test_add_subscription_upserts_and_returns_subscriber():
    mock_col = AsyncMock()
    mock_col.update_one = AsyncMock()
    mock_col.find_one = AsyncMock(
        return_value={"slack_user_id": "U123", "topic_ids": ["menap_general"], "subscribed_at": NOW}
    )
    with patch.object(document_store, "_subscribers", mock_col):
        result = await document_store.add_subscription("U123", ["menap_general"])

    mock_col.update_one.assert_awaited_once()
    filter_arg, update_arg = mock_col.update_one.call_args[0][:2]
    assert filter_arg == {"slack_user_id": "U123"}
    assert update_arg["$addToSet"] == {"topic_ids": {"$each": ["menap_general"]}}
    assert result.slack_user_id == "U123"
    assert result.topic_ids == ["menap_general"]


@pytest.mark.asyncio
async def test_remove_subscription_pulls_topics():
    mock_col = AsyncMock()
    mock_col.update_one = AsyncMock()
    mock_col.find_one = AsyncMock(
        return_value={"slack_user_id": "U123", "topic_ids": [], "subscribed_at": NOW}
    )
    with patch.object(document_store, "_subscribers", mock_col):
        result = await document_store.remove_subscription("U123", ["menap_general"])

    mock_col.update_one.assert_awaited_once_with(
        {"slack_user_id": "U123"},
        {"$pull": {"topic_ids": {"$in": ["menap_general"]}}},
    )
    assert result.topic_ids == []


@pytest.mark.asyncio
async def test_get_subscriber_returns_none_when_not_found():
    mock_col = AsyncMock()
    mock_col.find_one = AsyncMock(return_value=None)
    with patch.object(document_store, "_subscribers", mock_col):
        result = await document_store.get_subscriber("U999")
    assert result is None


@pytest.mark.asyncio
async def test_get_subscribers_for_topic_filters_correctly():
    docs = [
        {"_id": "1", "slack_user_id": "U1", "topic_ids": ["menap_general"], "subscribed_at": NOW},
        {"_id": "2", "slack_user_id": "U2", "topic_ids": ["menap_general", "global_vc"], "subscribed_at": NOW},
    ]
    mock_col = _make_cursor(docs)
    with patch.object(document_store, "_subscribers", mock_col):
        results = await document_store.get_subscribers_for_topic("menap_general")

    mock_col.find.assert_called_once_with({"topic_ids": "menap_general"})
    assert {r.slack_user_id for r in results} == {"U1", "U2"}


@pytest.mark.asyncio
async def test_get_subscribers_for_topic_empty():
    mock_col = _make_cursor([])
    with patch.object(document_store, "_subscribers", mock_col):
        results = await document_store.get_subscribers_for_topic("global_vc")
    assert results == []
