import asyncio
from collections.abc import AsyncIterator

import httpx
import pytest

from app import cache, db, embedder
from app.api import health
from app.main import create_app


async def up() -> None:
    return None


async def down() -> None:
    raise ConnectionError("postgresql://user:secret@host/db")


async def hangs() -> None:
    await asyncio.sleep(60)


@pytest.fixture
async def client() -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=create_app())
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.mark.parametrize(
    ("db_check", "redis_check", "embedder_check", "code", "body"),
    [
        (up, up, up, 200, {"status": "ok", "db": "ok", "redis": "ok", "embedder": "ok"}),
        (
            down,
            up,
            up,
            503,
            {"status": "unavailable", "db": "error", "redis": "ok", "embedder": "ok"},
        ),
        (
            up,
            down,
            up,
            503,
            {"status": "unavailable", "db": "ok", "redis": "error", "embedder": "ok"},
        ),
        (
            hangs,
            up,
            up,
            503,
            {"status": "unavailable", "db": "error", "redis": "ok", "embedder": "ok"},
        ),
        (up, up, down, 200, {"status": "ok", "db": "ok", "redis": "ok", "embedder": "error"}),
        (up, up, hangs, 200, {"status": "ok", "db": "ok", "redis": "ok", "embedder": "error"}),
    ],
)
async def test_healthz_reports_each_dependency(
    client, monkeypatch, caplog, db_check, redis_check, embedder_check, code, body
) -> None:
    monkeypatch.setattr(db, "ping", db_check)
    monkeypatch.setattr(cache, "ping", redis_check)
    monkeypatch.setattr(embedder, "ping", embedder_check)
    monkeypatch.setattr(health, "CHECK_TIMEOUT_SECONDS", 0.01)

    response = await client.get("/healthz")

    assert response.status_code == code
    assert response.json() == body
    assert "secret" not in response.text
    assert "secret" not in caplog.text
