"""Alembic entrypoint. The database URL comes from Settings, never from alembic.ini."""

import asyncio

from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from alembic import context
from app.config import get_settings
from app.models import Base


def include_name(name: str | None, type_: str, _: object) -> bool:
    # Owned by the PostGIS extension in the ParadeDB image, not by this schema.
    return not (type_ == "table" and name == "spatial_ref_sys")


def run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=Base.metadata,
        include_name=include_name,
    )
    with context.begin_transaction():
        context.run_migrations()


async def main() -> None:
    engine = create_async_engine(get_settings().database_url, poolclass=NullPool)
    async with engine.connect() as connection:
        await connection.run_sync(run_migrations)
        await connection.commit()
    await engine.dispose()


asyncio.run(main())
