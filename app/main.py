import logging
from contextlib import asynccontextmanager

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI

from app.routes.inbound import router as inbound_router
from app.routes.slack import router as slack_router
from app.jobs.rss_poller import poll_rss_feeds
from app.jobs.digest_job import generate_daily_digest

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()


@asynccontextmanager
async def lifespan(app: FastAPI):
    scheduler.add_job(poll_rss_feeds, "cron", hour=7, minute=5, timezone="UTC", id="rss_poller")
    scheduler.add_job(generate_daily_digest, "cron", hour=8, minute=10, timezone="UTC", id="daily_digest")
    scheduler.start()
    logger.info("Scheduler started")
    yield
    scheduler.shutdown()
    logger.info("Scheduler stopped")


app = FastAPI(title="VC Digest Ingestion", lifespan=lifespan)
app.include_router(inbound_router)
app.include_router(slack_router)


@app.get("/health")
async def health():
    return {"status": "ok"}
