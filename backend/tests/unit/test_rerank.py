"""The rerank stage, with fakes for the base search, the model and the database."""

from typing import Any
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.retrieval.protocols import RetrievalContext, SearchHit
from app.retrieval.rerank import RerankRetriever

FIRST = UUID(int=1)
SECOND = UUID(int=2)
GONE = UUID(int=3)
CONTEXT = RetrievalContext(uuid4(), uuid4(), frozenset({"public"}))


class Row:
    def __init__(self, chunk_id: UUID, text: str) -> None:
        self.id = chunk_id
        self.text = text


class FakeSession:
    """Returns the rows the ACL query would: GONE is never one of them."""

    async def __aenter__(self) -> "FakeSession":
        return self

    async def __aexit__(self, *args: object) -> None:
        return None

    async def execute(self, statement: Any) -> list[Row]:
        return [Row(FIRST, "first text"), Row(SECOND, "second text")]


class FakeBase:
    def __init__(self, *chunk_ids: UUID) -> None:
        self.chunk_ids = chunk_ids
        self.limits: list[int] = []

    async def search(self, query: str, *, context: RetrievalContext, limit: int) -> list[SearchHit]:
        self.limits.append(limit)
        return [
            SearchHit(chunk_id=chunk_id, score=0.0, rank=rank, method="hybrid")
            for rank, chunk_id in enumerate(self.chunk_ids, start=1)
        ]


class FakeReranker:
    def __init__(self) -> None:
        self.calls: list[tuple[str, list[tuple[UUID, str]], int]] = []

    async def rerank(
        self, query: str, candidates: list[tuple[UUID, str]], top_k: int
    ) -> list[SearchHit]:
        self.calls.append((query, candidates, top_k))
        return []


def retriever(base: FakeBase, reranker: FakeReranker) -> RerankRetriever:
    sessions: async_sessionmaker[AsyncSession] = FakeSession  # type: ignore[assignment]
    return RerankRetriever(base, reranker, sessions, top_n=20)


async def test_the_base_top_n_reaches_the_model_in_base_order() -> None:
    base = FakeBase(SECOND, FIRST)
    reranker = FakeReranker()

    await retriever(base, reranker).search("query", context=CONTEXT, limit=5)

    assert base.limits == [20]
    assert reranker.calls == [("query", [(SECOND, "second text"), (FIRST, "first text")], 5)]


async def test_a_chunk_the_acl_query_does_not_return_never_reaches_the_model() -> None:
    reranker = FakeReranker()

    await retriever(FakeBase(GONE, FIRST), reranker).search("query", context=CONTEXT, limit=5)

    assert reranker.calls[0][1] == [(FIRST, "first text")]
