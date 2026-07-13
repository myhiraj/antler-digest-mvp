import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

os.environ.setdefault("MONGODB_URI", "mongodb://localhost:27017")
os.environ.setdefault("VOYAGE_API_KEY", "test-voyage-key")
os.environ.setdefault("POSTMARK_WEBHOOK_TOKEN", "test-token")
os.environ.setdefault("ANTHROPIC_API_KEY", "test-anthropic-key")
os.environ.setdefault("HARMONIC_API_KEY", "test-harmonic-key")

from app.services import harmonic


def _mock_response(status_code: int, json_data=None, text: str = ""):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data
    resp.text = text
    return resp


@pytest.mark.asyncio
async def test_fetch_company_returns_payload_on_200():
    payload = {"name": "Lean Technologies", "headcount": 159}
    mock_client = MagicMock()
    mock_client.post = AsyncMock(return_value=_mock_response(200, payload))
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("app.services.harmonic.httpx.AsyncClient", return_value=mock_client):
        result = await harmonic.fetch_company("leantech.me")

    assert result == payload
    mock_client.post.assert_awaited_once()
    call = mock_client.post.await_args
    assert call.kwargs["params"] == {"website_domain": "leantech.me"}
    assert call.kwargs["headers"]["apikey"] == harmonic.settings.harmonic_api_key


@pytest.mark.asyncio
async def test_fetch_company_returns_none_on_404():
    mock_client = MagicMock()
    mock_client.post = AsyncMock(return_value=_mock_response(404))
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("app.services.harmonic.httpx.AsyncClient", return_value=mock_client):
        result = await harmonic.fetch_company("nonexistent.example")

    assert result is None


@pytest.mark.asyncio
async def test_fetch_company_returns_none_on_error_status():
    mock_client = MagicMock()
    mock_client.post = AsyncMock(return_value=_mock_response(500, text="server error"))
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("app.services.harmonic.httpx.AsyncClient", return_value=mock_client):
        result = await harmonic.fetch_company("harmonic.ai")

    assert result is None


@pytest.mark.asyncio
async def test_fetch_company_returns_none_without_api_key():
    with patch.object(harmonic.settings, "harmonic_api_key", ""):
        result = await harmonic.fetch_company("harmonic.ai")
    assert result is None


@pytest.mark.asyncio
async def test_fetch_company_returns_none_on_request_exception():
    import httpx

    mock_client = MagicMock()
    mock_client.post = AsyncMock(side_effect=httpx.ConnectError("boom"))
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("app.services.harmonic.httpx.AsyncClient", return_value=mock_client):
        result = await harmonic.fetch_company("harmonic.ai")

    assert result is None


@pytest.mark.asyncio
async def test_fetch_companies_returns_dict_keyed_by_domain():
    async def fake_fetch(domain):
        if domain == "found.example":
            return {"name": "Found Co"}
        return None

    with patch("app.services.harmonic.fetch_company", side_effect=fake_fetch):
        result = await harmonic.fetch_companies(["found.example", "missing.example"])

    assert result == {"found.example": {"name": "Found Co"}}


@pytest.mark.asyncio
async def test_fetch_companies_empty_list():
    result = await harmonic.fetch_companies([])
    assert result == {}
