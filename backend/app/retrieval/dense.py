"""Dense search over `chunks.embedding` (cosine), exact or through the HNSW index."""

from typing import Literal
from uuid import UUID

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models import Chunk
from app.retrieval.acl import access_predicate
from app.retrieval.protocols import Embedder, RetrievalContext, SearchHit

DenseMode = Literal["exact", "hnsw"]

# Applied per transaction. Exact turns index scans off, as the pgvector docs advise.
# HNSW must be forced: on a corpus this small the planner prefers a seq scan and a sort, so
# the "hnsw" mode would silently be exact. pgvector filters after the index scan, so
# iterative_scan keeps scanning until LIMIT is met; relaxed_order may return hits slightly
# out of order, which `search` puts right. ef_search 100 starts the scan wider than a top-50.
MODE_SETTINGS: dict[DenseMode, dict[str, str]] = {
    "exact": {"enable_indexscan": "off"},
    "hnsw": {
        "enable_seqscan": "off",
        "enable_bitmapscan": "off",
        "enable_sort": "off",
        "hnsw.ef_search": "100",
        "hnsw.iterative_scan": "relaxed_order",
    },
}


def dense_statement(
    embedding: list[float], *, context: RetrievalContext, limit: int
) -> Select[tuple[UUID, float]]:
    """Build the search query, with the ACL inside it. Tests run EXPLAIN on this exact statement.

    Ordering by the distance alone lets the HNSW index provide the order.
    """
    distance = Chunk.embedding.cosine_distance(embedding)
    return (
        select(Chunk.id, (1 - distance).label("score"))
        .where(access_predicate(context))
        .order_by(distance)
        .limit(limit)
    )


class DenseRetriever:
    def __init__(
        self, sessions: async_sessionmaker[AsyncSession], embedder: Embedder, mode: DenseMode
    ) -> None:
        self._sessions = sessions
        self._embedder = embedder
        self._mode = mode

    async def search(self, query: str, *, context: RetrievalContext, limit: int) -> list[SearchHit]:
        """Return the nearest chunks the context may read. The ACL is applied in the SQL query."""
        embedding = await self._embedder.embed_query(query)
        statement = dense_statement(embedding, context=context, limit=limit)
        async with self._sessions() as session, session.begin():
            for name, value in MODE_SETTINGS[self._mode].items():
                await session.execute(select(func.set_config(name, value, True)))
            rows = (await session.execute(statement)).all()
        ordered = sorted(rows, key=lambda row: (-row.score, row.id))
        return [
            SearchHit(chunk_id=row.id, score=row.score, rank=rank, method=f"dense_{self._mode}")
            for rank, row in enumerate(ordered, start=1)
        ]
