"""The eval runner end to end on the fixture: grading, report, and the leak check."""

from uuid import UUID, uuid4

import pytest
from eval.runner.dataset import EvalItem
from eval.runner.retrieval import (
    CONFIGS,
    blocking_problems,
    build_report,
    build_retriever,
    check,
    load_corpus,
    render_comparison,
    render_config,
    resolve_config,
    run_item,
)
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession, async_sessionmaker

from app.retrieval.protocols import SearchHit
from tests.fixtures.two_tenants import (
    CANARY_B,
    PUBLIC_TEXT,
    SHARED_TERM,
    create_two_tenants,
    fixed_embedding,
)

META: dict[str, object] = {
    "set": "fixture",
    "set_size": 2,
    "date": "2026-11-07",
    "git_sha": "abc1234",
    "corpus": "fixture",
    "labels": "fixture",
    "chunks_over_rerank_limit": 0,
    "unmatched_anchors": 0,
}


class RecordingEmbedder:
    def __init__(self) -> None:
        self.queries: list[str] = []

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        raise AssertionError("search must embed only the query")

    async def embed_query(self, text: str) -> list[float]:
        self.queries.append(text)
        return fixed_embedding(text)

    async def rerank(
        self, query: str, candidates: list[tuple[UUID, str]], top_k: int
    ) -> list[SearchHit]:
        return [
            SearchHit(chunk_id=chunk_id, score=0.0, rank=rank, method="rerank")
            for rank, (chunk_id, _) in enumerate(candidates[:top_k], start=1)
        ]

    async def rerank_model(self) -> str:
        return "service/model"


def item(item_id: str, **changes: object) -> EvalItem:
    fields: dict[str, object] = {
        "id": item_id,
        "query": SHARED_TERM,
        "answerable": True,
        "category": "identifier",
        "data_kind": "real",
        "ask_as_tenant": "fixture-a",
        "relevant": [{"doc_id": "public", "page": 1, "quote": f"review policy ref {PUBLIC_TEXT}"}],
    }
    return EvalItem.model_validate(fields | changes)


@pytest.mark.parametrize("name", ["fts", "bm25", "hybrid", "rerank_top20"])
async def test_a_config_runs_and_reports(connection: AsyncConnection, name: str) -> None:
    tenants = await create_two_tenants(connection)
    sessions = async_sessionmaker(
        bind=connection, class_=AsyncSession, join_transaction_mode="create_savepoint"
    )
    corpus = await load_corpus(sessions)
    config = CONFIGS[name]
    embedder = RecordingEmbedder()
    retriever = build_retriever(config, sessions, embedder, embedder)
    refusal = item(
        "dev-002",
        answerable=False,
        relevant=[],
        category=None,
        expected_refusal="insufficient_evidence",
        must_not_contain=[CANARY_B],
    )
    results = [
        await run_item(entry, config, retriever, tenants.tenant_a, corpus)
        for entry in (item("dev-001"), refusal)
    ]
    assert not check([item("dev-001")], corpus)

    report = build_report(name, config, results, META)
    real = report["real"]
    assert isinstance(real, dict)
    assert real["n"] == 1  # the refusal item is not in the denominator
    assert real["recall_at_20"]["mean"] == 1.0
    assert report["leaks"] == []
    assert "real / identifier" in render_config(report)
    assert name in render_comparison([report], {"all items": 1.0})


async def test_the_runner_keeps_expansion_away_from_the_hybrid_dense_path(
    connection: AsyncConnection,
) -> None:
    tenants = await create_two_tenants(connection)
    sessions = async_sessionmaker(
        bind=connection, class_=AsyncSession, join_transaction_mode="create_savepoint"
    )
    corpus = await load_corpus(sessions)
    config = CONFIGS["hybrid"]
    embedder = RecordingEmbedder()
    retriever = build_retriever(config, sessions, embedder)

    await run_item(item("dev-001", query="SAR"), config, retriever, tenants.tenant_a, corpus)

    assert embedder.queries == ["SAR"]


async def test_a_rerank_config_records_the_model_the_service_runs() -> None:
    config = await resolve_config("rerank_top20", RecordingEmbedder())  # type: ignore[arg-type]
    assert config.rerank_model == "service/model"
    assert config.config_hash() != CONFIGS["rerank_top20"].config_hash()


async def test_other_configs_never_ask_for_a_rerank_model() -> None:
    assert await resolve_config("bm25", None) is CONFIGS["bm25"]  # type: ignore[arg-type]


def test_a_duplicate_passage_stops_even_a_chunking_experiment() -> None:
    quote = "the same passage quoted twice by one item, long enough to count as the same passage"
    anchor = {"doc_id": "public", "page": 1, "quote": quote}
    twice = item("dev-001", relevant=[anchor, anchor])
    assert len(blocking_problems([twice], {}, allow_unmatched=True)) == 1


async def test_only_a_chunking_experiment_may_lose_an_anchor(connection: AsyncConnection) -> None:
    await create_two_tenants(connection)
    sessions = async_sessionmaker(
        bind=connection, class_=AsyncSession, join_transaction_mode="create_savepoint"
    )
    corpus = await load_corpus(sessions)
    lost = item("dev-001", relevant=[{"doc_id": "public", "page": 1, "quote": "not in it"}])
    assert blocking_problems([lost], corpus, allow_unmatched=True) == []
    assert len(blocking_problems([lost], corpus, allow_unmatched=False)) == 1


async def test_a_quote_the_corpus_lacks_is_reported(connection: AsyncConnection) -> None:
    await create_two_tenants(connection)
    sessions = async_sessionmaker(
        bind=connection, class_=AsyncSession, join_transaction_mode="create_savepoint"
    )
    corpus = await load_corpus(sessions)
    wrong = item(str(uuid4()), relevant=[{"doc_id": "public", "page": 1, "quote": "not in it"}])
    assert len(check([wrong], corpus)) == 1
