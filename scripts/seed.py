"""Seed the fictional dev tenants and users (docs/SCHEMA.md §8). Safe to run repeatedly."""

import asyncio

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from app import db
from app.auth.passwords import hash_password
from app.config import get_settings
from app.models import Tenant, User

TENANTS = {
    "bluefin": "Bluefin Community Bank",
    "granite": "Granite Ridge Credit Union",
    "lumen": "Lumen Pay",
}
ROLES = ("admin", "investigator")


async def main() -> None:
    password = get_settings().seed_password
    if password is None:
        raise SystemExit("Set SEED_PASSWORD in .env first.")

    async with db.get_sessionmaker().begin() as session:
        await session.execute(
            insert(Tenant)
            .values([{"slug": slug, "name": name} for slug, name in TENANTS.items()])
            .on_conflict_do_nothing(index_elements=["slug"])
        )
        rows = await session.execute(select(Tenant.slug, Tenant.id).where(Tenant.slug.in_(TENANTS)))
        users = [
            {
                "tenant_id": tenant_id,
                "email": f"{role}@{slug}.example",
                "password_hash": hash_password(password.get_secret_value()),
                "role": role,
            }
            for slug, tenant_id in rows.all()
            for role in ROLES
        ]
        await session.execute(
            insert(User).values(users).on_conflict_do_nothing(constraint="users_email_unique")
        )
    await db.close()


if __name__ == "__main__":
    asyncio.run(main())
