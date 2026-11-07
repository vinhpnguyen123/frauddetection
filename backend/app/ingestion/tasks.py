"""Celery application and the thin task around app.ingestion.pipeline."""

import asyncio
from typing import Any
from uuid import UUID

from celery import Celery, Task

from app import db
from app.config import get_settings
from app.embedder import http_embedder
from app.ingestion.pipeline import VersionMeta, run_job

BACKOFF_SECONDS = 10
MAX_DELIVERIES = 7

celery_app = Celery("frauddetection", broker=get_settings().redis_url)


async def run_attempt(job_id: str, meta: dict[str, Any]) -> bool:
    embedder = http_embedder()
    try:
        return await run_job(
            UUID(job_id),
            VersionMeta(**meta),
            sessions=db.get_sessionmaker(),
            embedder=embedder,
            storage_dir=get_settings().storage_dir,
        )
    finally:
        await embedder.client.aclose()
        await db.close()  # pooled connections belong to this event loop, which is about to end


# acks_late + reject_on_worker_lost: a job whose worker dies is delivered again, not lost.
# Job attempts are limited by ingestion_jobs.max_attempts. max_retries bounds the deliveries,
# and its backoff outlasts STALE_AFTER, so a job left running by a lost database gets claimed.
# Celery ships no type information, hence the ignore.
@celery_app.task(  # type: ignore[untyped-decorator]
    bind=True, acks_late=True, reject_on_worker_lost=True, max_retries=MAX_DELIVERIES
)
def ingest_document(self: Task, job_id: str, meta: dict[str, Any]) -> None:
    countdown = BACKOFF_SECONDS * 2**self.request.retries
    try:
        retry = asyncio.run(run_attempt(job_id, meta))
    except Exception as error:  # the job row cannot record this, so only a retry can help
        raise self.retry(countdown=countdown, exc=error) from error
    if retry:
        raise self.retry(countdown=countdown)
