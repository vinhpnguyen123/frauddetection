"""The Celery wrapper. The job itself is tested in tests/integration/test_pipeline.py."""

from typing import Any

import pytest
from celery.exceptions import Retry

from app.ingestion import tasks
from app.ingestion.pipeline import STALE_AFTER, JobBusy

META = {"source_url": None, "published_date": None, "status": "active", "authority": "advisory"}
JOB = "00000000-0000-0000-0000-000000000001"


def use_result(monkeypatch: pytest.MonkeyPatch, retry: bool) -> None:
    async def fake(job_id: str, meta: dict[str, Any]) -> bool:
        return retry

    monkeypatch.setattr(tasks, "run_attempt", fake)


def test_a_finished_attempt_ends_the_task(monkeypatch: pytest.MonkeyPatch) -> None:
    use_result(monkeypatch, retry=False)
    assert tasks.ingest_document.apply(args=[JOB, META]).state == "SUCCESS"


def test_a_failed_attempt_is_retried_with_backoff(monkeypatch: pytest.MonkeyPatch) -> None:
    use_result(monkeypatch, retry=True)
    seen: list[int] = []

    def fake_retry(countdown: int, exc: Exception | None = None) -> Retry:
        seen.append(countdown)
        return Retry()

    monkeypatch.setattr(tasks.ingest_document, "retry", fake_retry)
    with pytest.raises(Retry):
        tasks.ingest_document.run(JOB, META)
    assert seen == [tasks.BACKOFF_SECONDS]


@pytest.mark.parametrize(
    "error", [ConnectionRefusedError("postgres down"), JobBusy("job is running")]
)
def test_an_error_outside_the_job_is_retried(
    monkeypatch: pytest.MonkeyPatch, error: Exception
) -> None:
    """Regression: a database failure ended the task with the job stuck and no delivery left."""

    async def fail(job_id: str, meta: dict[str, Any]) -> bool:
        raise error

    monkeypatch.setattr(tasks, "run_attempt", fail)
    seen: list[Exception | None] = []

    def fake_retry(countdown: int, exc: Exception | None = None) -> Retry:
        seen.append(exc)
        return Retry()

    monkeypatch.setattr(tasks.ingest_document, "retry", fake_retry)
    with pytest.raises(Retry):
        tasks.ingest_document.run(JOB, META)
    assert seen == [error]


def test_retries_are_bounded_and_outlast_a_stale_claim() -> None:
    limit = tasks.ingest_document.max_retries
    assert limit is not None
    waited = sum(tasks.BACKOFF_SECONDS * 2**retry for retry in range(limit))
    assert waited > STALE_AFTER.total_seconds()


def test_a_lost_worker_does_not_lose_the_job() -> None:
    assert tasks.ingest_document.acks_late is True
    assert tasks.ingest_document.reject_on_worker_lost is True
