import os
import pytest
from unittest.mock import AsyncMock, patch

os.environ.setdefault("MONGODB_URI", "mongodb://localhost:27017")
os.environ.setdefault("VOYAGE_API_KEY", "test-voyage-key")
os.environ.setdefault("POSTMARK_WEBHOOK_TOKEN", "test-token")
os.environ.setdefault("ANTHROPIC_API_KEY", "test-anthropic-key")

from app.services import email_client

SAMPLE_DIGEST = """*Antler MENAP — Daily Intelligence Digest*
_MENA & Pakistan Startup Ecosystem | Tuesday, 12 August 2026_

*Key Deals & Funding*
- Fincart raised a $2.8M seed round <https://example.com/a|Wamda>

*So What?* Early-stage capital keeps flowing into Egyptian fintech.

*Emerging Trends*
- More funds are backing Saudi AI infrastructure plays <https://example.com/b|MENAbytes>

*So What?* Watch for spillover into adjacent verticals.
"""

SAMPLE_DEALS = [
    {
        "company": "Fincart",
        "country": "Egypt",
        "round": "Seed",
        "amount": "$2.8M",
        "investors": "Plus VC, Jedar Capital",
        "source_url": "https://example.com/a",
        "source_name": "Wamda",
    }
]


def test_deals_table_html_renders_rows():
    html_out = email_client._deals_table_html(SAMPLE_DEALS)
    assert "Fincart" in html_out
    assert "Egypt" in html_out
    assert "$2.8M" in html_out
    assert 'href="https://example.com/a"' in html_out
    assert "Key Deals" in html_out


def test_deals_table_html_empty_deals_returns_empty_string():
    assert email_client._deals_table_html([]) == ""


def test_deals_table_html_escapes_html_in_fields():
    malicious_deals = [
        {
            "company": "<script>alert(1)</script>",
            "country": "UAE",
            "round": "Seed",
            "amount": "$1M",
            "investors": "Bad & Co",
            "source_url": None,
            "source_name": None,
        }
    ]
    html_out = email_client._deals_table_html(malicious_deals)
    assert "<script>" not in html_out
    assert "&lt;script&gt;" in html_out
    assert "Bad &amp; Co" in html_out


def test_strip_section_removes_key_deals_block():
    remaining = email_client._strip_section(SAMPLE_DIGEST, "Key Deals & Funding")
    assert "Fincart" not in remaining
    assert "Emerging Trends" in remaining


def test_mrkdwn_to_html_fragment_converts_headings_and_links():
    remaining = email_client._strip_section(SAMPLE_DIGEST, "Key Deals & Funding")
    html_out = email_client._mrkdwn_to_html_fragment(remaining)
    assert "<h3" in html_out
    assert "Emerging Trends" in html_out
    assert '<a href="https://example.com/b">MENAbytes</a>' in html_out
    assert "<li" in html_out


def test_build_html_body_includes_table_and_prose():
    html_out = email_client._build_html_body(SAMPLE_DIGEST, SAMPLE_DEALS)
    assert "Fincart" in html_out
    assert "Emerging Trends" in html_out
    assert "Fincart raised a $2.8M seed round" not in html_out  # dropped from prose, now only in table


@pytest.mark.asyncio
async def test_send_digest_email_sends_html_and_text_body():
    mock_client = AsyncMock()
    mock_client.outbound.send = AsyncMock()

    with patch.object(email_client, "_client", mock_client), \
         patch.object(email_client.settings, "digest_email_recipients", "a@example.com"), \
         patch.object(email_client.settings, "digest_email_sender", "digest@example.com"):

        sent = await email_client.send_digest_email("Subject", SAMPLE_DIGEST, SAMPLE_DEALS)

    assert sent == 1
    call_kwargs = mock_client.outbound.send.await_args.args[0]
    assert "HtmlBody" in call_kwargs
    assert "TextBody" in call_kwargs
    assert "Fincart" in call_kwargs["HtmlBody"]


@pytest.mark.asyncio
async def test_send_digest_email_skips_when_not_configured():
    with patch.object(email_client, "_client", None):
        sent = await email_client.send_digest_email("Subject", SAMPLE_DIGEST, SAMPLE_DEALS)
    assert sent == 0


@pytest.mark.asyncio
async def test_send_digest_email_defaults_deals_to_empty_list():
    mock_client = AsyncMock()
    mock_client.outbound.send = AsyncMock()

    with patch.object(email_client, "_client", mock_client), \
         patch.object(email_client.settings, "digest_email_recipients", "a@example.com"), \
         patch.object(email_client.settings, "digest_email_sender", "digest@example.com"):

        sent = await email_client.send_digest_email("Subject", SAMPLE_DIGEST)  # deals omitted

    assert sent == 1
