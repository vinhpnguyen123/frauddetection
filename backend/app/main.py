"""FastAPI application factory."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app import cache, db
from app.api import health
from app.config import get_settings


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    get_settings()  # fail at startup, not on the first request, if config is missing
    yield
    await asyncio.gather(db.close(), cache.close())


def create_app() -> FastAPI:
    """Build the API application."""
    app = FastAPI(title="FraudDetection", lifespan=lifespan)
    app.include_router(health.router)
    return app
