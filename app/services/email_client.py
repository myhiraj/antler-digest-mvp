import logging
import re

from postmark import ServerClient
from postmark.exceptions import PostmarkException

from app.config import settings

logger = logging.getLogger(__name__)

_client = ServerClient(server_token=settings.postmark_server_token) if settings.postmark_server_token else None

_SLACK_LINK_RE = re.compile(r"<(https?://[^|>]+)\|([^>]+)>")


def _to_plain_text(slack_mrkdwn: str) -> str:
    """Turn Slack mrkdwn into a readable plain-text email body: resolve
    <url|label> links to 'label (url)' and drop single-asterisk/underscore
    emphasis markers, which read as clutter outside Slack."""
    text = _SLACK_LINK_RE.sub(r"\2 (\1)", slack_mrkdwn)
    text = re.sub(r"(?<!\*)\*(?!\*)([^*\n]+)\*(?!\*)", r"\1", text)
    text = re.sub(r"(?<!_)_(?!_)([^_\n]+)_(?!_)", r"\1", text)
    return text


async def send_digest_email(subject: str, summary_text: str) -> int:
    """Send the plain-text digest to every configured recipient. Returns
    the number of successful sends; a failure for one recipient does not
    stop delivery to the rest."""
    recipients = settings.digest_email_recipient_list
    if not _client or not recipients or not settings.digest_email_sender:
        logger.info("send_digest_email: email delivery not configured, skipping")
        return 0

    body = _to_plain_text(summary_text)
    sent = 0
    for recipient in recipients:
        try:
            await _client.outbound.send(
                {
                    "From": settings.digest_email_sender,
                    "To": recipient,
                    "Subject": subject,
                    "TextBody": body,
                }
            )
            sent += 1
        except PostmarkException:
            logger.exception("send_digest_email: failed to send to recipient=%r", recipient)
    return sent
