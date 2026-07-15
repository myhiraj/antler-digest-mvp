import logging

from fastapi import APIRouter, Request, HTTPException

from app.jobs.digest_job import TOPIC_IDS
from app.services.document_store import add_subscription, remove_subscription
from app.services.slack_client import verify_request, set_home_tab

router = APIRouter()
logger = logging.getLogger(__name__)


def _resolve_topics(arg: str) -> list[str]:
    arg = arg.strip()
    if not arg:
        return TOPIC_IDS
    if arg in TOPIC_IDS:
        return [arg]
    return []


@router.post("/slack/commands")
async def handle_slash_command(request: Request):
    body = await request.body()
    timestamp = request.headers.get("X-Slack-Request-Timestamp", "")
    signature = request.headers.get("X-Slack-Signature", "")

    if not verify_request(body, timestamp, signature):
        raise HTTPException(status_code=401, detail="Invalid Slack signature")

    form = await request.form()
    command = form.get("command", "")
    text = form.get("text", "")
    user_id = form.get("user_id", "")

    if not user_id:
        raise HTTPException(status_code=400, detail="Missing user_id")

    topics = _resolve_topics(text)
    if not topics:
        return {
            "response_type": "ephemeral",
            "text": f"Unknown topic {text!r}. Valid topics: {', '.join(TOPIC_IDS)}.",
        }

    if command == "/subscribe":
        subscriber = await add_subscription(user_id, topics)
    elif command == "/unsubscribe":
        subscriber = await remove_subscription(user_id, topics)
    else:
        raise HTTPException(status_code=400, detail=f"Unknown command {command!r}")

    await set_home_tab(user_id, subscriber.topic_ids)

    if subscriber.topic_ids:
        topics_text = ", ".join(f"`{t}`" for t in subscriber.topic_ids)
        reply = f"You're now subscribed to: {topics_text}"
    else:
        reply = "You're unsubscribed from all digests."

    return {"response_type": "ephemeral", "text": reply}
