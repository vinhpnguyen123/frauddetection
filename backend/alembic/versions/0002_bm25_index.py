"""BM25 index on chunks.

Revision ID: 0002
Revises: 0001
"""

from alembic import op

revision = "0002"
down_revision = "0001"

TOKENIZER = "pdb.unicode_words('stemmer=english', 'stopwords_language=English')"


def upgrade() -> None:
    # ACL columns stay out on purpose: pg_search turns a filter on an indexed column into a
    # scored term, which would boost a tenant's private chunks. Unindexed, the ACL is checked
    # against the table row inside the scan, before top-k, and adds nothing to the score.
    # Syntax from pg_search v0.26.5 docs; `key_field` is a no-op since 0.26.0.
    op.execute(
        f"""
        CREATE INDEX chunks_bm25 ON chunks USING paradedb (
          id,
          (text::{TOKENIZER}),
          (section_path::{TOKENIZER})
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX chunks_bm25")
