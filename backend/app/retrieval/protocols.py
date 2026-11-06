"""Retrieval value objects and interfaces. Business logic depends on these, not on engines."""

from dataclasses import dataclass
from typing import Protocol
from uuid import UUID


@dataclass(frozen=True)
class RetrievalContext:
    """Who is searching. Every retrieval path must filter by this in SQL."""

    user_id: UUID
    tenant_id: UUID
    allowed_access_levels: frozenset[str]  # subset of {"public", "tenant_private"}


@dataclass(frozen=True)
class SearchHit:
    chunk_id: UUID
    score: float
    rank: int
    method: str  # "fts" | "bm25" | "dense_exact" | "dense_hnsw" | "hybrid" | "rerank"


class Retriever(Protocol):
    async def search(
        self, query: str, *, context: RetrievalContext, limit: int
    ) -> list[SearchHit]: ...


class Embedder(Protocol):
    async def embed_documents(self, texts: list[str]) -> list[list[float]]: ...

    async def embed_query(self, text: str) -> list[float]: ...


class Reranker(Protocol):
    async def rerank(
        self, query: str, candidates: list[tuple[UUID, str]], top_k: int
    ) -> list[SearchHit]: ...
