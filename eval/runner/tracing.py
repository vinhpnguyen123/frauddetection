"""Opt-in evaluation traces. Content stays in memory; exports contain identifiers only."""

from collections.abc import Sequence
from dataclasses import dataclass
from time import perf_counter
from typing import Literal, Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.embedder import HttpEmbedder
from app.models import Chunk
from app.retrieval.acl import access_predicate
from app.retrieval.config import RetrievalConfig
from app.retrieval.diagnostics import RerankDiagnostics, TokenVisibility
from app.retrieval.hybrid import rrf_fuse
from app.retrieval.protocols import Embedder, Reranker, RetrievalContext, Retriever, SearchHit
from eval.runner.anchors import holds_quote, squash


class TraceValue(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Candidate(TraceValue):
    chunk_id: UUID
    document_id: UUID
    version_id: UUID
    rank: int
    score: float
    method: str


class Stage(TraceValue):
    name: str
    candidates: list[Candidate]
    retained_anchor_ids: list[str]
    elapsed_ms: float
    timing: Literal["inclusive", "derived_diagnostic"]


class GoldEvidence(TraceValue):
    anchor_id: str
    chunk_ids: list[UUID]


class VisibleAnchor(TraceValue):
    anchor_id: str
    full_quote_visible: bool
    label_match_visible: bool


class RerankerInput(TraceValue):
    chunk_id: UUID
    input_rank: int
    upstream_rank: int
    upstream_score: float
    score: float
    tokens: TokenVisibility
    anchors: list[VisibleAnchor]


class QueryTrace(TraceValue):
    schema_version: Literal["retrieval-trace/v1"] = "retrieval-trace/v1"
    query_id: str
    config_hash: str
    config: RetrievalConfig
    gold: list[GoldEvidence]
    stages: list[Stage]
    reranker_inputs: list[RerankerInput]
    reranker_metadata: dict[str, str | float]
    diagnostics: dict[str, list[str]]
    answer_sufficiency: None = None  # requires independent set-level judgments in Q2
    sufficiency_status: Literal["unjudged"] = "unjudged"


class DetailedReranker(Protocol):
    async def rerank_detailed(
        self, query: str, candidates: list[tuple[UUID, str]], top_k: int
    ) -> tuple[list[SearchHit], RerankDiagnostics]: ...


@dataclass
class Observation:
    hits: list[SearchHit]
    elapsed_ms: float
    derived: bool = False


class RecordingRetriever:
    def __init__(self, base: Retriever, name: str, collector: "TraceCollector") -> None:
        self.base, self.name, self.collector = base, name, collector

    async def search(self, query: str, *, context: RetrievalContext, limit: int) -> list[SearchHit]:
        started = perf_counter()
        hits = await self.base.search(query, context=context, limit=limit)
        self.collector.observations[self.name] = Observation(
            hits, (perf_counter() - started) * 1000
        )
        return hits


class RecordingEmbedder:
    def __init__(self, base: Embedder, collector: "TraceCollector") -> None:
        self.base, self.collector = base, collector

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return await self.base.embed_documents(texts)

    async def embed_query(self, text: str) -> list[float]:
        started = perf_counter()
        vector = await self.base.embed_query(text)
        self.collector.observations["query_embedding"] = Observation(
            [], (perf_counter() - started) * 1000
        )
        return vector


class RecordingReranker:
    def __init__(self, base: DetailedReranker, collector: "TraceCollector") -> None:
        self.base, self.collector = base, collector

    async def rerank(
        self, query: str, candidates: list[tuple[UUID, str]], top_k: int
    ) -> list[SearchHit]:
        if not candidates:
            return []
        started = perf_counter()
        hits, details = await self.base.rerank_detailed(query, candidates, top_k)
        self.collector.details = details
        self.collector.input_candidates = candidates
        self.collector.observations["reranker_all"] = Observation(
            HttpEmbedder.rank_scores(candidates, details.scores, len(candidates)),
            (perf_counter() - started) * 1000,
        )
        return hits


class TraceCollector:
    """One collector per config/run; reset per query, never a process-global logger."""

    def __init__(self) -> None:
        self.queries: list[QueryTrace] = []
        self.reset()

    def reset(self) -> None:
        self.observations: dict[str, Observation] = {}
        self.details: RerankDiagnostics | None = None
        self.input_candidates: list[tuple[UUID, str]] = []

    def wrap(self, base: Retriever, name: str) -> Retriever:
        return RecordingRetriever(base, name, self)

    def wrap_embedder(self, base: Embedder) -> Embedder:
        return RecordingEmbedder(base, self)

    def wrap_reranker(self, base: DetailedReranker) -> Reranker:
        return RecordingReranker(base, self)

    def fusion_stages(self, config: RetrievalConfig) -> None:
        if "bm25" not in self.observations or "dense" not in self.observations:
            return
        started = perf_counter()
        fused = rrf_fuse(
            [self.observations[n].hits for n in ("bm25", "dense")], k=config.rrf_k, limit=50
        )
        elapsed = (perf_counter() - started) * 1000
        actual = self.observations["hybrid"].hits
        if actual != fused[: len(actual)]:
            raise ValueError("trace replay does not match the actual hybrid ordering")
        self.observations["rrf_top20"] = Observation(fused[:20], elapsed, True)
        self.observations["rrf_top50"] = Observation(fused, elapsed, True)

    async def finish(
        self,
        *,
        query_id: str,
        config: RetrievalConfig,
        context: RetrievalContext,
        gold: Sequence[set[UUID]],
        quotes: Sequence[str],
        final: list[SearchHit],
        sessions: async_sessionmaker[AsyncSession],
        retrieval_ms: float = 0,
    ) -> QueryTrace:
        """Recheck export IDs in SQL. A stale/foreign observed ID aborts rather than leaks."""
        self.fusion_stages(config)
        self.observations["final_top20"] = Observation(final, retrieval_ms)
        observed_ids = {h.chunk_id for o in self.observations.values() for h in o.hits}
        gold_ids = set().union(*gold) if gold else set()
        statement = select(Chunk.id, Chunk.document_id, Chunk.version_id).where(
            Chunk.id.in_(observed_ids | gold_ids), access_predicate(context)
        )
        async with sessions() as session:
            metadata = {
                r.id: (r.document_id, r.version_id) for r in await session.execute(statement)
            }
        if not observed_ids.issubset(metadata):
            raise ValueError(
                "trace authorization changed or an upstream stage returned forbidden IDs"
            )
        readable_gold = [g.intersection(metadata) for g in gold]
        anchor_ids = [f"{query_id}:a{i + 1}" for i in range(len(gold))]

        def retained(hits: list[SearchHit]) -> list[str]:
            ids = {h.chunk_id for h in hits}
            return [a for a, g in zip(anchor_ids, readable_gold, strict=True) if ids & g]

        stages = [
            Stage(
                name=name,
                candidates=[
                    Candidate(
                        chunk_id=h.chunk_id,
                        document_id=metadata[h.chunk_id][0],
                        version_id=metadata[h.chunk_id][1],
                        rank=h.rank,
                        score=h.score,
                        method=h.method,
                    )
                    for h in observation.hits
                ],
                retained_anchor_ids=retained(observation.hits),
                elapsed_ms=observation.elapsed_ms,
                timing="derived_diagnostic" if observation.derived else "inclusive",
            )
            for name, observation in self.observations.items()
        ]
        sets = {s.name: set(s.retained_anchor_ids) for s in stages}
        leaf = sets.get("bm25", set()) | sets.get("dense", set())
        rrf = sets.get("rrf_top20", set())
        diagnostics = {
            "missing_from_leaf_union": sorted(set(anchor_ids) - leaf)
            if leaf or "rrf_top20" in sets
            else [],
            "lost_after_rrf_top20": sorted(leaf - rrf) if "rrf_top20" in sets else [],
            "lost_after_rrf_top50": sorted(leaf - sets.get("rrf_top50", set()))
            if "rrf_top50" in sets
            else [],
            "lost_from_final_top20": sorted(rrf - sets["final_top20"]) if self.details else [],
        }
        if self.details:
            before = self.observations["hybrid"].hits
            after = self.observations["reranker_all"].hits
            diagnostics["demoted_by_reranker"] = [
                a
                for a, g in zip(anchor_ids, readable_gold, strict=True)
                if any(h.chunk_id in g for h in before)
                and any(h.chunk_id in g for h in after)
                and min(h.rank for h in after if h.chunk_id in g)
                > min(h.rank for h in before if h.chunk_id in g)
            ]
        inputs = self.reranker_inputs(anchor_ids, readable_gold, quotes)
        reranker_metadata: dict[str, str | float] = {}
        if self.details:
            reranker_metadata = {
                "model": self.details.model,
                "model_revision": self.details.model_revision,
                "tokenizer_revision": self.details.tokenizer_revision,
                "scoring_ms": self.details.scoring_ms,
                "token_inspection_ms": self.details.token_inspection_ms,
            }
        trace = QueryTrace(
            query_id=query_id,
            config_hash=config.config_hash(),
            config=config,
            gold=[
                GoldEvidence(anchor_id=a, chunk_ids=sorted(g))
                for a, g in zip(anchor_ids, readable_gold, strict=True)
            ],
            stages=stages,
            reranker_inputs=inputs,
            reranker_metadata=reranker_metadata,
            diagnostics=diagnostics,
        )
        self.queries.append(trace)
        self.input_candidates = []  # drop content as soon as visibility diagnostics are complete
        return trace

    def reranker_inputs(
        self, anchor_ids: list[str], gold: list[set[UUID]], quotes: Sequence[str]
    ) -> list[RerankerInput]:
        if self.details is None:
            return []
        upstream = {h.chunk_id: h for h in self.observations["hybrid"].hits}
        inputs = []
        for i, ((chunk_id, text), score, tokens) in enumerate(
            zip(self.input_candidates, self.details.scores, self.details.tokens, strict=True),
            start=1,
        ):
            if any(a < 0 or a > b or b > len(text) for a, b in tokens.document_visible_ranges):
                raise ValueError("model diagnostic offsets fall outside the authorized input")
            visible = " ".join(text[a:b] for a, b in tokens.document_visible_ranges)
            inputs.append(
                RerankerInput(
                    chunk_id=chunk_id,
                    input_rank=i,
                    upstream_rank=upstream[chunk_id].rank,
                    upstream_score=upstream[chunk_id].score,
                    score=score,
                    tokens=tokens,
                    anchors=[
                        VisibleAnchor(
                            anchor_id=a,
                            full_quote_visible=squash(q) in squash(visible),
                            label_match_visible=holds_quote(visible, q),
                        )
                        for a, g, q in zip(anchor_ids, gold, quotes, strict=True)
                        if chunk_id in g
                    ],
                )
            )
        return inputs
