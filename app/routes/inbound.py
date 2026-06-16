from fastapi import APIRouter, Request, HTTPException, BackgroundTasks
from app.services.cleaner import clean_email
from app.services.document_store import document_exists, save_document, save_chunks
from app.services.chunker import chunk_text
from app.services.embedder import embed_chunks
from app.models.document import Document
from app.config import settings
import hashlib
import logging
from datetime import datetime, timezone

router = APIRouter()
logger = logging.getLogger(__name__)

TOPIC_MAP = {
    "hello@digitaldigest.me": "menap_general",
    "newsletter@wamda.com": "menap_general",
    "digest@strictlyvc.com": "global_vc",
    "termsheet@fortune.com": "global_vc",
}


def resolve_topic(sender: str) -> str:
    lower = sender.lower()
    for key, topic_id in TOPIC_MAP.items():
        if key in lower:
            return topic_id
    return "general"


async def process_document(doc: Document) -> None:
    chunks = chunk_text(doc)
    chunks = embed_chunks(chunks)
    await save_chunks(chunks)


@router.post("/inbound")
async def receive_email(request: Request, background_tasks: BackgroundTasks, token: str = ""):
    if token != settings.postmark_webhook_token:
        raise HTTPException(status_code=401, detail="Unauthorised")

    try:
        data = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    raw_text = data.get("TextBody") or data.get("HtmlBody", "")
    subject = data.get("Subject", "")
    sender = data.get("From", "")
    received_at = datetime.now(timezone.utc)

    if not raw_text:
        logger.warning(f"Empty body from {sender}, skipping")
        return {"status": "skipped", "reason": "empty body"}

    content_hash = hashlib.sha256(raw_text.encode()).hexdigest()
    if await document_exists(content_hash):
        logger.info(f"Duplicate from {sender}, skipping")
        return {"status": "skipped", "reason": "duplicate"}

    clean_text = clean_email(raw_text)
    doc = Document(
        source=sender,
        source_type="email",
        topic_id=resolve_topic(sender),
        raw_text=raw_text,
        clean_text=clean_text,
        content_hash=content_hash,
        ingested_at=received_at,
        published_at=received_at,
    )

    await save_document(doc)
    background_tasks.add_task(process_document, doc)

    logger.info(f"Ingested email from {sender}: {subject}")
    return {"status": "ok"}
