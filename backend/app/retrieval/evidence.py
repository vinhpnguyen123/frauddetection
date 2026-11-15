"""Evidence for generation: chunk text plus the document facts the prompt must state.

Read through the ACL in SQL, like every other chunk read, so the LLM is never shown a chunk
the context cannot read, even if one stopped being readable after the search.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from typing import Any
from uuid import UUID

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models import Chunk, Document, DocumentVersion
from app.retrieval.acl import access_predicate
from app.retrieval.parent import parent_sections
from app.retrieval.protocols import RetrievalContext


@dataclass(frozen=True)
class Evidence:
    chunk_id: UUID
    version_id: UUID
    text: str
    section_path: str
    spans: list[dict[str, Any]]  # Any: JSONB [{"page": int, "bbox": [x0, y0, x1, y1]}]
    title: str
    source: str
    authority: str
    status: str  # active | rescinded | superseded
    published_date: date | None
    parent_text: str | None = None  # only with parent_expansion


def evidence_statement(chunk_ids: Sequence[UUID], *, context: RetrievalContext) -> Select[Any]:
    """Join chunk → version → document, with the ACL inside the query. Tests run EXPLAIN on it."""
    return (
        select(
            Chunk.id,
            Chunk.version_id,
            Chunk.text,
            Chunk.section_path,
            Chunk.spans,
            Document.title,
            Document.source,
            DocumentVersion.authority,
            DocumentVersion.status,
            DocumentVersion.published_date,
        )
        .join(DocumentVersion, Chunk.version_id == DocumentVersion.id)
        .join(Document, Chunk.document_id == Document.id)
        .where(Chunk.id.in_(chunk_ids), access_predicate(context))
    )


async def load_evidence(
    sessions: async_sessionmaker[AsyncSession],
    chunk_ids: Sequence[UUID],
    *,
    context: RetrievalContext,
    parent_expansion: bool,
) -> list[Evidence]:
    """Return readable chunks in the order given. Unreadable ids are simply absent."""
    async with sessions() as session:
        rows = {
            row.id: row
            for row in await session.execute(evidence_statement(chunk_ids, context=context))
        }
    parents = (
        await parent_sections(sessions, list(rows), context=context) if parent_expansion else {}
    )
    return [
        Evidence(
            chunk_id=row.id,
            version_id=row.version_id,
            text=row.text,
            section_path=row.section_path,
            spans=row.spans,
            title=row.title,
            source=row.source,
            authority=row.authority,
            status=row.status,
            published_date=row.published_date,
            parent_text=parents.get(row.id),
        )
        for chunk_id in chunk_ids
        if (row := rows.get(chunk_id)) is not None
    ]
