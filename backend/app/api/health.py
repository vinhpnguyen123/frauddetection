"""Liveness of the services the API depends on."""

import asyncio
import logging
from collections.abc import Awaitable, Callable

from fastapi import APIRouter, Response, status

from app import cache, db, embedder

logger = logging.getLogger(__name__)
router = APIRouter()

CHECK_TIMEOUT_SECONDS = 2.0


async def _is_up(name: str, check: Callable[[], Awaitable[None]]) -> bool:
    try:
        async with asyncio.timeout(CHECK_TIMEOUT_SECONDS):
            await check()
    except Exception as exc:  # any failure means "down"; healthz must answer, not raise
        # Only the type: driver messages can contain the connection URL and its password.
        logger.warning("healthz: %s check failed (%s)", name, type(exc).__name__)
        return False
    return True


@router.get("/healthz")
async def healthz(response: Response) -> dict[str, str]:
    """Return 200 when the database and Redis respond, else 503. Never exposes error details.

    The embedder is reported but does not affect the status: it runs natively in dev and is
    not needed for the API to start.
    """
    db_up, redis_up, embedder_up = await asyncio.gather(
        _is_up("db", db.ping),
        _is_up("redis", cache.ping),
        _is_up("embedder", embedder.ping),
    )
    if not (db_up and redis_up):
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return {
        "status": "ok" if db_up and redis_up else "unavailable",
        "db": "ok" if db_up else "error",
        "redis": "ok" if redis_up else "error",
        "embedder": "ok" if embedder_up else "error",
    }
