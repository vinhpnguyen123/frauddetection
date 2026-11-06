"""A fresh, fully migrated test database for each pytest run."""

import asyncio
import os
import subprocess
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from sqlalchemy import make_url, text
from sqlalchemy.ext.asyncio import AsyncConnection, create_async_engine
from sqlalchemy.pool import NullPool

from app.config import get_settings

BACKEND_DIR = Path(__file__).resolve().parents[2]


async def recreate_database(admin_url: str, name: str) -> None:
    engine = create_async_engine(admin_url, isolation_level="AUTOCOMMIT", poolclass=NullPool)
    async with engine.connect() as connection:
        await connection.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        await connection.execute(text(f'CREATE DATABASE "{name}"'))
    await engine.dispose()


def run_alembic(url: str, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["alembic", *args],
        cwd=BACKEND_DIR,
        env={**os.environ, "DATABASE_URL": url},
        capture_output=True,
        text=True,
    )


@pytest.fixture(scope="session")
def test_database_url() -> str:
    admin = make_url(get_settings().database_url)
    name = f"{admin.database}_test"
    url = admin.set(database=name).render_as_string(hide_password=False)
    asyncio.run(recreate_database(admin.render_as_string(hide_password=False), name))
    result = run_alembic(url, "upgrade", "head")
    assert result.returncode == 0, result.stderr
    return url


@pytest.fixture
async def connection(test_database_url: str) -> AsyncIterator[AsyncConnection]:
    """A connection whose transaction is rolled back, so tests leave nothing behind."""
    engine = create_async_engine(test_database_url, poolclass=NullPool)
    async with engine.connect() as conn:
        transaction = await conn.begin()
        yield conn
        await transaction.rollback()
    await engine.dispose()
