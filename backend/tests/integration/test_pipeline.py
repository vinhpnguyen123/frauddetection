"""The ingestion pipeline on the real database, with a fake embedder and tiny PDFs."""

import hashlib
from collections.abc import AsyncIterator
from datetime import timedelta
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from scripts.render_synthetic import render_pdf
from sqlalchemy import func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.embedder import EMBED_DIMENSIONS
from app.ingestion import pipeline
from app.ingestion.pipeline import (
    STALE_AFTER,
    IngestItem,
    JobBusy,
    VersionMeta,
    claim,
    record_failure,
    register,
    run_job,
)
from app.models import Chunk, Document, DocumentVersion, IngestionJob, Section, Tenant
from app.retrieval.fts import FtsRetriever
from app.retrieval.protocols import RetrievalContext

Sessions = async_sessionmaker[AsyncSession]
META = VersionMeta("https://example.test/a.pdf", "2024-05-01", "active", "advisory")
POLICY = VersionMeta(None, None, "active", "internal_policy")


class FakeEmbedder:
    def __init__(self, failures: int = 0) -> None:
        self.failures = failures
        self.calls = 0

    async def count_tokens(self, texts: list[str]) -> list[int]:
        return [len(item.split()) for item in texts]

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        self.calls += 1
        if self.failures:
            self.failures -= 1
            raise ConnectionError("embedder down")
        return [[0.1] * EMBED_DIMENSIONS for _ in texts]


@pytest.fixture
async def sessions(test_database_url: str) -> AsyncIterator[Sessions]:
    """Real commits, because the pipeline manages its own transactions."""
    engine = create_async_engine(test_database_url, poolclass=NullPool)
    yield async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.execute(
            text("TRUNCATE tenants, documents, document_versions, ingestion_jobs CASCADE")
        )
    await engine.dispose()


FILLER = "Records stay available for review. " * 8  # above the parser's text density floor


def pdf(words: str) -> bytes:
    return render_pdf(f"# Title\n\n## Scope\n\n{words}\n\n## Records\n\n{FILLER}")


def item_for(
    storage: Path, content: bytes, *, tenant: UUID | None = None, key: str = "doc"
) -> IngestItem:
    item = IngestItem(
        doc_key=key,
        title="A document",
        source="fincen",
        collections=("fraud_typologies",),
        tenant_id=tenant,
        scope=str(tenant) if tenant else "public",
        content_hash=hashlib.sha256(content).hexdigest(),
    )
    target = storage / item.storage_key
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(content)
    return item


async def enqueue(sessions: Sessions, item: IngestItem) -> tuple[UUID, bool]:
    async with sessions.begin() as session:
        return await register(session, item)


async def ingest(
    sessions: Sessions,
    storage: Path,
    item: IngestItem,
    embedder: FakeEmbedder | None = None,
    meta: VersionMeta = META,
) -> UUID:
    job_id, _ = await enqueue(sessions, item)
    await run_job(
        job_id, meta, sessions=sessions, embedder=embedder or FakeEmbedder(), storage_dir=storage
    )
    return job_id


async def count(sessions: Sessions, model: type) -> int:
    async with sessions() as session:
        return (await session.scalar(select(func.count()).select_from(model))) or 0


async def job(sessions: Sessions, job_id: UUID) -> IngestionJob:
    async with sessions() as session:
        found = await session.get(IngestionJob, job_id)
    assert found is not None
    return found


async def set_job(
    sessions: Sessions, job_id: UUID, *, stale: bool = False, **values: object
) -> None:
    async with sessions.begin() as session:
        if values:
            await session.execute(
                update(IngestionJob).where(IngestionJob.id == job_id).values(**values)
            )
        if stale:
            age = STALE_AFTER + timedelta(seconds=1)
            await session.execute(
                update(IngestionJob)
                .where(IngestionJob.id == job_id)
                .values(updated_at=func.now() - age)
            )


async def add_tenant(sessions: Sessions, slug: str) -> UUID:
    async with sessions.begin() as session:
        tenant = Tenant(slug=slug, name=slug)
        session.add(tenant)
        await session.flush()
        return tenant.id


async def test_a_job_stores_a_current_version_with_chunks(
    sessions: Sessions, tmp_path: Path
) -> None:
    job_id = await ingest(sessions, tmp_path, item_for(tmp_path, pdf("Wire fraud rule.")))

    finished = await job(sessions, job_id)
    assert (finished.status, finished.attempts, finished.error) == ("succeeded", 1, None)
    async with sessions() as session:
        document = await session.scalar(select(Document))
        version = await session.scalar(select(DocumentVersion))
        chunks = (await session.scalars(select(Chunk).order_by(Chunk.ordinal))).all()
        sections = (await session.scalars(select(Section))).all()
    assert document is not None and version is not None
    assert document.current_version_id == version.id == finished.version_id
    assert (version.version_no, version.is_current, version.page_count) == (1, True, 1)
    assert str(version.published_date) == "2024-05-01"
    assert chunks and len(sections) >= 2
    assert {section.id for section in sections} >= {chunk.section_id for chunk in chunks}
    for chunk in chunks:
        assert chunk.is_current and chunk.access_level == "public" and chunk.tenant_id is None
        assert chunk.spans and chunk.spans[0]["page"] == 1 and len(chunk.spans[0]["bbox"]) == 4
        assert len(chunk.embedding) == EMBED_DIMENSIONS


async def test_running_again_creates_nothing(sessions: Sessions, tmp_path: Path) -> None:
    item = item_for(tmp_path, pdf("Wire fraud rule."))
    job_id = await ingest(sessions, tmp_path, item)
    before = await count(sessions, Chunk)

    _, needs_run = await enqueue(sessions, item)
    embedder = FakeEmbedder()
    await run_job(job_id, META, sessions=sessions, embedder=embedder, storage_dir=tmp_path)

    assert needs_run is False
    assert embedder.calls == 0
    assert await count(sessions, IngestionJob) == 1
    assert await count(sessions, DocumentVersion) == 1
    assert await count(sessions, Chunk) == before


async def test_a_redelivered_task_after_success_adds_no_version(
    sessions: Sessions, tmp_path: Path
) -> None:
    item = item_for(tmp_path, pdf("Wire fraud rule."))
    job_id = await ingest(sessions, tmp_path, item)
    # The worker died after the commit but before the ack, long enough ago to look lost.
    await set_job(sessions, job_id, status="running", stale=True)

    await run_job(job_id, META, sessions=sessions, embedder=FakeEmbedder(), storage_dir=tmp_path)

    assert await count(sessions, DocumentVersion) == 1
    assert (await job(sessions, job_id)).status == "succeeded"


async def test_changed_bytes_make_a_new_current_version(sessions: Sessions, tmp_path: Path) -> None:
    await ingest(sessions, tmp_path, item_for(tmp_path, pdf("Old rule text.")))
    await ingest(sessions, tmp_path, item_for(tmp_path, pdf("New rule text.")))

    async with sessions() as session:
        versions = (
            await session.scalars(select(DocumentVersion).order_by(DocumentVersion.version_no))
        ).all()
        document = await session.scalar(select(Document))
        current = (await session.scalars(select(Chunk).where(Chunk.is_current))).all()
        old = (await session.scalars(select(Chunk).where(Chunk.is_current.is_(False)))).all()
    assert [(v.version_no, v.is_current) for v in versions] == [(1, False), (2, True)]
    assert document is not None and document.current_version_id == versions[1].id
    assert current and all(chunk.version_id == versions[1].id for chunk in current)
    assert old and all(chunk.version_id == versions[0].id for chunk in old)
    assert await count(sessions, Document) == 1


async def current_text(sessions: Sessions) -> str:
    async with sessions() as session:
        chunks = (await session.scalars(select(Chunk.text).where(Chunk.is_current))).all()
    return " ".join(chunks)


async def test_an_older_job_finishing_late_does_not_replace_newer_content(
    sessions: Sessions, tmp_path: Path
) -> None:
    """Regression: a retried job from an old file made obsolete text current again."""
    old_job, _ = await enqueue(sessions, item_for(tmp_path, pdf("Old rule text.")))
    new_job, _ = await enqueue(sessions, item_for(tmp_path, pdf("New rule text.")))

    await run_job(new_job, META, sessions=sessions, embedder=FakeEmbedder(), storage_dir=tmp_path)
    await run_job(old_job, META, sessions=sessions, embedder=FakeEmbedder(), storage_dir=tmp_path)

    assert (await job(sessions, old_job)).status == "succeeded"
    assert await count(sessions, DocumentVersion) == 2  # the old version is kept, not current
    text_now = await current_text(sessions)
    assert "New rule text" in text_now and "Old rule text" not in text_now
    async with sessions() as session:
        document = await session.scalar(select(Document))
        current = (
            await session.scalars(select(DocumentVersion).where(DocumentVersion.is_current))
        ).all()
    assert document is not None and [v.id for v in current] == [document.current_version_id]
    assert document.current_version_id == (await job(sessions, new_job)).version_id


async def test_an_older_job_becomes_current_while_the_newer_one_has_failed(
    sessions: Sessions, tmp_path: Path
) -> None:
    old_job, _ = await enqueue(sessions, item_for(tmp_path, pdf("Old rule text.")))
    new_job, _ = await enqueue(sessions, item_for(tmp_path, pdf("New rule text.")))
    await set_job(sessions, new_job, status="failed", attempts=3)

    await run_job(old_job, META, sessions=sessions, embedder=FakeEmbedder(), storage_dir=tmp_path)

    assert "Old rule text" in await current_text(sessions)


async def test_a_broken_extraction_never_replaces_a_good_version(
    sessions: Sessions, tmp_path: Path
) -> None:
    """Regression: a nearly empty scan passed the checks and hid the complete version."""
    await ingest(sessions, tmp_path, item_for(tmp_path, pdf("Complete rule text.")))
    broken = render_pdf("# Title\n\n## Scope\n\nOne readable fragment.")

    job_id = await ingest(sessions, tmp_path, item_for(tmp_path, broken))

    failed = await job(sessions, job_id)
    assert failed.status == "failed" and "low_text_density" in (failed.error or "")
    assert await count(sessions, DocumentVersion) == 1
    assert "Complete rule text" in await current_text(sessions)


async def test_a_failed_embedding_leaves_nothing_and_is_retried(
    sessions: Sessions, tmp_path: Path
) -> None:
    job_id, _ = await enqueue(sessions, item_for(tmp_path, pdf("Wire fraud rule.")))
    retry = await run_job(
        job_id, META, sessions=sessions, embedder=FakeEmbedder(1), storage_dir=tmp_path
    )

    failed = await job(sessions, job_id)
    assert retry is True
    assert (failed.status, failed.attempts) == ("pending", 1)
    assert failed.error == "ConnectionError: embedder down"
    assert await count(sessions, DocumentVersion) == 0
    assert await count(sessions, Chunk) == 0

    assert not await run_job(
        job_id, META, sessions=sessions, embedder=FakeEmbedder(), storage_dir=tmp_path
    )
    done = await job(sessions, job_id)
    assert (done.status, done.attempts, done.error) == ("succeeded", 2, None)


async def test_a_database_error_rolls_the_whole_version_back(
    sessions: Sessions, tmp_path: Path
) -> None:
    """An invalid status fails inside the write transaction, after all the work is done."""
    job_id, _ = await enqueue(sessions, item_for(tmp_path, pdf("Wire fraud rule.")))
    bad = VersionMeta(None, None, "not-a-status", "advisory")

    await run_job(job_id, bad, sessions=sessions, embedder=FakeEmbedder(), storage_dir=tmp_path)

    assert (await job(sessions, job_id)).status == "pending"
    assert await count(sessions, DocumentVersion) == 0
    assert await count(sessions, Section) == 0
    assert await count(sessions, Chunk) == 0
    error = (await job(sessions, job_id)).error
    assert error is not None and "INSERT" not in error


async def test_a_failure_while_writing_chunks_rolls_back_version_and_sections(
    sessions: Sessions, tmp_path: Path
) -> None:
    """Vectors of the wrong size pass the fake and fail at the chunk insert, the last write."""

    class WrongSize(FakeEmbedder):
        async def embed_documents(self, texts: list[str]) -> list[list[float]]:
            return [[0.1, 0.2] for _ in texts]

    job_id, _ = await enqueue(sessions, item_for(tmp_path, pdf("Wire fraud rule.")))

    await run_job(job_id, META, sessions=sessions, embedder=WrongSize(), storage_dir=tmp_path)

    assert (await job(sessions, job_id)).status == "pending"
    assert await count(sessions, DocumentVersion) == 0
    assert await count(sessions, Section) == 0
    assert await count(sessions, Chunk) == 0


async def test_attempts_run_out(sessions: Sessions, tmp_path: Path) -> None:
    job_id, _ = await enqueue(sessions, item_for(tmp_path, pdf("Wire fraud rule.")))
    embedder = FakeEmbedder(failures=3)
    results = [
        await run_job(job_id, META, sessions=sessions, embedder=embedder, storage_dir=tmp_path)
        for _ in range(3)
    ]
    assert results == [True, True, False]
    assert (await job(sessions, job_id)).status == "failed"


async def test_a_failed_job_can_be_enqueued_again(sessions: Sessions, tmp_path: Path) -> None:
    item = item_for(tmp_path, pdf("Wire fraud rule."))
    job_id, _ = await enqueue(sessions, item)
    for _ in range(3):
        await run_job(
            job_id, META, sessions=sessions, embedder=FakeEmbedder(1), storage_dir=tmp_path
        )

    same_job, needs_run = await enqueue(sessions, item)

    assert (same_job, needs_run) == (job_id, True)
    reset = await job(sessions, job_id)
    assert (reset.status, reset.attempts, reset.error) == ("pending", 0, None)


async def test_enqueueing_again_leaves_active_jobs_alone(
    sessions: Sessions, tmp_path: Path
) -> None:
    """Regression: every `make ingest` reset the retry budget and added a delivery."""
    item = item_for(tmp_path, pdf("Wire fraud rule."))
    job_id, first = await enqueue(sessions, item)
    assert first is True

    assert (await enqueue(sessions, item))[1] is False  # queued
    await set_job(sessions, job_id, status="running", attempts=2)
    assert (await enqueue(sessions, item))[1] is False  # running
    await set_job(sessions, job_id, status="pending", attempts=2)
    assert (await enqueue(sessions, item))[1] is False  # waiting for its backoff
    assert (await job(sessions, job_id)).attempts == 2


@pytest.mark.parametrize("status", ["pending", "running"])
async def test_enqueueing_again_rescues_a_lost_job_and_keeps_its_budget(
    sessions: Sessions, tmp_path: Path, status: str
) -> None:
    item = item_for(tmp_path, pdf("Wire fraud rule."))
    job_id, _ = await enqueue(sessions, item)
    await set_job(sessions, job_id, status=status, attempts=2, stale=True)

    _, needs_run = await enqueue(sessions, item)

    rescued = await job(sessions, job_id)
    assert needs_run is True
    assert (rescued.status, rescued.attempts) == ("pending", 2)


async def test_a_second_delivery_cannot_run_a_job_in_progress(
    sessions: Sessions, tmp_path: Path
) -> None:
    job_id, _ = await enqueue(sessions, item_for(tmp_path, pdf("Wire fraud rule.")))
    await set_job(sessions, job_id, status="running", attempts=1)

    with pytest.raises(JobBusy):
        await claim(sessions, job_id)
    assert (await job(sessions, job_id)).attempts == 1


async def test_a_job_out_of_attempts_is_not_run_by_a_late_delivery(
    sessions: Sessions, tmp_path: Path
) -> None:
    job_id, _ = await enqueue(sessions, item_for(tmp_path, pdf("Wire fraud rule.")))
    await set_job(sessions, job_id, status="pending", attempts=3)
    embedder = FakeEmbedder()

    await run_job(job_id, META, sessions=sessions, embedder=embedder, storage_dir=tmp_path)

    assert embedder.calls == 0
    assert (await job(sessions, job_id)).status == "failed"


async def test_a_failed_job_is_not_run_by_a_late_delivery(
    sessions: Sessions, tmp_path: Path
) -> None:
    job_id, _ = await enqueue(sessions, item_for(tmp_path, pdf("Wire fraud rule.")))
    await set_job(sessions, job_id, status="failed", attempts=1)
    assert await claim(sessions, job_id) is None


async def test_an_old_attempt_cannot_overwrite_a_newer_success(
    sessions: Sessions, tmp_path: Path
) -> None:
    """Regression: a slow failed attempt marked a finished job as pending again."""
    job_id, _ = await enqueue(sessions, item_for(tmp_path, pdf("Wire fraud rule.")))
    old = await claim(sessions, job_id)
    assert old is not None
    await set_job(sessions, job_id, stale=True)
    await run_job(job_id, META, sessions=sessions, embedder=FakeEmbedder(), storage_dir=tmp_path)

    await record_failure(sessions, old, ConnectionError("late"), retry=True)

    finished = await job(sessions, job_id)
    assert (finished.status, finished.attempts, finished.error) == ("succeeded", 2, None)


async def test_an_old_attempt_cannot_finish_after_it_lost_the_job(
    sessions: Sessions, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    job_id, _ = await enqueue(sessions, item_for(tmp_path, pdf("Wire fraud rule.")))

    class TakenOver(FakeEmbedder):
        async def embed_documents(self, texts: list[str]) -> list[list[float]]:
            await set_job(sessions, job_id, attempts=2)  # a newer attempt took the job
            return await super().embed_documents(texts)

    retry = await run_job(
        job_id, META, sessions=sessions, embedder=TakenOver(), storage_dir=tmp_path
    )

    assert retry is False
    assert await count(sessions, DocumentVersion) == 0
    assert (await job(sessions, job_id)).status == "running"


async def test_a_lost_database_while_recording_a_failure_reaches_the_task(
    sessions: Sessions, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The task retries it. Later the stale job can be claimed again, within its budget."""
    job_id, _ = await enqueue(sessions, item_for(tmp_path, pdf("Wire fraud rule.")))

    async def no_database(*args: object, **kwargs: object) -> None:
        raise ConnectionError("postgres down")

    monkeypatch.setattr(pipeline, "record_failure", no_database)
    with pytest.raises(ConnectionError):
        await run_job(
            job_id, META, sessions=sessions, embedder=FakeEmbedder(1), storage_dir=tmp_path
        )
    monkeypatch.undo()

    stuck = await job(sessions, job_id)
    assert (stuck.status, stuck.attempts) == ("running", 1)
    with pytest.raises(JobBusy):
        await claim(sessions, job_id)

    await set_job(sessions, job_id, stale=True)
    await run_job(job_id, META, sessions=sessions, embedder=FakeEmbedder(), storage_dir=tmp_path)
    finished = await job(sessions, job_id)
    assert (finished.status, finished.attempts) == ("succeeded", 2)


async def test_a_corrupted_file_fails_without_a_retry(sessions: Sessions, tmp_path: Path) -> None:
    item = item_for(tmp_path, pdf("Wire fraud rule."))
    (tmp_path / item.storage_key).write_bytes(pdf("Tampered text."))
    job_id, _ = await enqueue(sessions, item)

    retry = await run_job(
        job_id, META, sessions=sessions, embedder=FakeEmbedder(), storage_dir=tmp_path
    )

    failed = await job(sessions, job_id)
    assert retry is False
    assert failed.status == "failed" and "does not match" in (failed.error or "")


async def test_a_document_without_text_fails_the_quality_check(
    sessions: Sessions, tmp_path: Path
) -> None:
    job_id, _ = await enqueue(sessions, item_for(tmp_path, render_pdf("12")))

    assert not await run_job(
        job_id, META, sessions=sessions, embedder=FakeEmbedder(), storage_dir=tmp_path
    )

    failed = await job(sessions, job_id)
    assert failed.status == "failed" and "no chunks" in (failed.error or "")
    assert await count(sessions, DocumentVersion) == 0


async def test_same_bytes_under_two_keys_is_refused(sessions: Sessions, tmp_path: Path) -> None:
    content = pdf("Wire fraud rule.")
    await enqueue(sessions, item_for(tmp_path, content, key="first"))
    with pytest.raises(Exception, match="same bytes"):
        await enqueue(sessions, item_for(tmp_path, content, key="second"))


async def test_one_file_can_belong_to_two_tenants(sessions: Sessions, tmp_path: Path) -> None:
    content = pdf("Wire fraud rule.")
    first, second = await add_tenant(sessions, "a"), await add_tenant(sessions, "b")
    await ingest(sessions, tmp_path, item_for(tmp_path, content, tenant=first), meta=POLICY)
    await ingest(sessions, tmp_path, item_for(tmp_path, content, tenant=second), meta=POLICY)
    assert await count(sessions, IngestionJob) == 2
    assert await count(sessions, DocumentVersion) == 2


async def test_a_tenant_never_finds_another_tenants_policy(
    sessions: Sessions, tmp_path: Path
) -> None:
    bluefin, granite = await add_tenant(sessions, "x-bluefin"), await add_tenant(sessions, "x-grn")
    private_a = pdf("Approver is the treasurer. Policy ref AAA-CANARY-1111.")
    private_b = pdf("Approver is the treasurer. Policy ref BBB-CANARY-2222.")
    await ingest(sessions, tmp_path, item_for(tmp_path, private_a, tenant=bluefin), meta=POLICY)
    await ingest(sessions, tmp_path, item_for(tmp_path, private_b, tenant=granite), meta=POLICY)
    await ingest(sessions, tmp_path, item_for(tmp_path, pdf("Treasurer public guidance.")))
    context = RetrievalContext(uuid4(), bluefin, frozenset({"public", "tenant_private"}))

    hits = await FtsRetriever(sessions).search("treasurer", context=context, limit=10)

    async with sessions() as session:
        found = (
            await session.scalars(select(Chunk).where(Chunk.id.in_(h.chunk_id for h in hits)))
        ).all()
    texts = " ".join(chunk.text for chunk in found)
    assert "AAA-CANARY-1111" in texts
    assert "Treasurer public guidance" in texts
    assert "BBB-CANARY-2222" not in texts
    assert {chunk.tenant_id for chunk in found} == {bluefin, None}
