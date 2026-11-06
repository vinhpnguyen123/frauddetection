"""Redis client."""

from functools import lru_cache

from redis.asyncio import Redis

from app.config import get_settings


@lru_cache
def get_redis() -> Redis:
    """Return the process-wide client, created on first use."""
    return Redis.from_url(get_settings().redis_url)


async def ping() -> None:
    """Ping Redis. Raises if it is unreachable."""
    await get_redis().ping()


async def close() -> None:
    """Close pooled connections."""
    await get_redis().aclose()
