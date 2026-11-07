"""ORM models. docs/SCHEMA.md is the source of truth; `alembic check` guards against drift."""

from datetime import date, datetime
from typing import Any
from uuid import UUID

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    CheckConstraint,
    Computed,
    ForeignKey,
    Index,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, ENUM, JSONB, TEXT, TIMESTAMP, TSVECTOR
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# Types are created by the migration, so the ORM must not try to create them.
UserRole = ENUM("investigator", "admin", name="user_role", create_type=False)
AccessLevel = ENUM("public", "tenant_private", name="access_level", create_type=False)
DocStatus = ENUM("active", "rescinded", "superseded", name="doc_status", create_type=False)
DocAuthority = ENUM(
    "regulation",
    "supervisory_guidance",
    "advisory",
    "industry_standard",
    "internal_policy",
    name="doc_authority",
    create_type=False,
)
JobStatus = ENUM("pending", "running", "succeeded", "failed", name="job_status", create_type=False)
JobSource = ENUM("manifest", "upload", name="job_source", create_type=False)

Timestamp = TIMESTAMP(timezone=True)
BM25_TOKENIZER = "pdb.unicode_words('stemmer=english', 'stopwords_language=English')"
ACL_SHAPE = (
    "(access_level = 'public' AND tenant_id IS NULL) OR "
    "(access_level = 'tenant_private' AND tenant_id IS NOT NULL)"
)


class Base(DeclarativeBase):
    type_annotation_map = {str: TEXT}


def primary_key() -> Mapped[UUID]:
    return mapped_column(primary_key=True, server_default=func.gen_random_uuid())


def created_at() -> Mapped[datetime]:
    return mapped_column(Timestamp, server_default=func.now())


class Tenant(Base):
    __tablename__ = "tenants"

    id: Mapped[UUID] = primary_key()
    slug: Mapped[str] = mapped_column(unique=True)
    name: Mapped[str]
    created_at: Mapped[datetime] = created_at()


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("email = lower(email)", name="users_email_lower"),
        UniqueConstraint("email", name="users_email_unique"),
    )

    id: Mapped[UUID] = primary_key()
    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id"))
    email: Mapped[str]
    password_hash: Mapped[str]
    role: Mapped[str] = mapped_column(UserRole, server_default="investigator")
    is_active: Mapped[bool] = mapped_column(server_default=text("true"))
    created_at: Mapped[datetime] = created_at()


class Document(Base):
    __tablename__ = "documents"
    __table_args__ = (
        CheckConstraint(ACL_SHAPE, name="documents_acl_shape"),
        UniqueConstraint(
            "tenant_id",
            "doc_key",
            name="documents_key_unique",
            postgresql_nulls_not_distinct=True,
        ),
    )

    id: Mapped[UUID] = primary_key()
    doc_key: Mapped[str]
    title: Mapped[str]
    source: Mapped[str]
    collections: Mapped[list[str]] = mapped_column(ARRAY(TEXT), server_default="{}")
    tenant_id: Mapped[UUID | None] = mapped_column(ForeignKey("tenants.id"))
    access_level: Mapped[str] = mapped_column(AccessLevel)
    # use_alter: documents and document_versions reference each other.
    current_version_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("document_versions.id", name="documents_current_fk", use_alter=True)
    )
    created_at: Mapped[datetime] = created_at()


class DocumentVersion(Base):
    __tablename__ = "document_versions"
    __table_args__ = (
        UniqueConstraint("document_id", "version_no", name="dv_no_unique"),
        UniqueConstraint("document_id", "content_hash", name="dv_hash_unique"),
        Index(
            "dv_one_current",
            "document_id",
            unique=True,
            postgresql_where=text("is_current"),
        ),
    )

    id: Mapped[UUID] = primary_key()
    document_id: Mapped[UUID] = mapped_column(ForeignKey("documents.id"))
    version_no: Mapped[int]
    content_hash: Mapped[str]
    storage_key: Mapped[str]
    source_url: Mapped[str | None]
    published_date: Mapped[date | None]
    status: Mapped[str] = mapped_column(DocStatus, server_default="active")
    authority: Mapped[str] = mapped_column(DocAuthority)
    page_count: Mapped[int]
    is_current: Mapped[bool] = mapped_column(server_default=text("false"))
    ingested_at: Mapped[datetime] = mapped_column(Timestamp, server_default=func.now())


class Section(Base):
    __tablename__ = "sections"

    id: Mapped[UUID] = primary_key()
    version_id: Mapped[UUID] = mapped_column(ForeignKey("document_versions.id"))
    path: Mapped[str]
    text: Mapped[str]
    page_start: Mapped[int]
    page_end: Mapped[int]
    ordinal: Mapped[int]


class Chunk(Base):
    __tablename__ = "chunks"
    __table_args__ = (
        UniqueConstraint("version_id", "ordinal", name="chunks_ordinal_unique"),
        CheckConstraint(ACL_SHAPE, name="chunks_acl_shape"),
        Index("chunks_acl", "is_current", "access_level", "tenant_id"),
        Index(
            "chunks_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
        Index("chunks_fts", "fts", postgresql_using="gin"),
        Index(
            "chunks_bm25",
            "id",
            text(f"(text::{BM25_TOKENIZER})"),
            text(f"(section_path::{BM25_TOKENIZER})"),
            postgresql_using="paradedb",
        ),
    )

    id: Mapped[UUID] = primary_key()
    version_id: Mapped[UUID] = mapped_column(ForeignKey("document_versions.id"))
    document_id: Mapped[UUID] = mapped_column(ForeignKey("documents.id"))
    section_id: Mapped[UUID | None] = mapped_column(ForeignKey("sections.id"))
    tenant_id: Mapped[UUID | None] = mapped_column(ForeignKey("tenants.id"))
    access_level: Mapped[str] = mapped_column(AccessLevel)
    is_current: Mapped[bool] = mapped_column(server_default=text("false"))
    ordinal: Mapped[int]
    section_path: Mapped[str] = mapped_column(server_default="")
    text: Mapped[str]
    token_count: Mapped[int]
    # Any: free-form JSON, shape documented in SCHEMA.md §6.
    spans: Mapped[list[dict[str, Any]]] = mapped_column(JSONB)
    content_hash: Mapped[str]
    embedding: Mapped[list[float]] = mapped_column(Vector(768))
    fts: Mapped[str] = mapped_column(
        TSVECTOR,
        Computed("to_tsvector('english', section_path || ' ' || text)", persisted=True),
    )
    created_at: Mapped[datetime] = created_at()


class IngestionJob(Base):
    __tablename__ = "ingestion_jobs"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "content_hash",
            name="jobs_idempotent",
            postgresql_nulls_not_distinct=True,
        ),
    )

    id: Mapped[UUID] = primary_key()
    tenant_id: Mapped[UUID | None] = mapped_column(ForeignKey("tenants.id"))
    source: Mapped[str] = mapped_column(JobSource)
    doc_key: Mapped[str]
    content_hash: Mapped[str]
    storage_key: Mapped[str]
    status: Mapped[str] = mapped_column(JobStatus, server_default="pending")
    attempts: Mapped[int] = mapped_column(server_default=text("0"))
    max_attempts: Mapped[int] = mapped_column(server_default=text("3"))
    error: Mapped[str | None]
    version_id: Mapped[UUID | None] = mapped_column(ForeignKey("document_versions.id"))
    created_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = created_at()
    updated_at: Mapped[datetime] = mapped_column(Timestamp, server_default=func.now())


class SavedAnswer(Base):
    __tablename__ = "saved_answers"
    __table_args__ = (
        Index("saved_answers_owner", "tenant_id", "user_id", text("created_at DESC")),
    )

    id: Mapped[UUID] = primary_key()
    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id"))
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    question: Mapped[str]
    # Any: free-form JSON, shapes documented in SCHEMA.md §6.
    answer: Mapped[dict[str, Any]] = mapped_column(JSONB)
    citations: Mapped[list[dict[str, Any]]] = mapped_column(JSONB)
    note: Mapped[str | None]
    created_at: Mapped[datetime] = created_at()
