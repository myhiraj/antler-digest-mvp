import logging

from slack_sdk.web.async_client import AsyncWebClient
from slack_sdk.signature import SignatureVerifier
from slack_sdk.errors import SlackApiError

from app.config import settings

logger = logging.getLogger(__name__)

_client = AsyncWebClient(token=settings.slack_bot_token)
_verifier = SignatureVerifier(signing_secret=settings.slack_signing_secret)


def verify_request(body: bytes, timestamp: str, signature: str) -> bool:
    if not settings.slack_signing_secret:
        logger.warning("verify_request: SLACK_SIGNING_SECRET not set, rejecting request")
        return False
    return _verifier.is_valid(body=body, timestamp=timestamp, signature=signature)


async def send_dm(slack_user_id: str, text: str) -> bool:
    """Send a DM to a user. Slack opens the DM channel automatically when
    chat.postMessage is called with a user ID. Returns False on failure
    rather than raising, so one bad user ID doesn't stop digest delivery
    to everyone else."""
    try:
        await _client.chat_postMessage(channel=slack_user_id, text=text)
        return True
    except SlackApiError:
        logger.exception("send_dm: failed to message slack_user_id=%r", slack_user_id)
        return False


async def set_home_tab(slack_user_id: str, topic_ids: list[str]) -> None:
    """Publish a friendly App Home view so a user who clicks into the bot
    sees their subscription status instead of Slack's default 'this app
    doesn't accept DMs' placeholder."""
    if topic_ids:
        topics_text = ", ".join(f"`{t}`" for t in topic_ids)
        status_line = f"You're subscribed to: {topics_text}"
    else:
        status_line = "You're not subscribed to any digests yet."

    view = {
        "type": "home",
        "blocks": [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        "*Antler Digest*\n"
                        "Daily VC & startup intelligence, delivered here.\n\n"
                        f"{status_line}"
                    ),
                },
            },
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": (
                            "Use `/subscribe menap_general`, `/subscribe global_vc`, "
                            "or `/subscribe` for both. `/unsubscribe` works the same way."
                        ),
                    }
                ],
            },
        ],
    }

    try:
        await _client.views_publish(user_id=slack_user_id, view=view)
    except SlackApiError:
        logger.exception("set_home_tab: failed to publish view for slack_user_id=%r", slack_user_id)
