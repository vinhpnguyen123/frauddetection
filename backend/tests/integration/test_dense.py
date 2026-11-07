"""Dense behaviour the shared ACL tests cannot show: the mode is real and HNSW loses nothing."""

import random
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import (
    AsyncConnection,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.retrieval.dense import MODE_SETTINGS, DenseMode, DenseRetriever, dense_statement
from app.retrieval.protocols import RetrievalContext
from tests.fixtures.plans import explain
from tests.fixtures.two_tenants import TwoTenants, add_chunk, create_two_tenants

ALL_LEVELS = frozenset({"public", "tenant_private"})
PRIVATE_ONLY = frozenset({"tenant_private"})
QUERY = [1.0] + [0.0] * 767
NEAR_CHUNKS = 150  # more than hnsw.ef_search, so one index pass cannot reach what lies beyond


class QueryEmbedder:
    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        raise AssertionError("search must embed only the query")

    async def embed_query(self, text: str) -> list[float]:
        return QUERY


def near(index: int) -> list[float]:
    """A vector in a tight cluster around QUERY, so the cluster fills every HNSW candidate list."""
    rng = random.Random(index)
    return [value + rng.uniform(-0.01, 0.01) for value in QUERY]


def context(tenant_id: UUID, levels: frozenset[str] = ALL_LEVELS) -> RetrievalContext:
    return RetrievalContext(user_id=uuid4(), tenant_id=tenant_id, allowed_access_levels=levels)


def retriever(connection: AsyncConnection, mode: DenseMode) -> DenseRetriever:
    sessions = async_sessionmaker(
        bind=connection, class_=AsyncSession, join_transaction_mode="create_savepoint"
    )
    return DenseRetriever(sessions, QueryEmbedder(), mode)


@pytest.fixture
async def tenants(connection: AsyncConnection) -> TwoTenants:
    """Many public chunks near QUERY; the private chunks keep their random, far embeddings."""
    created = await create_two_tenants(connection)
    for index in range(NEAR_CHUNKS):
        await add_chunk(connection, f"near-{index}", "near", None, embedding=near(index))
    # Rolled-back rows of earlier tests stay in the graph as dead entries and change the scan.
    await connection.execute(text("REINDEX INDEX chunks_embedding_hnsw"))
    return created


async def plan_for(connection: AsyncConnection, mode: DenseMode, tenant_id: UUID) -> str:
    for name, value in MODE_SETTINGS[mode].items():
        await connection.execute(select(func.set_config(name, value, True)))
    statement = dense_statement(QUERY, context=context(tenant_id), limit=50)
    return "\n".join(await explain(connection, statement))


async def test_hnsw_mode_uses_the_index(connection: AsyncConnection, tenants: TwoTenants) -> None:
    assert "chunks_embedding_hnsw" in await plan_for(connection, "hnsw", tenants.tenant_a)


async def test_exact_mode_avoids_the_index(
    connection: AsyncConnection, tenants: TwoTenants
) -> None:
    assert "chunks_embedding_hnsw" not in await plan_for(connection, "exact", tenants.tenant_a)


@pytest.mark.parametrize("mode", ["exact", "hnsw"])
async def test_a_readable_chunk_behind_many_others_is_found(
    connection: AsyncConnection, tenants: TwoTenants, mode: DenseMode
) -> None:
    """pgvector filters after the index scan; without iterative scan this returns nothing."""
    ctx = context(tenants.tenant_a, PRIVATE_ONLY)
    hits = await retriever(connection, mode).search("q", context=ctx, limit=5)
    assert len(hits) == 1


@pytest.mark.parametrize("mode", ["exact", "hnsw"])
async def test_a_top_50_is_filled_and_ordered_by_score(
    connection: AsyncConnection, tenants: TwoTenants, mode: DenseMode
) -> None:
    """One index pass may stop short of the limit; the settings must still fill it."""
    hits = await retriever(connection, mode).search(
        "q", context=context(tenants.tenant_a), limit=50
    )
    assert len(hits) == 50
    assert [hit.rank for hit in hits] == list(range(1, 51))
    assert [hit.score for hit in hits] == sorted((hit.score for hit in hits), reverse=True)
    assert {hit.method for hit in hits} == {f"dense_{mode}"}


async def test_settings_do_not_outlive_the_search(test_database_url: str) -> None:
    """One pooled connection and real commits: the next user of it must see the defaults."""
    engine = create_async_engine(test_database_url, pool_size=1, max_overflow=0)
    sessions = async_sessionmaker(engine, class_=AsyncSession)
    await DenseRetriever(sessions, QueryEmbedder(), "hnsw").search(
        "q", context=context(uuid4()), limit=5
    )
    async with sessions() as session:
        assert await session.scalar(select(func.current_setting("enable_seqscan"))) == "on"
        assert await session.scalar(select(func.current_setting("hnsw.iterative_scan"))) == "off"
    await engine.dispose()
