"""Tracing captures real outputs; fusion replay must reproduce their ordering."""

from uuid import UUID, uuid4

import pytest
from eval.runner.retrieval import CONFIGS, evaluate
from eval.runner.tracing import Observation, QueryTrace, TraceCollector
from pydantic import ValidationError

from app.retrieval.hybrid import rrf_fuse
from app.retrieval.protocols import RetrievalContext, SearchHit


class Leaf:
    def __init__(self, hits: list[SearchHit]) -> None:
        self.hits, self.calls = hits, 0

    async def search(self, query: str, *, context: RetrievalContext, limit: int) -> list[SearchHit]:
        self.calls += 1
        return self.hits[:limit]


async def test_capture_does_not_repeat_or_change_the_leaf_call() -> None:
    hits = [SearchHit(UUID(int=i), 1 / i, i, "bm25") for i in range(1, 4)]
    leaf = Leaf(hits)
    trace = TraceCollector()
    ctx = RetrievalContext(uuid4(), uuid4(), frozenset({"public"}))
    assert await trace.wrap(leaf, "bm25").search("private query", context=ctx, limit=2) == hits[:2]
    assert leaf.calls == 1 and trace.observations["bm25"].hits == hits[:2]


def test_fusion_trace_prefixes_match_actual_ranking_or_fail_closed() -> None:
    hits = [SearchHit(UUID(int=i), 0.5, i, "bm25") for i in range(1, 61)]
    trace = TraceCollector()
    trace.observations["bm25"] = Observation(hits[:50], 1)
    trace.observations["dense"] = Observation(hits[10:], 2)
    actual = rrf_fuse([hits[:50], hits[10:]], k=60, limit=20)
    trace.observations["hybrid"] = Observation(actual, 4)
    trace.fusion_stages(CONFIGS["hybrid_raw"])
    assert trace.observations["rrf_top20"].hits == actual
    assert trace.observations["rrf_top50"].hits[:20] == actual
    trace.observations["hybrid"].hits = actual[::-1]
    with pytest.raises(ValueError, match="actual hybrid ordering"):
        trace.fusion_stages(CONFIGS["hybrid_raw"])


async def test_trace_flag_cannot_run_the_held_out_test_set() -> None:
    with pytest.raises(SystemExit, match="SET=dev"):
        await evaluate("test", "hybrid_raw", "fixture", trace_enabled=True)


def test_public_trace_schema_rejects_raw_query_fields() -> None:
    fields = dict(
        query_id="fixture",
        config_hash="fixture",
        config=CONFIGS["fts"],
        gold=[],
        stages=[],
        reranker_inputs=[],
        reranker_metadata={},
        diagnostics={},
    )
    with pytest.raises(ValidationError, match="extra_forbidden"):
        QueryTrace.model_validate({**fields, "query": "sensitive"})
