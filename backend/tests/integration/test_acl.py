"""Tenant isolation through a real retrieval path, against real Postgres."""

from collections.abc import Callable
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Select, func, select, text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession, async_sessionmaker

from app.models import Chunk
from app.retrieval.bm25 import Bm25Retriever, bm25_statement
from app.retrieval.fts import FtsRetriever, fts_statement
from app.retrieval.protocols import RetrievalContext, Retriever
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


@pytest.fixture(params=[FtsRetriever, Bm25Retriever], ids=["fts", "bm25"])
def retriever(connection: AsyncConnection, request: pytest.FixtureRequest) -> Retriever:
    """Every test below runs once per retrieval path."""
    sessions = async_sessionmaker(
        bind=connection, class_=AsyncSession, join_transaction_mode="create_savepoint"
    )
    build: Callable[..., Retriever] = request.param
    return build(sessions)


def context(tenant_id: UUID, levels: frozenset[str] = ALL_LEVELS) -> RetrievalContext:
    return RetrievalContext(user_id=uuid4(), tenant_id=tenant_id, allowed_access_levels=levels)


async def search_texts(
    connection: AsyncConnection, retriever: Retriever, query: str, ctx: RetrievalContext
) -> str:
    hits = await retriever.search(query, context=ctx, limit=50)
    ids = [hit.chunk_id for hit in hits]
    rows = await connection.scalars(select(Chunk.text).where(Chunk.id.in_(ids)))
    return "\n".join(rows)


async def conditions_in_plan(connection: AsyncConnection, statement: Select[Any]) -> str:
    """Return the plan lines where Postgres applies conditions, for the exact statement."""
    compiled = statement.compile(
        dialect=connection.dialect, compile_kwargs={"render_postcompile": True}
    )
    params = tuple(compiled.params[name] for name in compiled.positiontup or [])
    plan = await connection.exec_driver_sql(f"EXPLAIN {compiled}", params)
    lines = [row[0] for row in plan]
    return "\n".join(
        line
        for line in lines
        if any(k in line for k in ("Filter", "Index Cond", "Recheck Cond", "Tantivy Query"))
    )


async def test_fixture_would_leak_without_the_acl(
    connection: AsyncConnection, tenants: TwoTenants
) -> None:
    """Control: the shared term matches every chunk, so only the ACL can narrow the results."""
    matches = await connection.scalar(
        select(func.count()).where(Chunk.text.contains(SHARED_TERM)).select_from(Chunk)
    )
    assert matches == 4


async def test_tenant_a_never_sees_tenant_b(
    connection: AsyncConnection, tenants: TwoTenants, retriever: Retriever
) -> None:
    found = await search_texts(connection, retriever, SHARED_TERM, context(tenants.tenant_a))
    assert CANARY_A in found
    assert PUBLIC_TEXT in found
    assert CANARY_B not in found


async def test_tenant_b_never_sees_tenant_a(
    connection: AsyncConnection, tenants: TwoTenants, retriever: Retriever
) -> None:
    found = await search_texts(connection, retriever, SHARED_TERM, context(tenants.tenant_b))
    assert CANARY_B in found
    assert PUBLIC_TEXT in found
    assert CANARY_A not in found


async def test_searching_for_another_tenants_canary_never_returns_their_chunk(
    connection: AsyncConnection, tenants: TwoTenants, retriever: Retriever
) -> None:
    """Both canaries hold the word "canary", so under OR tenant A matches its own chunk."""
    own = await search_texts(connection, retriever, CANARY_B, context(tenants.tenant_b))
    other = await search_texts(connection, retriever, CANARY_B, context(tenants.tenant_a))
    assert CANARY_B in own
    assert CANARY_A not in own
    assert CANARY_B not in other
    assert CANARY_A in other


async def test_unknown_tenant_sees_only_public(
    connection: AsyncConnection, tenants: TwoTenants, retriever: Retriever
) -> None:
    found = await search_texts(connection, retriever, SHARED_TERM, context(uuid4()))
    assert PUBLIC_TEXT in found
    assert CANARY_A not in found
    assert CANARY_B not in found


async def test_public_only_context_hides_own_private_chunks(
    connection: AsyncConnection, tenants: TwoTenants, retriever: Retriever
) -> None:
    ctx = context(tenants.tenant_a, frozenset({"public"}))
    found = await search_texts(connection, retriever, SHARED_TERM, ctx)
    assert PUBLIC_TEXT in found
    assert CANARY_A not in found


async def test_private_only_context_hides_public_chunks(
    connection: AsyncConnection, tenants: TwoTenants, retriever: Retriever
) -> None:
    ctx = context(tenants.tenant_a, frozenset({"tenant_private"}))
    found = await search_texts(connection, retriever, SHARED_TERM, ctx)
    assert CANARY_A in found
    assert PUBLIC_TEXT not in found


async def test_empty_access_levels_match_nothing(tenants: TwoTenants, retriever: Retriever) -> None:
    ctx = context(tenants.tenant_a, frozenset())
    assert await retriever.search(SHARED_TERM, context=ctx, limit=50) == []


async def test_stale_chunks_are_never_returned(
    connection: AsyncConnection, tenants: TwoTenants, retriever: Retriever
) -> None:
    found = await search_texts(connection, retriever, SHARED_TERM, context(tenants.tenant_a))
    assert STALE_TEXT not in found


async def test_hits_are_ranked_and_respect_the_limit(
    tenants: TwoTenants, retriever: Retriever
) -> None:
    hits = await retriever.search(SHARED_TERM, context=context(tenants.tenant_a), limit=1)
    method = "fts" if isinstance(retriever, FtsRetriever) else "bm25"
    assert [(hit.rank, hit.method) for hit in hits] == [(1, method)]


@pytest.mark.parametrize("build", [fts_statement, bm25_statement], ids=["fts", "bm25"])
@pytest.mark.parametrize("force_index", [False, True], ids=["default_plan", "index_plan"])
async def test_explain_shows_the_acl_in_the_query(
    connection: AsyncConnection,
    tenants: TwoTenants,
    force_index: bool,
    build: Callable[..., Select[Any]],
) -> None:
    """The fixture is tiny, so the default plan is a seq scan; also force the index path."""
    if force_index:
        await connection.execute(text("SET LOCAL enable_seqscan = off"))
    statement = build(SHARED_TERM, context=context(tenants.tenant_a), limit=50)
    conditions = await conditions_in_plan(connection, statement)
    assert "is_current" in conditions
    assert "access_level" in conditions
    assert str(tenants.tenant_a) in conditions


async def test_a_term_missing_from_the_chunk_does_not_hide_it(
    connection: AsyncConnection, tenants: TwoTenants, retriever: Retriever
) -> None:
    query = f"{SHARED_TERM} zzzabsentterm"
    found = await search_texts(connection, retriever, query, context(tenants.tenant_a))
    assert CANARY_A in found
    assert CANARY_B not in found


async def test_a_minus_sign_does_not_match_unrelated_chunks(
    tenants: TwoTenants, retriever: Retriever
) -> None:
    """`-term` must stay a plain term: as a negation it would match every chunk without it."""
    query = "zzzabsentterm -yyyabsentterm"
    assert await retriever.search(query, context=context(tenants.tenant_a), limit=50) == []


async def test_a_minus_prefixed_term_still_matches(
    connection: AsyncConnection, tenants: TwoTenants, retriever: Retriever
) -> None:
    query = f"zzzabsentterm -{SHARED_TERM}"
    found = await search_texts(connection, retriever, query, context(tenants.tenant_a))
    assert CANARY_A in found
    assert CANARY_B not in found


async def test_quotes_do_not_require_the_whole_phrase(
    connection: AsyncConnection, tenants: TwoTenants, retriever: Retriever
) -> None:
    query = f'"{SHARED_TERM} zzzabsentterm"'
    found = await search_texts(connection, retriever, query, context(tenants.tenant_a))
    assert CANARY_A in found
    assert CANARY_B not in found


@pytest.mark.parametrize("query", ["the and of", ""], ids=["stopwords", "empty"])
async def test_a_query_without_terms_finds_nothing(
    tenants: TwoTenants, retriever: Retriever, query: str
) -> None:
    assert await retriever.search(query, context=context(tenants.tenant_a), limit=50) == []
