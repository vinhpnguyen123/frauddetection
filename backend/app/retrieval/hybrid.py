"""Hybrid search: BM25 and dense rankings fused with Reciprocal Rank Fusion."""

from collections import defaultdict
from uuid import UUID

from app.retrieval.protocols import RetrievalContext, Retriever, SearchHit
from app.retrieval.query_processing import expand_query


def rrf_fuse(rankings: list[list[SearchHit]], *, k: int, limit: int) -> list[SearchHit]:
    """Score each chunk by the sum of 1 / (k + rank) over the rankings that hold it.

    Only ranks are used, because BM25 and cosine scores are on different scales. A tie goes
    to the lower `chunk_id`, so a run is repeatable.
    """
    scores: defaultdict[UUID, float] = defaultdict(float)
    for hits in rankings:
        for hit in hits:
            scores[hit.chunk_id] += 1 / (k + hit.rank)
    ordered = sorted(scores.items(), key=lambda item: (-item[1], item[0]))[:limit]
    return [
        SearchHit(chunk_id=chunk_id, score=score, rank=rank, method="hybrid")
        for rank, (chunk_id, score) in enumerate(ordered, start=1)
    ]


class HybridRetriever:
    def __init__(
        self,
        bm25: Retriever,
        dense: Retriever,
        *,
        k_bm25: int,
        k_dense: int,
        rrf_k: int,
        query_expansion: bool,
    ) -> None:
        self._bm25 = bm25
        self._dense = dense
        self._k_bm25 = k_bm25
        self._k_dense = k_dense
        self._rrf_k = rrf_k
        self._query_expansion = query_expansion

    async def search(self, query: str, *, context: RetrievalContext, limit: int) -> list[SearchHit]:
        """Fuse both paths. Each one applies the ACL in its own SQL query, so this adds no filter.

        Expansion feeds BM25 only: appended words could shift the query embedding.
        """
        bm25_query = expand_query(query) if self._query_expansion else query
        # ponytail: one path after the other; asyncio.gather if M8 latency work shows it matters.
        bm25_hits = await self._bm25.search(bm25_query, context=context, limit=self._k_bm25)
        dense_hits = await self._dense.search(query, context=context, limit=self._k_dense)
        return rrf_fuse([bm25_hits, dense_hits], k=self._rrf_k, limit=limit)
