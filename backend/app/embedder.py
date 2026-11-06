"""Reachability of the embedder service. The real client arrives in M2-S4."""

import httpx

from app.config import get_settings


async def ping() -> None:
    """Call the service's /healthz. Raises if it is unreachable or unhealthy."""
    async with httpx.AsyncClient() as client:
        response = await client.get(f"{get_settings().embedder_url}/healthz")
        response.raise_for_status()
