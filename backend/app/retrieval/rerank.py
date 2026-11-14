"""Second stage: a cross-encoder reads each candidate with the query and reorders them."""

from collections.abc import Collection
from uuid import UUID

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models import Chunk
from app.retrieval.acl import access_predicate
from app.retrieval.protocols import Reranker, RetrievalContext, Retriever, SearchHit


def chunk_texts_statement(
    chunk_ids: Collection[UUID], *, context: RetrievalContext
) -> Select[UUID, str]:
    """Read candidate texts, with the ACL inside the query. Tests run EXPLAIN on this statement."""
    return select(Chunk.id, Chunk.text).where(Chunk.id.in_(chunk_ids), access_predicate(context))


class RerankRetriever:
    def __init__(
        self,
        base: Retriever,
        reranker: Reranker,
        sessions: async_sessionmaker[AsyncSession],
        *,
        top_n: int,
    ) -> None:
        self._base = base
        self._reranker = reranker
        self._sessions = sessions
        self._top_n = top_n

    async def search(self, query: str, *, context: RetrievalContext, limit: int) -> list[SearchHit]:
        """Rerank the base top-N and return the best `limit`.

        Candidate text is read through the ACL again, so the model only sees chunks the context
        may read, even if a candidate stopped being readable after the base search.
        """
        hits = await self._base.search(query, context=context, limit=self._top_n)
        statement = chunk_texts_statement([hit.chunk_id for hit in hits], context=context)
        async with self._sessions() as session:
            texts: dict[UUID, str] = {row.id: row.text for row in await session.execute(statement)}
        candidates = [(hit.chunk_id, texts[hit.chunk_id]) for hit in hits if hit.chunk_id in texts]
        return await self._reranker.rerank(query, candidates, limit)
