"""The eval runner end to end on the fixture: grading, report, and the leak check."""

from uuid import uuid4

import pytest
from eval.runner.dataset import EvalItem
from eval.runner.retrieval import (
    CONFIGS,
    build_report,
    build_retriever,
    check,
    load_corpus,
    render_comparison,
    render_config,
    run_item,
)
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession, async_sessionmaker

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
}


class RecordingEmbedder:
    def __init__(self) -> None:
        self.queries: list[str] = []

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        raise AssertionError("search must embed only the query")

    async def embed_query(self, text: str) -> list[float]:
        self.queries.append(text)
        return fixed_embedding(text)


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


@pytest.mark.parametrize("name", ["fts", "bm25", "hybrid"])
async def test_a_config_runs_and_reports(connection: AsyncConnection, name: str) -> None:
    tenants = await create_two_tenants(connection)
    sessions = async_sessionmaker(
        bind=connection, class_=AsyncSession, join_transaction_mode="create_savepoint"
    )
    corpus = await load_corpus(sessions)
    config = CONFIGS[name]
    retriever = build_retriever(config, sessions, RecordingEmbedder())
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


async def test_a_quote_the_corpus_lacks_is_reported(connection: AsyncConnection) -> None:
    await create_two_tenants(connection)
    sessions = async_sessionmaker(
        bind=connection, class_=AsyncSession, join_transaction_mode="create_savepoint"
    )
    corpus = await load_corpus(sessions)
    wrong = item(str(uuid4()), relevant=[{"doc_id": "public", "page": 1, "quote": "not in it"}])
    assert len(check([wrong], corpus)) == 1
