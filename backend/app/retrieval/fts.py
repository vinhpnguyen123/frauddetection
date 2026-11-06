"""Postgres full-text search. A baseline only: this is not BM25."""

from sqlalchemy import cast, func, select
from sqlalchemy.dialects.postgresql import REGCONFIG
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models import Chunk
from app.retrieval.acl import access_predicate
from app.retrieval.protocols import RetrievalContext, SearchHit


class FtsRetriever:
    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def search(self, query: str, *, context: RetrievalContext, limit: int) -> list[SearchHit]:
        """Return the best matches the context may read. The ACL is applied in the SQL query."""
        ts_query = func.websearch_to_tsquery(cast("english", REGCONFIG), query)
        score = func.ts_rank_cd(Chunk.fts, ts_query)
        statement = (
            select(Chunk.id, score.label("score"))
            .where(Chunk.fts.op("@@")(ts_query), access_predicate(context))
            .order_by(score.desc(), Chunk.id)
            .limit(limit)
        )
        async with self._sessions() as session:
            rows = (await session.execute(statement)).all()
        return [
            SearchHit(chunk_id=row.id, score=row.score, rank=rank, method="fts")
            for rank, row in enumerate(rows, start=1)
        ]
