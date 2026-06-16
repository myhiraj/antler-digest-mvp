import logging
from contextlib import asynccontextmanager

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI

from app.routes.inbound import router as inbound_router
from app.jobs.rss_poller import poll_rss_feeds

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()


@asynccontextmanager
async def lifespan(app: FastAPI):
    scheduler.add_job(poll_rss_feeds, "interval", hours=6, id="rss_poller")
    scheduler.start()
    logger.info("Scheduler started")
    yield
    scheduler.shutdown()
    logger.info("Scheduler stopped")


app = FastAPI(title="VC Digest Ingestion", lifespan=lifespan)
app.include_router(inbound_router)


@app.get("/health")
async def health():
    return {"status": "ok"}
