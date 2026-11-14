"""Trace parity and export authorization against real ParadeDB; model calls stay fake."""

from dataclasses import replace
from uuid import UUID, uuid4

import pytest
from eval.runner.retrieval import CONFIGS, build_retriever, load_corpus, run_item
from eval.runner.tracing import Observation, TraceCollector
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncConnection

from app.embedder import HttpEmbedder
from app.models import Chunk
from app.retrieval.diagnostics import RerankDiagnostics, TokenVisibility
from app.retrieval.protocols import RetrievalContext, SearchHit
from tests.fixtures.two_tenants import CANARY_A, CANARY_B, SHARED_TERM, create_two_tenants
from tests.integration.test_acl import FixedEmbedder, sessions_for
from tests.integration.test_eval_runner import item


class DiagnosticModel(FixedEmbedder):
    def __init__(self) -> None:
        self.calls = 0

    async def rerank(
        self, query: str, candidates: list[tuple[UUID, str]], top_k: int
    ) -> list[SearchHit]:
        self.calls += 1
        return HttpEmbedder.rank_scores(
            candidates, [float(i) for i in range(len(candidates))], top_k
        )

    async def rerank_detailed(
        self, query: str, candidates: list[tuple[UUID, str]], top_k: int
    ) -> tuple[list[SearchHit], RerankDiagnostics]:
        hits = await self.rerank(query, candidates, top_k)
        details = RerankDiagnostics(
            model="fixture",
            model_revision="fixture",
            tokenizer_revision="fixture",
            scoring_ms=1,
            token_inspection_ms=1,
            scores=[float(i) for i in range(len(candidates))],
            tokens=[
                TokenVisibility(
                    query_tokens=1,
                    document_tokens=5,
                    special_tokens=3,
                    input_tokens=9,
                    effective_tokens=9,
                    retained_query_tokens=1,
                    retained_document_tokens=5,
                    effective_limit=512,
                    truncated=False,
                    document_visible_ranges=[(0, len(text))],
                    input_ids_sha256="fixture",
                )
                for _, text in candidates
            ],
        )
        return hits, details


@pytest.mark.parametrize(
    "name", ["fts", "bm25", "dense_exact", "hybrid_raw", "rerank_top20", "rerank_top50"]
)
async def test_tracing_preserves_order_scores_metrics_and_hides_foreign_content(
    connection: AsyncConnection, name: str
) -> None:
    tenants = await create_two_tenants(connection)
    sessions = sessions_for(connection)
    config = CONFIGS[name]
    corpus = await load_corpus(sessions)
    model = DiagnosticModel()
    normal = build_retriever(config, sessions, model, model)
    entry = item("fixture-query", ask_as_tenant="fixture-a")
    before = await run_item(entry, config, normal, tenants.tenant_a, corpus)
    ctx = RetrievalContext(uuid4(), tenants.tenant_a, frozenset({"public", "tenant_private"}))
    expected_hits = await normal.search(SHARED_TERM, context=ctx, limit=20)
    trace = TraceCollector()
    traced = build_retriever(config, sessions, model, trace.wrap_reranker(model), trace=trace)
    after = await run_item(
        entry, config, traced, tenants.tenant_a, corpus, trace=trace, sessions=sessions
    )
    assert replace(before, latency_ms=0) == replace(after, latency_ms=0)
    result = trace.queries[0]
    final = next(s for s in result.stages if s.name == "final_top20")
    assert [(c.chunk_id, c.rank, c.score) for c in final.candidates] == [
        (h.chunk_id, h.rank, h.score) for h in expected_hits
    ]
    foreign = (
        await connection.execute(
            select(Chunk.id, Chunk.document_id).where(Chunk.tenant_id == tenants.tenant_b)
        )
    ).one()
    serialized = result.model_dump_json()
    for forbidden in (CANARY_A, CANARY_B, str(foreign.id), str(foreign.document_id), SHARED_TERM):
        assert forbidden not in serialized
    assert result.sufficiency_status == "unjudged" and result.answer_sufficiency is None
    if config.method in ("hybrid", "rerank"):
        stages = {s.name: s for s in result.stages}
        assert stages["rrf_top20"].candidates == stages["rrf_top50"].candidates[:20]
        assert set(stages["rrf_top50"].retained_anchor_ids).issubset(
            set(stages["bm25"].retained_anchor_ids) | set(stages["dense"].retained_anchor_ids)
        )
    if config.method == "rerank":
        assert len(result.reranker_inputs) == len(expected_hits)
        assert model.calls == 3  # once per normal/expected/traced call, never a shadow score call
        assert trace.input_candidates == []


async def test_even_gold_references_are_sql_filtered_before_export(
    connection: AsyncConnection,
) -> None:
    tenants = await create_two_tenants(connection)
    foreign = await connection.scalar(select(Chunk.id).where(Chunk.tenant_id == tenants.tenant_b))
    ctx = RetrievalContext(uuid4(), tenants.tenant_a, frozenset({"public", "tenant_private"}))
    result = await TraceCollector().finish(
        query_id="fixture",
        config=CONFIGS["fts"],
        context=ctx,
        gold=[{foreign}],
        quotes=[CANARY_B],
        final=[],
        sessions=sessions_for(connection),
    )
    assert result.gold[0].chunk_ids == []
    assert str(foreign) not in result.model_dump_json()
    assert CANARY_B not in result.model_dump_json()


async def test_forbidden_observed_ids_abort_the_whole_trace(connection: AsyncConnection) -> None:
    tenants = await create_two_tenants(connection)
    foreign = await connection.scalar(select(Chunk.id).where(Chunk.tenant_id == tenants.tenant_b))
    trace = TraceCollector()
    trace.observations["bm25"] = Observation([SearchHit(foreign, 1, 1, "bm25")], 1)
    ctx = RetrievalContext(uuid4(), tenants.tenant_a, frozenset({"public", "tenant_private"}))
    with pytest.raises(ValueError, match="authorization"):
        await trace.finish(
            query_id="fixture",
            config=CONFIGS["bm25"],
            context=ctx,
            gold=[],
            quotes=[],
            final=[],
            sessions=sessions_for(connection),
        )
    assert trace.queries == []


async def test_review_pool_passages_are_sql_scoped(connection: AsyncConnection) -> None:
    from eval.runner.relevance_review import authorized_passages

    tenants = await create_two_tenants(connection)
    ctx = RetrievalContext(uuid4(), tenants.tenant_a, frozenset({"public", "tenant_private"}))
    rows = await authorized_passages(sessions_for(connection), ctx)
    content = " ".join(str(row["text"]) for row in rows)
    assert CANARY_A in content
    assert CANARY_B not in content
    empty = RetrievalContext(uuid4(), tenants.tenant_a, frozenset())
    assert await authorized_passages(sessions_for(connection), empty) == []
