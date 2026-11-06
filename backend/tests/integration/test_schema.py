"""The migrated database matches docs/SCHEMA.md and rejects what the schema forbids."""

from uuid import UUID

import pytest
from sqlalchemy import insert, text, update
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncConnection

from app.models import Chunk, Document, DocumentVersion, IngestionJob, Tenant, User

from .conftest import run_alembic

TABLES = {
    "tenants",
    "users",
    "documents",
    "document_versions",
    "sections",
    "chunks",
    "ingestion_jobs",
    "saved_answers",
}
ENUMS = {
    "user_role": ["investigator", "admin"],
    "access_level": ["public", "tenant_private"],
    "doc_status": ["active", "rescinded", "superseded"],
    "doc_authority": [
        "regulation",
        "supervisory_guidance",
        "advisory",
        "industry_standard",
        "internal_policy",
    ],
    "job_status": ["pending", "running", "succeeded", "failed"],
    "job_source": ["manifest", "upload"],
}
INDEXES = {
    "dv_one_current",
    "saved_answers_owner",
    "chunks_acl",
    "chunks_embedding_hnsw",
    "chunks_fts",
}


async def add_tenant(conn: AsyncConnection, slug: str = "bluefin") -> UUID:
    return await conn.scalar(insert(Tenant).values(slug=slug, name=slug).returning(Tenant.id))


async def add_document(conn: AsyncConnection, tenant_id: UUID | None, key: str = "d1") -> UUID:
    return await conn.scalar(
        insert(Document)
        .values(
            doc_key=key,
            title="t",
            source="synthetic",
            tenant_id=tenant_id,
            access_level="tenant_private" if tenant_id else "public",
        )
        .returning(Document.id)
    )


async def add_version(
    conn: AsyncConnection, document_id: UUID, number: int = 1, is_current: bool = False
) -> UUID:
    return await conn.scalar(
        insert(DocumentVersion)
        .values(
            document_id=document_id,
            version_no=number,
            content_hash=f"h{number}",
            storage_key="k",
            authority="internal_policy",
            page_count=1,
            is_current=is_current,
        )
        .returning(DocumentVersion.id)
    )


def chunk_values(version_id: UUID, document_id: UUID, **acl: object) -> dict[str, object]:
    return {
        "version_id": version_id,
        "document_id": document_id,
        "ordinal": 0,
        "text": "structuring cash deposits",
        "token_count": 3,
        "spans": [{"page": 1, "bbox": [0.0, 0.0, 1.0, 1.0]}],
        "content_hash": "c",
        "embedding": [0.0] * 768,
        **acl,
    }


async def test_tables_enums_and_indexes_match_schema(connection: AsyncConnection) -> None:
    tables = await connection.scalars(
        text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
    )
    assert set(tables) - {"alembic_version", "spatial_ref_sys"} == TABLES

    rows = await connection.execute(
        text(
            "SELECT t.typname, array_agg(e.enumlabel::text ORDER BY e.enumsortorder) "
            "FROM pg_type t JOIN pg_enum e ON e.enumtypid = t.oid "
            # Extensions such as pg_search bring their own enums.
            "WHERE NOT EXISTS ("
            "SELECT 1 FROM pg_depend d WHERE d.objid = t.oid AND d.deptype = 'e'"
            ") "
            "GROUP BY t.typname"
        )
    )
    assert dict(rows.all()) == ENUMS

    indexes = await connection.scalars(
        text("SELECT indexname FROM pg_indexes WHERE schemaname = 'public'")
    )
    assert INDEXES <= set(indexes)


async def test_extensions_are_installed(connection: AsyncConnection) -> None:
    names = await connection.scalars(text("SELECT extname FROM pg_extension"))
    assert {"vector", "pg_search"} <= set(names)


def test_orm_matches_migrations(test_database_url: str) -> None:
    result = run_alembic(test_database_url, "check")
    assert result.returncode == 0, result.stdout + result.stderr


def test_migrating_again_changes_nothing(test_database_url: str) -> None:
    result = run_alembic(test_database_url, "upgrade", "head")
    assert result.returncode == 0, result.stderr


async def test_public_document_with_tenant_is_rejected(connection: AsyncConnection) -> None:
    tenant_id = await add_tenant(connection)
    with pytest.raises(IntegrityError, match="documents_acl_shape"):
        await connection.execute(
            insert(Document).values(
                doc_key="d", title="t", source="s", tenant_id=tenant_id, access_level="public"
            )
        )


async def test_private_document_without_tenant_is_rejected(connection: AsyncConnection) -> None:
    with pytest.raises(IntegrityError, match="documents_acl_shape"):
        await connection.execute(
            insert(Document).values(
                doc_key="d", title="t", source="s", tenant_id=None, access_level="tenant_private"
            )
        )


async def test_public_chunk_with_tenant_is_rejected(connection: AsyncConnection) -> None:
    tenant_id = await add_tenant(connection)
    document_id = await add_document(connection, tenant_id)
    version_id = await add_version(connection, document_id)
    with pytest.raises(IntegrityError, match="chunks_acl_shape"):
        await connection.execute(
            insert(Chunk).values(
                chunk_values(version_id, document_id, tenant_id=tenant_id, access_level="public")
            )
        )


async def test_private_chunk_without_tenant_is_rejected(connection: AsyncConnection) -> None:
    tenant_id = await add_tenant(connection)
    document_id = await add_document(connection, tenant_id)
    version_id = await add_version(connection, document_id)
    with pytest.raises(IntegrityError, match="chunks_acl_shape"):
        await connection.execute(
            insert(Chunk).values(
                chunk_values(version_id, document_id, tenant_id=None, access_level="tenant_private")
            )
        )


async def test_chunk_with_unknown_tenant_is_rejected(connection: AsyncConnection) -> None:
    tenant_id = await add_tenant(connection)
    document_id = await add_document(connection, tenant_id)
    version_id = await add_version(connection, document_id)
    unknown = UUID(int=1)
    with pytest.raises(IntegrityError, match="chunks_tenant_id_fkey"):
        await connection.execute(
            insert(Chunk).values(
                chunk_values(
                    version_id, document_id, tenant_id=unknown, access_level="tenant_private"
                )
            )
        )


async def test_chunk_round_trip_fills_fts(connection: AsyncConnection) -> None:
    document_id = await add_document(connection, None)
    version_id = await add_version(connection, document_id)
    fts = await connection.scalar(
        insert(Chunk)
        .values(chunk_values(version_id, document_id, tenant_id=None, access_level="public"))
        .returning(Chunk.fts)
    )
    assert "structur" in fts


async def test_duplicate_public_doc_key_is_rejected(connection: AsyncConnection) -> None:
    await add_document(connection, None, key="same")
    with pytest.raises(IntegrityError, match="documents_key_unique"):
        await add_document(connection, None, key="same")


async def test_same_doc_key_in_two_tenants_is_allowed(connection: AsyncConnection) -> None:
    first = await add_tenant(connection, "bluefin")
    second = await add_tenant(connection, "granite")
    await add_document(connection, first, key="same")
    await add_document(connection, second, key="same")


async def test_duplicate_public_job_is_rejected(connection: AsyncConnection) -> None:
    values = {"source": "manifest", "doc_key": "d", "content_hash": "h", "storage_key": "k"}
    await connection.execute(insert(IngestionJob).values(values))
    with pytest.raises(IntegrityError, match="jobs_idempotent"):
        await connection.execute(insert(IngestionJob).values(values))


async def test_two_current_versions_are_rejected(connection: AsyncConnection) -> None:
    document_id = await add_document(connection, None)
    await add_version(connection, document_id, 1, is_current=True)
    with pytest.raises(IntegrityError, match="dv_one_current"):
        await add_version(connection, document_id, 2, is_current=True)


async def test_current_version_foreign_key_works(connection: AsyncConnection) -> None:
    document_id = await add_document(connection, None)
    version_id = await add_version(connection, document_id, is_current=True)
    await connection.execute(
        update(Document).where(Document.id == document_id).values(current_version_id=version_id)
    )


async def test_uppercase_email_is_rejected(connection: AsyncConnection) -> None:
    tenant_id = await add_tenant(connection)
    with pytest.raises(IntegrityError, match="users_email_lower"):
        await connection.execute(
            insert(User).values(tenant_id=tenant_id, email="A@x.io", password_hash="h")
        )


async def test_unknown_access_level_is_rejected(connection: AsyncConnection) -> None:
    with pytest.raises(DBAPIError, match="access_level"):
        await connection.execute(
            text(
                "INSERT INTO documents (doc_key, title, source, access_level) "
                "VALUES ('d', 't', 's', 'restricted')"
            )
        )
