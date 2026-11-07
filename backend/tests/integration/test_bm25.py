"""BM25 behaviour the shared ACL tests cannot show: ranking must not depend on the ACL."""

from uuid import UUID, uuid4

import pytest
from sqlalchemy import Float, func, select, text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession, async_sessionmaker

from app.models import Chunk
from app.retrieval.acl import access_predicate
from app.retrieval.bm25 import Bm25Retriever, bm25_match
from app.retrieval.protocols import RetrievalContext
from tests.fixtures.two_tenants import SHARED_TERM, TwoTenants, add_chunk, create_two_tenants

ALL_LEVELS = frozenset({"public", "tenant_private"})
PRIVATE_ONLY = frozenset({"tenant_private"})


@pytest.fixture
async def tenants(connection: AsyncConnection) -> TwoTenants:
    """Public chunks of rising term frequency, plus a long private chunk that ranks last."""
    created = await create_two_tenants(connection)
    for count in range(1, 7):
        await add_chunk(connection, f"public-{count}", f"{SHARED_TERM} " * count, None)
    await add_chunk(connection, "weak-a", "filler " * 40, created.tenant_a)
    return created


@pytest.fixture
def retriever(connection: AsyncConnection) -> Bm25Retriever:
    sessions = async_sessionmaker(
        bind=connection, class_=AsyncSession, join_transaction_mode="create_savepoint"
    )
    return Bm25Retriever(sessions)


def context(tenant_id: UUID, levels: frozenset[str] = ALL_LEVELS) -> RetrievalContext:
    return RetrievalContext(user_id=uuid4(), tenant_id=tenant_id, allowed_access_levels=levels)


async def unfiltered_then_restricted(
    connection: AsyncConnection, ctx: RetrievalContext, limit: int
) -> list[tuple[UUID, float]]:
    """Search with no ACL at all, then keep the readable rows. The reference for the tests."""
    score = func.pdb.score(Chunk.id, type_=Float)
    rows = await connection.execute(
        select(Chunk.id, score)
        .where(bm25_match(SHARED_TERM))
        .order_by(score.desc(), Chunk.id)
        .limit(1000)
    )
    readable = set(await connection.scalars(select(Chunk.id).where(access_predicate(ctx))))
    return [(row[0], row[1]) for row in rows if row[0] in readable][:limit]


@pytest.mark.parametrize("levels", [ALL_LEVELS, PRIVATE_ONLY], ids=["all", "private_only"])
@pytest.mark.parametrize("limit", [1, 3, 100])
async def test_the_acl_loses_no_result_and_changes_no_score(
    connection: AsyncConnection,
    tenants: TwoTenants,
    retriever: Bm25Retriever,
    limit: int,
    levels: frozenset[str],
) -> None:
    """Fails if an ACL column joins the index: pg_search would score it as a search term."""
    ctx = context(tenants.tenant_a, levels)
    expected = await unfiltered_then_restricted(connection, ctx, limit)
    hits = await retriever.search(SHARED_TERM, context=ctx, limit=limit)
    assert expected
    assert [hit.chunk_id for hit in hits] == [chunk_id for chunk_id, _ in expected]
    assert [hit.score for hit in hits] == pytest.approx([score for _, score in expected])


async def test_a_private_chunk_that_ranks_last_is_still_found(
    connection: AsyncConnection, tenants: TwoTenants, retriever: Bm25Retriever
) -> None:
    """`LIMIT` must apply after the ACL, or a low-ranked readable chunk would vanish."""
    hits = await retriever.search(
        SHARED_TERM, context=context(tenants.tenant_a, PRIVATE_ONLY), limit=2
    )
    assert len(hits) == 2


async def test_the_acl_holds_under_a_generic_plan(
    connection: AsyncConnection, tenants: TwoTenants, retriever: Bm25Retriever
) -> None:
    """A generic plan keeps the tenant as a parameter instead of a value known at planning."""
    await connection.execute(text("SET LOCAL plan_cache_mode = force_generic_plan"))
    for tenant_id in (tenants.tenant_a, tenants.tenant_b):
        ctx = context(tenant_id)
        expected = await unfiltered_then_restricted(connection, ctx, 100)
        hits = await retriever.search(SHARED_TERM, context=ctx, limit=100)
        assert [hit.chunk_id for hit in hits] == [chunk_id for chunk_id, _ in expected]


async def test_a_dotted_identifier_stays_one_token(
    connection: AsyncConnection, tenants: TwoTenants, retriever: Bm25Retriever
) -> None:
    await add_chunk(connection, "cite", "31 CFR 1020.320", None)
    await add_chunk(connection, "numbers", "1020 and 320", None)
    hits = await retriever.search("1020.320", context=context(tenants.tenant_a), limit=10)
    assert len(hits) == 1
    found = await connection.scalar(select(Chunk.text).where(Chunk.id == hits[0].chunk_id))
    assert found is not None and "1020.320" in found


async def test_query_terms_are_stemmed(
    connection: AsyncConnection, tenants: TwoTenants, retriever: Bm25Retriever
) -> None:
    await add_chunk(connection, "owners", "beneficial owners", None)
    hits = await retriever.search("owner", context=context(tenants.tenant_a), limit=10)
    assert [(hit.rank, hit.method) for hit in hits] == [(1, "bm25")]
