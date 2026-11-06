import os
import subprocess
import sys
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from argon2 import PasswordHasher
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncConnection, create_async_engine
from sqlalchemy.pool import NullPool

from app.models import Tenant, User

BACKEND_DIR = Path(__file__).resolve().parents[2]
PASSWORD = "test-only-password"
SLUGS = {"bluefin", "granite", "lumen"}


@pytest.fixture
async def committed(test_database_url: str) -> AsyncIterator[AsyncConnection]:
    """The seed script commits, so this test cleans up after itself."""
    engine = create_async_engine(test_database_url, poolclass=NullPool)
    async with engine.connect() as conn:
        yield conn
        await conn.rollback()
        await conn.execute(delete(User))
        await conn.execute(delete(Tenant))
        await conn.commit()
    await engine.dispose()


def run_seed(url: str) -> None:
    subprocess.run(
        [sys.executable, "../scripts/seed.py"],
        cwd=BACKEND_DIR,
        env={**os.environ, "DATABASE_URL": url, "SEED_PASSWORD": PASSWORD, "PYTHONPATH": "."},
        check=True,
    )


async def test_seed_creates_tenants_and_users_once(
    test_database_url: str, committed: AsyncConnection
) -> None:
    run_seed(test_database_url)
    run_seed(test_database_url)

    slugs = await committed.scalars(select(Tenant.slug))
    users = (await committed.execute(select(User.email, User.role, User.password_hash))).all()

    assert set(slugs) == SLUGS
    assert len(users) == 6
    assert {user.role for user in users} == {"admin", "investigator"}
    for user in users:
        assert PASSWORD not in user.password_hash
        assert PasswordHasher().verify(user.password_hash, PASSWORD)
