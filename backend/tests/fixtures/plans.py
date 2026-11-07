"""EXPLAIN for the exact statement a retriever runs."""

from typing import Any

from sqlalchemy import Select
from sqlalchemy.ext.asyncio import AsyncConnection


async def explain(connection: AsyncConnection, statement: Select[Any]) -> list[str]:
    """Return the plan lines. Driver-level SQL skips bind processing, so a vector goes as text."""
    compiled = statement.compile(
        dialect=connection.dialect, compile_kwargs={"render_postcompile": True}
    )
    values = (compiled.params[name] for name in compiled.positiontup or [])
    params = tuple(str(value) if isinstance(value, list) else value for value in values)
    plan = await connection.exec_driver_sql(f"EXPLAIN {compiled}", params)
    return [row[0] for row in plan]
