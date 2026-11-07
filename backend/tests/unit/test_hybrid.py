"""RRF arithmetic, and which query and limit reach each path."""

from uuid import UUID, uuid4

import pytest

from app.retrieval.hybrid import HybridRetriever, rrf_fuse
from app.retrieval.protocols import RetrievalContext, SearchHit

LOW = UUID(int=1)
MID = UUID(int=2)
HIGH = UUID(int=3)
CONTEXT = RetrievalContext(uuid4(), uuid4(), frozenset({"public"}))


def ranking(*chunk_ids: UUID) -> list[SearchHit]:
    """Hits with scores that must not matter: RRF reads the rank only."""
    return [
        SearchHit(chunk_id=chunk_id, score=1000.0 * rank, rank=rank, method="bm25")
        for rank, chunk_id in enumerate(chunk_ids, start=1)
    ]


class RecordingRetriever:
    def __init__(self, hits: list[SearchHit]) -> None:
        self.hits = hits
        self.calls: list[tuple[str, RetrievalContext, int]] = []

    async def search(self, query: str, *, context: RetrievalContext, limit: int) -> list[SearchHit]:
        self.calls.append((query, context, limit))
        return self.hits


def test_score_is_the_sum_of_reciprocal_ranks() -> None:
    fused = rrf_fuse([ranking(LOW, MID), ranking(MID)], k=60, limit=10)
    assert [(hit.chunk_id, hit.rank, hit.method) for hit in fused] == [
        (MID, 1, "hybrid"),
        (LOW, 2, "hybrid"),
    ]
    assert fused[0].score == pytest.approx(1 / 62 + 1 / 61)
    assert fused[1].score == pytest.approx(1 / 61)


def test_a_chunk_in_both_rankings_beats_a_top_hit_of_one() -> None:
    fused = rrf_fuse([ranking(LOW, HIGH), ranking(MID, HIGH)], k=60, limit=1)
    assert fused[0].chunk_id == HIGH


def test_a_tie_goes_to_the_lower_chunk_id() -> None:
    fused = rrf_fuse([ranking(HIGH), ranking(LOW)], k=60, limit=10)
    assert [hit.chunk_id for hit in fused] == [LOW, HIGH]


def test_limit_applies_after_fusion() -> None:
    fused = rrf_fuse([ranking(LOW, MID, HIGH)], k=60, limit=2)
    assert [hit.rank for hit in fused] == [1, 2]


def test_one_empty_ranking_keeps_the_other_order() -> None:
    fused = rrf_fuse([[], ranking(HIGH, LOW)], k=60, limit=10)
    assert [hit.chunk_id for hit in fused] == [HIGH, LOW]


def test_no_hits_fuse_to_nothing() -> None:
    assert rrf_fuse([[], []], k=60, limit=10) == []


@pytest.mark.parametrize(
    ("query_expansion", "bm25_query"),
    [(True, "SAR deadline suspicious activity report"), (False, "SAR deadline")],
)
async def test_expansion_reaches_bm25_only(query_expansion: bool, bm25_query: str) -> None:
    bm25 = RecordingRetriever(ranking(LOW))
    dense = RecordingRetriever(ranking(MID))
    retriever = HybridRetriever(
        bm25, dense, k_bm25=7, k_dense=9, rrf_k=60, query_expansion=query_expansion
    )

    hits = await retriever.search("SAR deadline", context=CONTEXT, limit=1)

    assert bm25.calls == [(bm25_query, CONTEXT, 7)]
    assert dense.calls == [("SAR deadline", CONTEXT, 9)]
    assert len(hits) == 1
