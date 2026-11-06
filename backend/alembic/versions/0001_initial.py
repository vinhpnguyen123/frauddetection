"""Initial schema, as defined in docs/SCHEMA.md. BM25 index arrives in M3-S2."""

from alembic import op

revision = "0001"
down_revision = None

# One statement per entry: asyncpg cannot run several in a single prepared statement.
STATEMENTS = [
    "CREATE EXTENSION IF NOT EXISTS vector",
    "CREATE EXTENSION IF NOT EXISTS pg_search",
    "CREATE TYPE user_role AS ENUM ('investigator', 'admin')",
    "CREATE TYPE access_level AS ENUM ('public', 'tenant_private')",
    "CREATE TYPE doc_status AS ENUM ('active', 'rescinded', 'superseded')",
    """CREATE TYPE doc_authority AS ENUM (
        'regulation', 'supervisory_guidance', 'advisory', 'industry_standard', 'internal_policy'
    )""",
    "CREATE TYPE job_status AS ENUM ('pending', 'running', 'succeeded', 'failed')",
    "CREATE TYPE job_source AS ENUM ('manifest', 'upload')",
    """CREATE TABLE tenants (
        id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        slug        text NOT NULL UNIQUE,
        name        text NOT NULL,
        created_at  timestamptz NOT NULL DEFAULT now()
    )""",
    """CREATE TABLE users (
        id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        tenant_id      uuid NOT NULL REFERENCES tenants(id),
        email          text NOT NULL,
        password_hash  text NOT NULL,
        role           user_role NOT NULL DEFAULT 'investigator',
        is_active      boolean NOT NULL DEFAULT true,
        created_at     timestamptz NOT NULL DEFAULT now(),
        CONSTRAINT users_email_lower CHECK (email = lower(email)),
        CONSTRAINT users_email_unique UNIQUE (email)
    )""",
    """CREATE TABLE documents (
        id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        doc_key             text NOT NULL,
        title               text NOT NULL,
        source              text NOT NULL,
        collections         text[] NOT NULL DEFAULT '{}',
        tenant_id           uuid NULL REFERENCES tenants(id),
        access_level        access_level NOT NULL,
        current_version_id  uuid NULL,
        created_at          timestamptz NOT NULL DEFAULT now(),
        CONSTRAINT documents_acl_shape CHECK (
            (access_level = 'public' AND tenant_id IS NULL) OR
            (access_level = 'tenant_private' AND tenant_id IS NOT NULL)
        ),
        CONSTRAINT documents_key_unique UNIQUE NULLS NOT DISTINCT (tenant_id, doc_key)
    )""",
    """CREATE TABLE document_versions (
        id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        document_id     uuid NOT NULL REFERENCES documents(id),
        version_no      integer NOT NULL,
        content_hash    text NOT NULL,
        storage_key     text NOT NULL,
        source_url      text NULL,
        published_date  date NULL,
        status          doc_status NOT NULL DEFAULT 'active',
        authority       doc_authority NOT NULL,
        page_count      integer NOT NULL,
        is_current      boolean NOT NULL DEFAULT false,
        ingested_at     timestamptz NOT NULL DEFAULT now(),
        CONSTRAINT dv_no_unique   UNIQUE (document_id, version_no),
        CONSTRAINT dv_hash_unique UNIQUE (document_id, content_hash)
    )""",
    "CREATE UNIQUE INDEX dv_one_current ON document_versions(document_id) WHERE is_current",
    """ALTER TABLE documents ADD CONSTRAINT documents_current_fk
        FOREIGN KEY (current_version_id) REFERENCES document_versions(id)""",
    """CREATE TABLE sections (
        id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        version_id   uuid NOT NULL REFERENCES document_versions(id),
        path         text NOT NULL,
        text         text NOT NULL,
        page_start   integer NOT NULL,
        page_end     integer NOT NULL,
        ordinal      integer NOT NULL
    )""",
    """CREATE TABLE chunks (
        id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        version_id    uuid NOT NULL REFERENCES document_versions(id),
        document_id   uuid NOT NULL REFERENCES documents(id),
        section_id    uuid NULL REFERENCES sections(id),
        tenant_id     uuid NULL REFERENCES tenants(id),
        access_level  access_level NOT NULL,
        is_current    boolean NOT NULL DEFAULT false,
        ordinal       integer NOT NULL,
        section_path  text NOT NULL DEFAULT '',
        text          text NOT NULL,
        token_count   integer NOT NULL,
        spans         jsonb NOT NULL,
        content_hash  text NOT NULL,
        embedding     vector(768) NOT NULL,
        fts           tsvector GENERATED ALWAYS AS (
            to_tsvector('english', section_path || ' ' || text)
        ) STORED,
        created_at    timestamptz NOT NULL DEFAULT now(),
        CONSTRAINT chunks_ordinal_unique UNIQUE (version_id, ordinal),
        CONSTRAINT chunks_acl_shape CHECK (
            (access_level = 'public' AND tenant_id IS NULL) OR
            (access_level = 'tenant_private' AND tenant_id IS NOT NULL)
        )
    )""",
    """CREATE TABLE ingestion_jobs (
        id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        tenant_id     uuid NULL REFERENCES tenants(id),
        source        job_source NOT NULL,
        doc_key       text NOT NULL,
        content_hash  text NOT NULL,
        storage_key   text NOT NULL,
        status        job_status NOT NULL DEFAULT 'pending',
        attempts      integer NOT NULL DEFAULT 0,
        max_attempts  integer NOT NULL DEFAULT 3,
        error         text NULL,
        version_id    uuid NULL REFERENCES document_versions(id),
        created_by    uuid NULL REFERENCES users(id),
        created_at    timestamptz NOT NULL DEFAULT now(),
        updated_at    timestamptz NOT NULL DEFAULT now(),
        CONSTRAINT jobs_idempotent UNIQUE NULLS NOT DISTINCT (tenant_id, content_hash)
    )""",
    """CREATE TABLE saved_answers (
        id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        tenant_id   uuid NOT NULL REFERENCES tenants(id),
        user_id     uuid NOT NULL REFERENCES users(id),
        question    text NOT NULL,
        answer      jsonb NOT NULL,
        citations   jsonb NOT NULL,
        note        text NULL,
        created_at  timestamptz NOT NULL DEFAULT now()
    )""",
    "CREATE INDEX saved_answers_owner ON saved_answers(tenant_id, user_id, created_at DESC)",
    "CREATE INDEX chunks_acl ON chunks(is_current, access_level, tenant_id)",
    "CREATE INDEX chunks_embedding_hnsw ON chunks USING hnsw (embedding vector_cosine_ops)",
    "CREATE INDEX chunks_fts ON chunks USING gin (fts)",
]


def upgrade() -> None:
    for statement in STATEMENTS:
        op.execute(statement)


def downgrade() -> None:
    raise NotImplementedError("Migrations are forward-only (expand/contract).")
