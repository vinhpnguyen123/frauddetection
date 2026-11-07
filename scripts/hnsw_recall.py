"""Measure HNSW recall@50 against exact search, for the queries of an eval set.

Usage: python scripts/hnsw_recall.py <set.jsonl>. Needs the stack and `make embedder` running.
"""

import asyncio
import json
import sys
from pathlib import Path
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import get_settings
from app.embedder import http_embedder
from app.models import Tenant
from app.retrieval.dense import DenseRetriever
from app.retrieval.protocols import Embedder, RetrievalContext

K = 50
LEVELS = frozenset({"public", "tenant_private"})


def recall(exact: set[UUID], approximate: set[UUID]) -> float:
    """Share of the exact hits that the approximate search also found. Nothing to find is 1."""
    return len(exact & approximate) / len(exact) if exact else 1.0


async def measure(
    queries: list[tuple[str, str]],
    sessions: async_sessionmaker[AsyncSession],
    embedder: Embedder,
) -> list[float]:
    """Return recall@K per (query, tenant slug), for that tenant's normal context."""
    exact = DenseRetriever(sessions, embedder, "exact")
    hnsw = DenseRetriever(sessions, embedder, "hnsw")
    async with sessions() as session:
        rows = await session.execute(select(Tenant.slug, Tenant.id))
        tenants = {row.slug: row.id for row in rows}
    results = []
    for query, tenant in queries:
        context = RetrievalContext(uuid4(), tenants[tenant], LEVELS)
        wanted = await exact.search(query, context=context, limit=K)
        found = await hnsw.search(query, context=context, limit=K)
        results.append(recall({h.chunk_id for h in wanted}, {h.chunk_id for h in found}))
    return results


async def run(path: Path) -> None:
    lines = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    engine = create_async_engine(get_settings().database_url)
    sessions = async_sessionmaker(engine, class_=AsyncSession)
    results = await measure(
        [(item["query"], item["ask_as_tenant"]) for item in lines], sessions, http_embedder()
    )
    await engine.dispose()
    print(f"queries={len(results)} mean_recall@{K}={sum(results) / len(results):.4f}", end=" ")
    print(f"min={min(results):.4f}")


if __name__ == "__main__":
    asyncio.run(run(Path(sys.argv[1])))
