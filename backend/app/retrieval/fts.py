"""Postgres full-text search. A baseline only: this is not BM25."""

from uuid import UUID

from sqlalchemy import Select, Text, cast, func, select
from sqlalchemy.dialects.postgresql import REGCONFIG, TSQUERY
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models import Chunk
from app.retrieval.acl import access_predicate
from app.retrieval.protocols import RetrievalContext, SearchHit


def fts_statement(
    query: str, *, context: RetrievalContext, limit: int
) -> Select[tuple[UUID, float]]:
    """Build the search query, with the ACL inside it. Tests run EXPLAIN on this exact statement.

    Terms are joined with OR, because AND would match only chunks holding every term of a full
    question, which makes the baseline unfairly weak. `plainto_tsquery` ignores search operators
    (`-`, quotes), so its output only ever holds positive terms joined by `&`.
    """
    parsed = func.plainto_tsquery(cast("english", REGCONFIG), query)
    ts_query = cast(func.replace(cast(parsed, Text), " & ", " | "), TSQUERY)
    score = func.ts_rank_cd(Chunk.fts, ts_query)
    return (
        select(Chunk.id, score.label("score"))
        .where(Chunk.fts.op("@@")(ts_query), access_predicate(context))
        .order_by(score.desc(), Chunk.id)
        .limit(limit)
    )


class FtsRetriever:
    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def search(self, query: str, *, context: RetrievalContext, limit: int) -> list[SearchHit]:
        """Return the best matches the context may read. The ACL is applied in the SQL query."""
        statement = fts_statement(query, context=context, limit=limit)
        async with self._sessions() as session:
            rows = (await session.execute(statement)).all()
        return [
            SearchHit(chunk_id=row.id, score=row.score, rank=rank, method="fts")
            for rank, row in enumerate(rows, start=1)
        ]
