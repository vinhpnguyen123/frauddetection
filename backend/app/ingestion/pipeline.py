"""One ingestion job, from a stored PDF to searchable chunks. See docs/ARCHITECTURE.md §3.

Independent of Celery, so the whole path runs in tests against the real database. Everything a
job writes lands in one transaction: a reader sees all of a version or none of it.
"""

import hashlib
import logging
from dataclasses import asdict, dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Protocol
from uuid import UUID

from sqlalchemy import ColumnElement, and_, func, insert, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.ingestion.chunk import MAX_TOKENS, Chunk, chunk_document
from app.ingestion.parse import ParsedDocument, parse_pdf
from app.models import Chunk as ChunkRow
from app.models import Document, DocumentVersion, IngestionJob
from app.models import Section as SectionRow

logger = logging.getLogger(__name__)

MAX_ERROR_CHARS = 500
# A job untouched for this long has lost its worker or its message. Well above the slowest
# document, and a wrong guess is safe: attempts fence off the older run.
STALE_AFTER = timedelta(minutes=10)


class IngestionFailed(Exception):
    """A failure that a retry cannot fix, such as a corrupt file or a broken document."""


class JobBusy(Exception):
    """Another delivery is running this job. The task tries again later."""


class StaleAttempt(Exception):
    """A newer attempt took this job, so this one must not record anything."""


class IngestEmbedder(Protocol):
    async def count_tokens(self, texts: list[str]) -> list[int]: ...

    async def embed_documents(self, texts: list[str]) -> list[list[float]]: ...


@dataclass(frozen=True)
class VersionMeta:
    """What the job row does not hold. It travels with the task, as plain JSON."""

    source_url: str | None
    published_date: str | None  # ISO date
    status: str
    authority: str

    def as_task_argument(self) -> dict[str, str | None]:
        return asdict(self)


@dataclass(frozen=True)
class IngestItem:
    doc_key: str
    title: str
    source: str
    collections: tuple[str, ...]
    tenant_id: UUID | None
    scope: str  # 'public' or the tenant slug
    content_hash: str

    @property
    def storage_key(self) -> str:
        return f"{self.scope}/{self.doc_key}/{self.content_hash}.pdf"


@dataclass(frozen=True)
class ClaimedJob:
    id: UUID
    tenant_id: UUID | None
    doc_key: str
    content_hash: str
    storage_key: str
    attempts: int
    max_attempts: int


def is_stale() -> ColumnElement[bool]:
    return func.now() - IngestionJob.updated_at > STALE_AFTER


async def register(session: AsyncSession, item: IngestItem) -> tuple[UUID, bool]:
    """Create the document and job if new. Returns the job id and whether to send a task.

    Idempotent on (tenant_id, content_hash). A task is sent for a new job, for a failed job,
    which also gets a fresh retry budget because running this is the explicit retry, and for
    a job that went stale, which keeps its budget. An active job already has its delivery.
    """
    await session.execute(
        pg_insert(Document)
        .values(
            doc_key=item.doc_key,
            title=item.title,
            source=item.source,
            collections=list(item.collections),
            tenant_id=item.tenant_id,
            access_level="tenant_private" if item.tenant_id else "public",
        )
        .on_conflict_do_nothing(constraint="documents_key_unique")
    )
    new_id: UUID | None = await session.scalar(
        pg_insert(IngestionJob)
        .values(
            tenant_id=item.tenant_id,
            source="manifest",
            doc_key=item.doc_key,
            content_hash=item.content_hash,
            storage_key=item.storage_key,
        )
        .on_conflict_do_nothing(constraint="jobs_idempotent")
        .returning(IngestionJob.id)
    )
    found = (
        await session.execute(
            select(IngestionJob, is_stale())
            .where(
                IngestionJob.tenant_id.is_not_distinct_from(item.tenant_id),
                IngestionJob.content_hash == item.content_hash,
            )
            .with_for_update(of=IngestionJob)
        )
    ).first()
    if found is None:
        raise AssertionError("unreachable: the job was just inserted")
    job, stale = found
    if job.doc_key != item.doc_key:
        raise IngestionFailed(f"{item.doc_key} has the same bytes as {job.doc_key}")
    if new_id is not None:
        return job.id, True
    if job.status == "failed":
        job.status, job.attempts, job.error, job.updated_at = "pending", 0, None, func.now()
        return job.id, True
    if job.status != "succeeded" and stale:
        job.status, job.updated_at = "pending", func.now()
        return job.id, True
    return job.id, False


async def claim(sessions: async_sessionmaker[AsyncSession], job_id: UUID) -> ClaimedJob | None:
    """Mark the job as running. Returns None if there is nothing left to do.

    Raises JobBusy while another delivery holds the job. Each claim gets its own attempt
    number, which is what proves ownership when the attempt records its outcome.
    """
    async with sessions.begin() as session:
        found = (
            await session.execute(
                select(IngestionJob, is_stale())
                .where(IngestionJob.id == job_id)
                .with_for_update(of=IngestionJob)
            )
        ).first()
        if found is None:
            return None
        job, stale = found
        if job.status in {"succeeded", "failed"}:
            return None
        if job.status == "running" and not stale:
            raise JobBusy(f"job {job_id} is running")
        if job.attempts >= job.max_attempts:
            job.status, job.updated_at = "failed", func.now()
            job.error = job.error or "out of attempts"
            return None
        job.status, job.attempts, job.updated_at = "running", job.attempts + 1, func.now()
        return ClaimedJob(
            job.id,
            job.tenant_id,
            job.doc_key,
            job.content_hash,
            job.storage_key,
            job.attempts,
            job.max_attempts,
        )


def check_quality(parsed: ParsedDocument, chunks: list[Chunk]) -> None:
    """The per-document checks of docs/DATASET.md §5. Raises instead of storing a bad version."""
    problems = []
    if parsed.page_count == 0:
        problems.append("no pages")
    if not chunks:
        problems.append("no chunks")
    if any(not chunk.text.strip() for chunk in chunks):
        problems.append("empty chunk")
    if any(not chunk.spans for chunk in chunks):
        problems.append("chunk without spans")
    if any(chunk.token_count > MAX_TOKENS for chunk in chunks):
        problems.append("chunk over the token limit")
    if problems:
        raise IngestionFailed("; ".join(problems))


def read_verified(path: Path, content_hash: str) -> None:
    if not path.exists():
        raise IngestionFailed(f"missing file {path.name}")
    if hashlib.sha256(path.read_bytes()).hexdigest() != content_hash:
        raise IngestionFailed(f"file {path.name} does not match its hash")


async def write_version(
    session: AsyncSession,
    job: ClaimedJob,
    meta: VersionMeta,
    parsed: ParsedDocument,
    chunks: list[Chunk],
    vectors: list[list[float]],
) -> UUID:
    """Store a new current version. The document row lock serializes writers of one document."""
    document = await session.scalar(
        select(Document)
        .where(
            Document.tenant_id.is_not_distinct_from(job.tenant_id),
            Document.doc_key == job.doc_key,
        )
        .with_for_update()
    )
    if document is None:
        raise IngestionFailed(f"no document {job.doc_key}")
    existing: UUID | None = await session.scalar(
        select(DocumentVersion.id).where(
            DocumentVersion.document_id == document.id,
            DocumentVersion.content_hash == job.content_hash,
        )
    )
    if existing is not None:
        return existing  # a redelivered task: this version is already stored

    last_no = await session.scalar(
        select(func.max(DocumentVersion.version_no)).where(
            DocumentVersion.document_id == document.id
        )
    )
    version_id: UUID | None = await session.scalar(
        insert(DocumentVersion)
        .values(
            document_id=document.id,
            version_no=(last_no or 0) + 1,
            content_hash=job.content_hash,
            storage_key=job.storage_key,
            source_url=meta.source_url,
            published_date=date.fromisoformat(meta.published_date) if meta.published_date else None,
            status=meta.status,
            authority=meta.authority,
            page_count=parsed.page_count,
        )
        .returning(DocumentVersion.id)
    )
    if version_id is None:
        raise AssertionError("unreachable: insert returns the new id")
    inserted = await session.execute(
        insert(SectionRow).returning(SectionRow.ordinal, SectionRow.id),
        [
            {
                "version_id": version_id,
                "path": section.path,
                "text": section.text,
                "page_start": section.page_start,
                "page_end": section.page_end,
                "ordinal": section.ordinal,
            }
            for section in parsed.sections
        ],
    )
    section_ids = {row.ordinal: row.id for row in inserted}
    await session.execute(
        insert(ChunkRow), chunk_rows(chunks, vectors, section_ids, version_id, document)
    )
    await flip_current(session, document, version_id)
    return version_id


def chunk_rows(
    chunks: list[Chunk],
    vectors: list[list[float]],
    section_ids: dict[int, UUID],
    version_id: UUID,
    document: Document,
) -> list[dict[str, Any]]:
    return [
        {
            "version_id": version_id,
            "document_id": document.id,
            "section_id": section_ids[chunk.section_ordinal],
            # The ACL columns are copied here and nowhere else.
            "tenant_id": document.tenant_id,
            "access_level": document.access_level,
            "is_current": False,  # flip_current makes the whole version visible at once
            "ordinal": chunk.ordinal,
            "section_path": chunk.section_path,
            "text": chunk.text,
            "token_count": chunk.token_count,
            "spans": [{"page": span.page, "bbox": list(span.bbox)} for span in chunk.spans],
            "content_hash": chunk.content_hash,
            "embedding": vector,
        }
        for chunk, vector in zip(chunks, vectors, strict=True)
    ]


async def flip_current(session: AsyncSession, document: Document, version_id: UUID) -> None:
    """Old rows first: dv_one_current allows only one current version per document."""
    await session.execute(
        update(DocumentVersion)
        .where(DocumentVersion.document_id == document.id, DocumentVersion.is_current)
        .values(is_current=False)
    )
    await session.execute(
        update(ChunkRow)
        .where(ChunkRow.document_id == document.id, ChunkRow.is_current)
        .values(is_current=False)
    )
    await session.execute(
        update(DocumentVersion).where(DocumentVersion.id == version_id).values(is_current=True)
    )
    await session.execute(
        update(ChunkRow).where(ChunkRow.version_id == version_id).values(is_current=True)
    )
    document.current_version_id = version_id


async def process(
    job: ClaimedJob,
    meta: VersionMeta,
    sessions: async_sessionmaker[AsyncSession],
    embedder: IngestEmbedder,
    storage_dir: Path,
) -> None:
    path = storage_dir / job.storage_key
    read_verified(path, job.content_hash)
    parsed = parse_pdf(path)
    chunks = await chunk_document(parsed, embedder.count_tokens)
    check_quality(parsed, chunks)
    vectors = await embedder.embed_documents([chunk.text for chunk in chunks])
    async with sessions.begin() as session:
        version_id = await write_version(session, job, meta, parsed, chunks, vectors)
        finished = await session.scalar(
            update(IngestionJob)
            .where(owned_by(job))
            .values(status="succeeded", version_id=version_id, error=None, updated_at=func.now())
            .returning(IngestionJob.id)
        )
        if finished is None:
            raise StaleAttempt(f"job {job.id} moved past attempt {job.attempts}")


def owned_by(job: ClaimedJob) -> ColumnElement[bool]:
    return and_(
        IngestionJob.id == job.id,
        IngestionJob.attempts == job.attempts,
        IngestionJob.status == "running",
    )


def error_text(error: Exception) -> str:
    """A database error embeds its statement and parameters, which may hold chunk text."""
    return f"{type(error).__name__}: {getattr(error, 'orig', error)}"[:MAX_ERROR_CHARS]


async def record_failure(
    sessions: async_sessionmaker[AsyncSession], job: ClaimedJob, error: Exception, retry: bool
) -> None:
    """Does nothing if a newer attempt took the job: its outcome is the one that counts."""
    async with sessions.begin() as session:
        await session.execute(
            update(IngestionJob)
            .where(owned_by(job))
            .values(
                status="pending" if retry else "failed",
                error=error_text(error),
                updated_at=func.now(),
            )
        )


async def run_job(
    job_id: UUID,
    meta: VersionMeta,
    *,
    sessions: async_sessionmaker[AsyncSession],
    embedder: IngestEmbedder,
    storage_dir: Path,
) -> bool:
    """Run one attempt and record its outcome. Returns True if the job should be retried.

    Raises when the outcome cannot be recorded, such as with the database down, or JobBusy.
    The task retries both, because no row can say so.
    """
    job = await claim(sessions, job_id)
    if job is None:
        return False
    try:
        await process(job, meta, sessions, embedder, storage_dir)
    except StaleAttempt:
        return False
    except IngestionFailed as error:
        await record_failure(sessions, job, error, retry=False)
        return False
    except Exception as error:  # whatever went wrong must end up in the job row
        retry = job.attempts < job.max_attempts
        logger.warning("ingestion job %s failed: %s", job.id, type(error).__name__)
        await record_failure(sessions, job, error, retry=retry)
        return retry
    return False
