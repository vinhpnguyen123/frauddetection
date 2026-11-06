"""The access predicate. This is the only place an ACL condition may be built."""

from sqlalchemy import ColumnElement, and_, or_

from app.models import Chunk
from app.retrieval.protocols import RetrievalContext


def access_predicate(context: RetrievalContext) -> ColumnElement[bool]:
    """Build the SQL condition from docs/SCHEMA.md §5 for `Chunk`.

    Guarantees that only current chunks match, that public chunks match only if the context
    allows them, and that private chunks match only for the context's own tenant. An empty
    `allowed_access_levels` matches nothing.
    """
    return and_(
        Chunk.is_current,
        Chunk.access_level.in_(sorted(context.allowed_access_levels)),
        or_(
            Chunk.access_level == "public",
            and_(Chunk.access_level == "tenant_private", Chunk.tenant_id == context.tenant_id),
        ),
    )
