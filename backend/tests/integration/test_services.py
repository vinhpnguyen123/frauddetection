"""Runs against the real ParadeDB and Redis: `make up` locally, service containers in CI."""

from collections.abc import AsyncIterator

import httpx
import pytest
from sqlalchemy import text

from app import cache, db
from app.main import create_app


@pytest.fixture(autouse=True)
async def close_connections() -> AsyncIterator[None]:
    yield
    # Each test has its own event loop; pooled connections must not outlive it.
    await db.close()
    await cache.close()


async def test_healthz_is_ok_against_real_services() -> None:
    transport = httpx.ASGITransport(app=create_app())
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "db": "ok", "redis": "ok"}


async def test_database_is_paradedb_with_required_extensions() -> None:
    query = text("SELECT name FROM pg_available_extensions WHERE name IN ('vector', 'pg_search')")
    async with db.get_engine().connect() as connection:
        names = set((await connection.execute(query)).scalars())

    assert names == {"vector", "pg_search"}
