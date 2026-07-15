import time
import pytest
from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient

import os
os.environ.setdefault("MONGODB_URI", "mongodb://localhost:27017")
os.environ.setdefault("VOYAGE_API_KEY", "test-voyage-key")
os.environ.setdefault("POSTMARK_WEBHOOK_TOKEN", "test-secret")
os.environ.setdefault("ANTHROPIC_API_KEY", "test-anthropic-key")
os.environ.setdefault("SLACK_BOT_TOKEN", "xoxb-test-token")

from slack_sdk.signature import SignatureVerifier

from app.main import app  # noqa: E402
from app.models.subscriber import Subscriber  # noqa: E402
from app.config import settings  # noqa: E402

# pydantic-settings reads .env directly, so a real SLACK_SIGNING_SECRET
# already present in .env takes precedence over any os.environ override —
# sign test requests with whatever the app actually resolved to.
SIGNING_SECRET = settings.slack_signing_secret


@pytest.fixture()
def client():
    with TestClient(app) as c:
        yield c


def _signed_headers(body: str) -> dict:
    timestamp = str(int(time.time()))
    verifier = SignatureVerifier(signing_secret=SIGNING_SECRET)
    signature = verifier.generate_signature(timestamp=timestamp, body=body)
    return {
        "X-Slack-Request-Timestamp": timestamp,
        "X-Slack-Signature": signature,
        "Content-Type": "application/x-www-form-urlencoded",
    }


def _post_command(client, command="/subscribe", text="", user_id="U123"):
    body = f"command={command}&text={text}&user_id={user_id}"
    return client.post("/slack/commands", content=body, headers=_signed_headers(body))


@patch("app.routes.slack.set_home_tab", new_callable=AsyncMock)
@patch("app.routes.slack.add_subscription", new_callable=AsyncMock)
def test_subscribe_all_topics(mock_add, mock_home, client):
    mock_add.return_value = Subscriber(slack_user_id="U123", topic_ids=["menap_general", "global_vc"])

    resp = _post_command(client, command="/subscribe", text="")

    assert resp.status_code == 200
    mock_add.assert_awaited_once_with("U123", ["menap_general", "global_vc"])
    assert "menap_general" in resp.json()["text"]
    assert "global_vc" in resp.json()["text"]


@patch("app.routes.slack.set_home_tab", new_callable=AsyncMock)
@patch("app.routes.slack.add_subscription", new_callable=AsyncMock)
def test_subscribe_single_topic(mock_add, mock_home, client):
    mock_add.return_value = Subscriber(slack_user_id="U123", topic_ids=["menap_general"])

    resp = _post_command(client, command="/subscribe", text="menap_general")

    assert resp.status_code == 200
    mock_add.assert_awaited_once_with("U123", ["menap_general"])


@patch("app.routes.slack.set_home_tab", new_callable=AsyncMock)
@patch("app.routes.slack.remove_subscription", new_callable=AsyncMock)
def test_unsubscribe_single_topic(mock_remove, mock_home, client):
    mock_remove.return_value = Subscriber(slack_user_id="U123", topic_ids=["global_vc"])

    resp = _post_command(client, command="/unsubscribe", text="menap_general")

    assert resp.status_code == 200
    mock_remove.assert_awaited_once_with("U123", ["menap_general"])


@patch("app.routes.slack.set_home_tab", new_callable=AsyncMock)
@patch("app.routes.slack.remove_subscription", new_callable=AsyncMock)
def test_unsubscribe_all_shows_no_subscriptions(mock_remove, mock_home, client):
    mock_remove.return_value = Subscriber(slack_user_id="U123", topic_ids=[])

    resp = _post_command(client, command="/unsubscribe", text="")

    assert resp.status_code == 200
    assert "unsubscribed" in resp.json()["text"].lower()


def test_unknown_topic_rejected(client):
    resp = _post_command(client, command="/subscribe", text="not_a_real_topic")

    assert resp.status_code == 200
    assert "unknown topic" in resp.json()["text"].lower()


def test_invalid_signature_rejected(client):
    body = "command=/subscribe&text=&user_id=U123"
    resp = client.post(
        "/slack/commands",
        content=body,
        headers={
            "X-Slack-Request-Timestamp": str(int(time.time())),
            "X-Slack-Signature": "v0=deadbeef",
            "Content-Type": "application/x-www-form-urlencoded",
        },
    )
    assert resp.status_code == 401


def test_missing_user_id_rejected(client):
    body = "command=/subscribe&text="
    resp = client.post("/slack/commands", content=body, headers=_signed_headers(body))
    assert resp.status_code == 400
