"""Client for the embedder service. Task prefixes are added by the service, never here."""

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any
from uuid import UUID

import httpx

from app.config import get_settings
from app.retrieval.protocols import SearchHit

EMBED_DIMENSIONS = 768  # chunks.embedding is vector(768)
EMBED_BATCH = 8  # measured on the 8 GB dev machine: faster and lighter than 16 or 32
TOKENS_BATCH = 256  # the service's MAX_BATCH
MAX_ATTEMPTS = 3
RETRYABLE_STATUS = {429, 500, 502, 503, 504}
TIMEOUT_SECONDS = 180.0  # the first call loads the model


async def ping() -> None:
    """Call the service's /healthz. Raises if it is unreachable or unhealthy."""
    async with httpx.AsyncClient() as client:
        response = await client.get(f"{get_settings().embedder_url}/healthz")
        response.raise_for_status()


class HttpEmbedder:
    """The Embedder and Reranker protocols over HTTP, plus token counting and the reranker name."""

    def __init__(
        self,
        client: httpx.AsyncClient,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self.client = client
        self.sleep = sleep

    async def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        for attempt in range(1, MAX_ATTEMPTS + 1):
            try:
                response = await self.client.post(path, json=payload)
            except httpx.TransportError:
                if attempt == MAX_ATTEMPTS:
                    raise
            else:
                if response.status_code not in RETRYABLE_STATUS or attempt == MAX_ATTEMPTS:
                    response.raise_for_status()
                    result: dict[str, Any] = response.json()
                    return result
            await self.sleep(2.0**attempt)
        raise AssertionError("unreachable: the last attempt returns or raises")

    async def _embed(self, texts: list[str], kind: str) -> list[list[float]]:
        vectors: list[list[float]] = []
        for start in range(0, len(texts), EMBED_BATCH):
            batch = texts[start : start + EMBED_BATCH]
            found = (await self._post("/embed", {"texts": batch, "kind": kind}))["embeddings"]
            if len(found) != len(batch) or any(len(v) != EMBED_DIMENSIONS for v in found):
                raise ValueError(f"expected {len(batch)} vectors of {EMBED_DIMENSIONS} dimensions")
            vectors += found
        return vectors

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return await self._embed(texts, "document")

    async def embed_query(self, text: str) -> list[float]:
        return (await self._embed([text], "query"))[0]

    async def count_tokens(self, texts: list[str]) -> list[int]:
        counts: list[int] = []
        for start in range(0, len(texts), TOKENS_BATCH):
            batch = texts[start : start + TOKENS_BATCH]
            counts += (await self._post("/tokens", {"texts": batch}))["counts"]
        return counts

    async def rerank(
        self, query: str, candidates: list[tuple[UUID, str]], top_k: int
    ) -> list[SearchHit]:
        """Return the best `top_k` by score; a tie goes to the lower chunk id."""
        if not candidates:
            return []
        documents = [text for _, text in candidates]
        scores = (await self._post("/rerank", {"query": query, "documents": documents}))["scores"]
        if len(scores) != len(candidates):
            raise ValueError(f"expected {len(candidates)} scores, got {len(scores)}")
        pairs = zip((chunk_id for chunk_id, _ in candidates), scores, strict=True)
        ordered = sorted(pairs, key=lambda pair: (-pair[1], pair[0]))[:top_k]
        return [
            SearchHit(chunk_id=chunk_id, score=score, rank=rank, method="rerank")
            for rank, (chunk_id, score) in enumerate(ordered, start=1)
        ]

    async def rerank_model(self) -> str:
        """Name the model the service is really running, so a report cannot name the wrong one."""
        response = await self.client.get("/healthz")
        response.raise_for_status()
        model: str = response.json()["rerank_model"]
        return model


def http_embedder(client: httpx.AsyncClient | None = None) -> HttpEmbedder:
    """Build the client from settings. The caller owns closing it."""
    return HttpEmbedder(
        client or httpx.AsyncClient(base_url=get_settings().embedder_url, timeout=TIMEOUT_SECONDS)
    )
