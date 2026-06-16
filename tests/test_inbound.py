import pytest
from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient

# Patch config before app import so pydantic-settings doesn't need a real .env
import os
os.environ.setdefault("MONGODB_URI", "mongodb://localhost:27017")
os.environ.setdefault("VOYAGE_API_KEY", "test-voyage-key")
os.environ.setdefault("POSTMARK_WEBHOOK_TOKEN", "test-secret")

from app.main import app  # noqa: E402

VALID_TOKEN = "test-secret"

POSTMARK_PAYLOAD = {
    "From": "hello@digitaldigest.me",
    "Subject": "Digital Digest #42",
    "TextBody": "Welcome to this week's digest. Startup A raised $5M. Startup B launched in MENA.",
    "HtmlBody": "<p>Welcome to this week's digest.</p>",
}


@pytest.fixture()
def client():
    with TestClient(app) as c:
        yield c


def _post(client, payload=None, token=VALID_TOKEN):
    return client.post(
        f"/inbound?token={token}",
        json=payload or POSTMARK_PAYLOAD,
    )


@patch("app.routes.inbound.save_chunks", new_callable=AsyncMock)
@patch("app.routes.inbound.embed_chunks", return_value=[])
@patch("app.routes.inbound.chunk_text", return_value=[])
@patch("app.routes.inbound.save_document", new_callable=AsyncMock)
@patch("app.routes.inbound.document_exists", new_callable=AsyncMock, return_value=False)
def test_happy_path(mock_exists, mock_save, mock_chunk, mock_embed, mock_save_chunks, client):
    resp = _post(client)
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
    mock_save.assert_awaited_once()


@patch("app.routes.inbound.document_exists", new_callable=AsyncMock, return_value=True)
def test_duplicate_skipped(mock_exists, client):
    resp = _post(client)
    assert resp.status_code == 200
    assert resp.json() == {"status": "skipped", "reason": "duplicate"}


@patch("app.routes.inbound.save_document", new_callable=AsyncMock)
@patch("app.routes.inbound.document_exists", new_callable=AsyncMock, return_value=False)
def test_empty_body_skipped(mock_exists, mock_save, client):
    payload = {**POSTMARK_PAYLOAD, "TextBody": "", "HtmlBody": ""}
    resp = _post(client, payload=payload)
    assert resp.status_code == 200
    assert resp.json() == {"status": "skipped", "reason": "empty body"}
    mock_save.assert_not_awaited()


def test_bad_token_rejected(client):
    resp = _post(client, token="wrong-token")
    assert resp.status_code == 401


@patch("app.routes.inbound.save_chunks", new_callable=AsyncMock)
@patch("app.routes.inbound.embed_chunks", return_value=[])
@patch("app.routes.inbound.chunk_text", return_value=[])
@patch("app.routes.inbound.save_document", new_callable=AsyncMock)
@patch("app.routes.inbound.document_exists", new_callable=AsyncMock, return_value=False)
def test_topic_resolved_to_menap(mock_exists, mock_save, mock_chunk, mock_embed, mock_save_chunks, client):
    resp = _post(client)
    assert resp.status_code == 200
    saved_doc = mock_save.call_args[0][0]
    assert saved_doc.topic_id == "menap_general"
    assert saved_doc.source_type == "email"
