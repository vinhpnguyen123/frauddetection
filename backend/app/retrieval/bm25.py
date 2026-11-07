"""BM25 search through pg_search. The index is `chunks_bm25` (migration 0002)."""

from uuid import UUID

from sqlalchemy import ColumnElement, Float, Select, Text, cast, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models import Chunk
from app.retrieval.acl import access_predicate
from app.retrieval.protocols import RetrievalContext, SearchHit


def bm25_match(query: str) -> ColumnElement[bool]:
    """Match chunks holding any query term. `|||` tokenizes `query` like the indexed column."""
    term = cast(query, Text)
    return or_(Chunk.text.op("|||")(term), Chunk.section_path.op("|||")(term))


def bm25_statement(
    query: str, *, context: RetrievalContext, limit: int
) -> Select[tuple[UUID, float]]:
    """Build the search query, with the ACL inside it. Tests run EXPLAIN on this exact statement.

    The `id` tiebreak keeps equal scores in a stable order.
    """
    score = func.pdb.score(Chunk.id, type_=Float)
    return (
        select(Chunk.id, score.label("score"))
        .where(bm25_match(query), access_predicate(context))
        .order_by(score.desc(), Chunk.id)
        .limit(limit)
    )


class Bm25Retriever:
    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def search(self, query: str, *, context: RetrievalContext, limit: int) -> list[SearchHit]:
        """Return the best matches the context may read. The ACL is applied in the SQL query."""
        statement = bm25_statement(query, context=context, limit=limit)
        async with self._sessions() as session:
            rows = (await session.execute(statement)).all()
        return [
            SearchHit(chunk_id=row.id, score=row.score, rank=rank, method="bm25")
            for rank, row in enumerate(rows, start=1)
        ]
