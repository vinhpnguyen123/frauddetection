"""Two tenants with one private chunk each, plus public and stale chunks.

Every chunk contains SHARED_TERM, so a search for it can only be narrowed by the ACL.
"""

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import insert
from sqlalchemy.ext.asyncio import AsyncConnection

from app.models import Chunk, Document, DocumentVersion, Tenant

SHARED_TERM = "structuring"
CANARY_A = "TENANTA-CANARY-7Q4M"
CANARY_B = "TENANTB-CANARY-9K2X"
PUBLIC_TEXT = "PUBLIC-GUIDANCE-3H8P"
STALE_TEXT = "STALE-GUIDANCE-5T1Z"


@dataclass(frozen=True)
class TwoTenants:
    tenant_a: UUID
    tenant_b: UUID


async def add_chunk(
    conn: AsyncConnection, key: str, marker: str, tenant_id: UUID | None, is_current: bool = True
) -> None:
    access_level = "tenant_private" if tenant_id else "public"
    document_id = await conn.scalar(
        insert(Document)
        .values(
            doc_key=key,
            title=key,
            source="synthetic",
            tenant_id=tenant_id,
            access_level=access_level,
        )
        .returning(Document.id)
    )
    version_id = await conn.scalar(
        insert(DocumentVersion)
        .values(
            document_id=document_id,
            version_no=1,
            content_hash=key,
            storage_key=key,
            authority="internal_policy",
            page_count=1,
            is_current=is_current,
        )
        .returning(DocumentVersion.id)
    )
    await conn.execute(
        insert(Chunk).values(
            version_id=version_id,
            document_id=document_id,
            tenant_id=tenant_id,
            access_level=access_level,
            is_current=is_current,
            ordinal=0,
            text=f"{SHARED_TERM} review policy ref {marker}",
            token_count=5,
            spans=[{"page": 1, "bbox": [0.0, 0.0, 1.0, 1.0]}],
            content_hash=key,
            embedding=[0.0] * 768,
        )
    )


async def create_two_tenants(conn: AsyncConnection) -> TwoTenants:
    tenant_a = await conn.scalar(
        insert(Tenant).values(slug="fixture-a", name="Fixture A").returning(Tenant.id)
    )
    tenant_b = await conn.scalar(
        insert(Tenant).values(slug="fixture-b", name="Fixture B").returning(Tenant.id)
    )
    await add_chunk(conn, "private-a", CANARY_A, tenant_a)
    await add_chunk(conn, "private-b", CANARY_B, tenant_b)
    await add_chunk(conn, "public", PUBLIC_TEXT, None)
    await add_chunk(conn, "stale", STALE_TEXT, None, is_current=False)
    return TwoTenants(tenant_a=tenant_a, tenant_b=tenant_b)
