"""Async database engine and sessions."""

from functools import lru_cache

from sqlalchemy import literal, select
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import get_settings


@lru_cache
def get_engine() -> AsyncEngine:
    """Return the process-wide engine, created on first use."""
    return create_async_engine(get_settings().database_url, pool_pre_ping=True)


@lru_cache
def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    """Return the session factory bound to the process-wide engine."""
    return async_sessionmaker(get_engine(), expire_on_commit=False)


async def ping() -> None:
    """Run a trivial query. Raises if the database is unreachable."""
    async with get_engine().connect() as connection:
        await connection.execute(select(literal(1)))


async def close() -> None:
    """Close pooled connections. The engine stays usable afterwards."""
    await get_engine().dispose()
