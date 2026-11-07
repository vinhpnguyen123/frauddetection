"""Parent expansion: the full section around a chunk, as extra context for generation.

Citations still point to chunks. `sections` has no ACL columns, so a section is only reachable
through a chunk the context may read.
"""

from collections.abc import Collection
from uuid import UUID

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models import Chunk, Section
from app.retrieval.acl import access_predicate
from app.retrieval.protocols import RetrievalContext


def parent_sections_statement(
    chunk_ids: Collection[UUID], *, context: RetrievalContext
) -> Select[UUID, str]:
    """Read each chunk's section, with the ACL inside the query. Tests run EXPLAIN on this."""
    return (
        select(Chunk.id, Section.text)
        .join(Section, Chunk.section_id == Section.id)
        .where(Chunk.id.in_(chunk_ids), access_predicate(context))
    )


async def parent_sections(
    sessions: async_sessionmaker[AsyncSession],
    chunk_ids: Collection[UUID],
    *,
    context: RetrievalContext,
) -> dict[UUID, str]:
    """Map each readable chunk to its section text. Other ids are simply absent."""
    statement = parent_sections_statement(chunk_ids, context=context)
    async with sessions() as session:
        return {row.id: row.text for row in await session.execute(statement)}
