"""Tenant isolation through a real retrieval path, against real Postgres."""

from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession, async_sessionmaker

from app.models import Chunk
from app.retrieval.fts import FtsRetriever
from app.retrieval.protocols import RetrievalContext
from tests.fixtures.two_tenants import (
    CANARY_A,
    CANARY_B,
    PUBLIC_TEXT,
    SHARED_TERM,
    STALE_TEXT,
    TwoTenants,
    create_two_tenants,
)

ALL_LEVELS = frozenset({"public", "tenant_private"})


@pytest.fixture
async def tenants(connection: AsyncConnection) -> TwoTenants:
    return await create_two_tenants(connection)


@pytest.fixture
def retriever(connection: AsyncConnection) -> FtsRetriever:
    sessions = async_sessionmaker(
        bind=connection, class_=AsyncSession, join_transaction_mode="create_savepoint"
    )
    return FtsRetriever(sessions)


def context(tenant_id: UUID, levels: frozenset[str] = ALL_LEVELS) -> RetrievalContext:
    return RetrievalContext(user_id=uuid4(), tenant_id=tenant_id, allowed_access_levels=levels)


async def search_texts(
    connection: AsyncConnection, retriever: FtsRetriever, query: str, ctx: RetrievalContext
) -> str:
    hits = await retriever.search(query, context=ctx, limit=50)
    ids = [hit.chunk_id for hit in hits]
    rows = await connection.scalars(select(Chunk.text).where(Chunk.id.in_(ids)))
    return "\n".join(rows)


async def test_fixture_would_leak_without_the_acl(
    connection: AsyncConnection, tenants: TwoTenants
) -> None:
    """Control: the shared term matches every chunk, so only the ACL can narrow the results."""
    matches = await connection.scalar(
        select(func.count()).where(Chunk.text.contains(SHARED_TERM)).select_from(Chunk)
    )
    assert matches == 4


async def test_tenant_a_never_sees_tenant_b(
    connection: AsyncConnection, tenants: TwoTenants, retriever: FtsRetriever
) -> None:
    found = await search_texts(connection, retriever, SHARED_TERM, context(tenants.tenant_a))
    assert CANARY_A in found
    assert PUBLIC_TEXT in found
    assert CANARY_B not in found


async def test_tenant_b_never_sees_tenant_a(
    connection: AsyncConnection, tenants: TwoTenants, retriever: FtsRetriever
) -> None:
    found = await search_texts(connection, retriever, SHARED_TERM, context(tenants.tenant_b))
    assert CANARY_B in found
    assert PUBLIC_TEXT in found
    assert CANARY_A not in found


async def test_searching_for_another_tenants_canary_finds_nothing(
    tenants: TwoTenants, retriever: FtsRetriever
) -> None:
    own = await retriever.search(CANARY_B, context=context(tenants.tenant_b), limit=50)
    other = await retriever.search(CANARY_B, context=context(tenants.tenant_a), limit=50)
    assert len(own) == 1
    assert other == []


async def test_unknown_tenant_sees_only_public(
    connection: AsyncConnection, tenants: TwoTenants, retriever: FtsRetriever
) -> None:
    found = await search_texts(connection, retriever, SHARED_TERM, context(uuid4()))
    assert PUBLIC_TEXT in found
    assert CANARY_A not in found
    assert CANARY_B not in found


async def test_public_only_context_hides_own_private_chunks(
    connection: AsyncConnection, tenants: TwoTenants, retriever: FtsRetriever
) -> None:
    ctx = context(tenants.tenant_a, frozenset({"public"}))
    found = await search_texts(connection, retriever, SHARED_TERM, ctx)
    assert PUBLIC_TEXT in found
    assert CANARY_A not in found


async def test_private_only_context_hides_public_chunks(
    connection: AsyncConnection, tenants: TwoTenants, retriever: FtsRetriever
) -> None:
    ctx = context(tenants.tenant_a, frozenset({"tenant_private"}))
    found = await search_texts(connection, retriever, SHARED_TERM, ctx)
    assert CANARY_A in found
    assert PUBLIC_TEXT not in found


async def test_empty_access_levels_match_nothing(
    tenants: TwoTenants, retriever: FtsRetriever
) -> None:
    ctx = context(tenants.tenant_a, frozenset())
    assert await retriever.search(SHARED_TERM, context=ctx, limit=50) == []


async def test_stale_chunks_are_never_returned(
    connection: AsyncConnection, tenants: TwoTenants, retriever: FtsRetriever
) -> None:
    found = await search_texts(connection, retriever, SHARED_TERM, context(tenants.tenant_a))
    assert STALE_TEXT not in found


async def test_hits_are_ranked_and_respect_the_limit(
    tenants: TwoTenants, retriever: FtsRetriever
) -> None:
    hits = await retriever.search(SHARED_TERM, context=context(tenants.tenant_a), limit=1)
    assert [(hit.rank, hit.method) for hit in hits] == [(1, "fts")]
