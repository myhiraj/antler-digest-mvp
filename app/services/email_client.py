import html
import logging
import re
from typing import Any, Dict, List

from postmark import ServerClient
from postmark.exceptions import PostmarkException

from app.config import settings

logger = logging.getLogger(__name__)

_client = ServerClient(server_token=settings.postmark_server_token) if settings.postmark_server_token else None

_SLACK_LINK_RE = re.compile(r"<(https?://[^|>]+)\|([^>]+)>")

_TABLE_COLUMNS = ["Company", "Country", "Round", "Amount", "Investors", "Source"]


def _to_plain_text(slack_mrkdwn: str) -> str:
    """Turn Slack mrkdwn into a readable plain-text fallback body: resolve
    <url|label> links to 'label (url)' and drop single-asterisk/underscore
    emphasis markers, which read as clutter outside Slack."""
    text = _SLACK_LINK_RE.sub(r"\2 (\1)", slack_mrkdwn)
    text = re.sub(r"(?<!\*)\*(?!\*)([^*\n]+)\*(?!\*)", r"\1", text)
    text = re.sub(r"(?<!_)_(?!_)([^_\n]+)_(?!_)", r"\1", text)
    return text


def _strip_section(slack_mrkdwn: str, heading: str) -> str:
    """Remove the *Key Deals & Funding* section (now rendered as a table)
    from the mrkdwn body before converting the rest to HTML prose."""
    pattern = re.compile(
        rf"\*{re.escape(heading)}\*.*?(?=\n\*[^*\n]+\*|\Z)", re.DOTALL
    )
    return pattern.sub("", slack_mrkdwn)


def _mrkdwn_to_html_fragment(slack_mrkdwn: str) -> str:
    """Render the remaining (non-tabular) sections as simple styled HTML:
    bold section headings, resolved links, bullet lists."""
    lines = slack_mrkdwn.strip().splitlines()
    html_parts = []
    in_list = False

    def close_list():
        nonlocal in_list
        if in_list:
            html_parts.append("</ul>")
            in_list = False

    for raw_line in lines:
        line = raw_line.strip()
        if not line:
            close_list()
            continue

        line = _SLACK_LINK_RE.sub(
            lambda m: f'<a href="{html.escape(m.group(1))}">{html.escape(m.group(2))}</a>',
            line,
        )

        heading_match = re.fullmatch(r"\*([^*]+)\*", line)
        if heading_match:
            close_list()
            html_parts.append(
                f'<h3 style="margin:20px 0 8px;font-size:15px;color:#1a1a1a;">{html.escape(heading_match.group(1))}</h3>'
            )
            continue

        line = re.sub(r"(?<!\*)\*(?!\*)([^*\n]+)\*(?!\*)", r"<b>\1</b>", line)
        line = re.sub(r"(?<!_)_(?!_)([^_\n]+)_(?!_)", r"<i>\1</i>", line)

        if line.startswith("- "):
            if not in_list:
                html_parts.append('<ul style="margin:4px 0;padding-left:20px;">')
                in_list = True
            html_parts.append(f'<li style="margin:4px 0;line-height:1.5;">{line[2:]}</li>')
        else:
            close_list()
            html_parts.append(f'<p style="margin:8px 0;line-height:1.5;">{line}</p>')

    close_list()
    return "\n".join(html_parts)


def _deals_table_html(deals: List[Dict[str, Any]]) -> str:
    if not deals:
        return ""

    header_cells = "".join(
        f'<th style="text-align:left;padding:8px 10px;border-bottom:2px solid #ddd;font-size:12px;'
        f'text-transform:uppercase;color:#666;">{col}</th>'
        for col in _TABLE_COLUMNS
    )

    rows = []
    for deal in deals:
        company = html.escape(deal.get("company") or "—")
        country = html.escape(deal.get("country") or "—")
        round_ = html.escape(deal.get("round") or "—")
        amount = html.escape(deal.get("amount") or "—")
        investors = html.escape(deal.get("investors") or "—")
        source_url = deal.get("source_url")
        source_name = html.escape(deal.get("source_name") or "Source")
        source_cell = (
            f'<a href="{html.escape(source_url)}">{source_name}</a>' if source_url else "—"
        )
        rows.append(
            "<tr>"
            f'<td style="padding:8px 10px;border-bottom:1px solid #eee;">{company}</td>'
            f'<td style="padding:8px 10px;border-bottom:1px solid #eee;">{country}</td>'
            f'<td style="padding:8px 10px;border-bottom:1px solid #eee;">{round_}</td>'
            f'<td style="padding:8px 10px;border-bottom:1px solid #eee;">{amount}</td>'
            f'<td style="padding:8px 10px;border-bottom:1px solid #eee;">{investors}</td>'
            f'<td style="padding:8px 10px;border-bottom:1px solid #eee;">{source_cell}</td>'
            "</tr>"
        )

    return (
        '<h3 style="margin:20px 0 8px;font-size:15px;color:#1a1a1a;">Key Deals &amp; Funding</h3>'
        '<table style="width:100%;border-collapse:collapse;font-size:13px;">'
        f"<thead><tr>{header_cells}</tr></thead>"
        f"<tbody>{''.join(rows)}</tbody>"
        "</table>"
    )


def _build_html_body(summary_text: str, deals: List[Dict[str, Any]]) -> str:
    table_html = _deals_table_html(deals)
    remaining_mrkdwn = _strip_section(summary_text, "Key Deals & Funding")
    prose_html = _mrkdwn_to_html_fragment(remaining_mrkdwn)

    return (
        '<div style="font-family:-apple-system,Helvetica,Arial,sans-serif;color:#1a1a1a;max-width:640px;">'
        f"{table_html}{prose_html}"
        "</div>"
    )


async def send_digest_email(subject: str, summary_text: str, deals: List[Dict[str, Any]] = None) -> int:
    """Send the digest to every configured recipient as an HTML email — a
    table for Key Deals & Funding, styled prose for the remaining sections —
    with a plain-text fallback. Returns the number of successful sends; a
    failure for one recipient does not stop delivery to the rest."""
    recipients = settings.digest_email_recipient_list
    if not _client or not recipients or not settings.digest_email_sender:
        logger.info("send_digest_email: email delivery not configured, skipping")
        return 0

    html_body = _build_html_body(summary_text, deals or [])
    text_body = _to_plain_text(summary_text)
    sent = 0
    for recipient in recipients:
        try:
            await _client.outbound.send(
                {
                    "From": settings.digest_email_sender,
                    "To": recipient,
                    "Subject": subject,
                    "HtmlBody": html_body,
                    "TextBody": text_body,
                }
            )
            sent += 1
        except PostmarkException:
            logger.exception("send_digest_email: failed to send to recipient=%r", recipient)
    return sent
