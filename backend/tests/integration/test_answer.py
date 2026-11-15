"""The answer path against real Postgres: the LLM only ever sees what the context may read."""

from typing import Any
from uuid import uuid4

import pytest
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncConnection

from app.generation.answer import answer_question
from app.generation.llm import FakeLLMProvider
from app.models import Chunk
from app.retrieval.config import RetrievalConfig
from app.retrieval.evidence import evidence_statement, load_evidence
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
from tests.integration.test_acl import ALL_LEVELS, conditions_in_plan, sessions_for

CONFIG = RetrievalConfig(method="fts", final_k=5)


@pytest.fixture
async def tenants(connection: AsyncConnection) -> TwoTenants:
    return await create_two_tenants(connection)


class RecordingLLM(FakeLLMProvider):
    """Keeps every prompt it was sent, so a test can search it for the other tenant's canary."""

    def __init__(self, responses: list[dict[str, Any]]) -> None:
        super().__init__(responses)
        self.prompts: list[str] = []

    async def generate_json(
        self, *, system: str, user: str, schema: type[BaseModel], temperature: float = 0.0
    ) -> BaseModel:
        self.prompts.append(system + user)
        return await super().generate_json(
            system=system, user=user, schema=schema, temperature=temperature
        )


def claim(*citations: str) -> dict[str, Any]:
    return {
        "type": "answer",
        "claims": [{"text": "c", "citations": list(citations)}],
        "refusal": None,
    }


def context(tenant_id: Any, levels: frozenset[str] = ALL_LEVELS) -> RetrievalContext:
    return RetrievalContext(user_id=uuid4(), tenant_id=tenant_id, allowed_access_levels=levels)


async def ask(connection: AsyncConnection, llm: RecordingLLM, ctx: RetrievalContext) -> Any:
    sessions = sessions_for(connection)
    return await answer_question(
        SHARED_TERM,
        context=ctx,
        retriever=FtsRetriever(sessions),
        llm=llm,
        sessions=sessions,
        config=CONFIG,
    )


async def test_prompt_for_tenant_a_never_holds_tenant_b_text(
    connection: AsyncConnection, tenants: TwoTenants
) -> None:
    llm = RecordingLLM([claim("E1")])
    await ask(connection, llm, context(tenants.tenant_a))
    prompt = "\n".join(llm.prompts)
    assert CANARY_A in prompt and PUBLIC_TEXT in prompt
    assert CANARY_B not in prompt
    assert STALE_TEXT not in prompt


async def test_citations_point_to_readable_chunks(
    connection: AsyncConnection, tenants: TwoTenants
) -> None:
    llm = RecordingLLM([claim("E1", "E2")])
    answer = await ask(connection, llm, context(tenants.tenant_b))
    cited = [c.chunk_id for c in answer.claims[0].citations]
    texts = list(await connection.scalars(select(Chunk.text).where(Chunk.id.in_(cited))))
    assert len(texts) == 2
    assert all(CANARY_A not in text for text in texts)


async def test_invalid_citation_is_retried_once_with_feedback(
    connection: AsyncConnection, tenants: TwoTenants
) -> None:
    llm = RecordingLLM([claim("E9"), claim("E1")])
    answer = await ask(connection, llm, context(tenants.tenant_a))
    assert len(llm.prompts) == 2
    assert "cites labels that do not exist: ['E9']" in llm.prompts[1]
    assert answer.retried and answer.dropped_claims == 0 and len(answer.claims) == 1


async def test_claim_still_invalid_after_retry_is_dropped(
    connection: AsyncConnection, tenants: TwoTenants
) -> None:
    llm = RecordingLLM([claim("E9"), claim("E9")])
    answer = await ask(connection, llm, context(tenants.tenant_a))
    assert len(llm.prompts) == 2
    assert answer.claims == [] and answer.dropped_claims == 1


async def test_no_readable_evidence_refuses_without_calling_the_llm(
    connection: AsyncConnection, tenants: TwoTenants
) -> None:
    llm = RecordingLLM([])
    answer = await ask(connection, llm, context(tenants.tenant_a, frozenset()))
    assert llm.prompts == []
    assert answer.type == "refusal" and answer.refusal.code == "insufficient_evidence"


async def test_load_evidence_skips_ids_the_context_cannot_read(
    connection: AsyncConnection, tenants: TwoTenants
) -> None:
    ids = list(await connection.scalars(select(Chunk.id)))
    found = await load_evidence(
        sessions_for(connection), ids, context=context(tenants.tenant_a), parent_expansion=False
    )
    texts = "\n".join(item.text for item in found)
    assert CANARY_A in texts and PUBLIC_TEXT in texts
    assert CANARY_B not in texts and STALE_TEXT not in texts


async def test_explain_shows_the_acl_in_the_evidence_query(
    connection: AsyncConnection, tenants: TwoTenants
) -> None:
    statement = evidence_statement([uuid4()], context=context(tenants.tenant_a))
    conditions = await conditions_in_plan(connection, statement)
    assert "is_current" in conditions
    assert "access_level" in conditions
    assert str(tenants.tenant_a) in conditions
