"""Check the M2 gate against the database and write data/corpus_stats.json."""

import asyncio
import json
import sys
from pathlib import Path

from scripts.download import MANIFEST, read_manifest
from scripts.ingest import STAGE
from scripts.render_synthetic import SOURCE_DIR
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import db
from app.ingestion.chunk import MAX_TOKENS
from app.models import Chunk, Document, DocumentVersion, IngestionJob, Section

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "data" / "corpus_stats.json"
SHORT_CHUNK_TOKENS = 20


async def count(session: AsyncSession, *conditions: object, model: type = Chunk) -> int:
    statement = select(func.count()).select_from(model).where(*conditions)  # type: ignore[arg-type]
    return (await session.scalar(statement)) or 0


async def collect(session: AsyncSession) -> dict[str, object]:
    current = Chunk.is_current
    jobs = await session.execute(
        select(IngestionJob.status, func.count()).group_by(IngestionJob.status)
    )
    tokens = await session.scalar(select(func.avg(Chunk.token_count)).where(current))
    return {
        "documents_public": await count(session, Document.access_level == "public", model=Document),
        "documents_tenant_private": await count(
            session, Document.access_level == "tenant_private", model=Document
        ),
        "documents_without_current_version": await count(
            session, Document.current_version_id.is_(None), model=Document
        ),
        "versions": await count(session, model=DocumentVersion),
        "sections": await count(session, model=Section),
        "chunks_current": await count(session, current),
        "chunks_total": await count(session),
        "avg_tokens": round(float(tokens or 0), 1),
        "chunks_empty": await count(session, func.btrim(Chunk.text) == ""),
        "chunks_without_spans": await count(session, func.jsonb_array_length(Chunk.spans) == 0),
        "chunks_over_max": await count(session, Chunk.token_count > MAX_TOKENS),
        "chunks_under_20_tokens": await count(session, Chunk.token_count < SHORT_CHUNK_TOKENS),
        "jobs": {status: total for status, total in sorted(jobs.all())},
    }


def gate_failures(stats: dict[str, object], expected: int) -> list[str]:
    found = int(str(stats["documents_public"])) + int(str(stats["documents_tenant_private"]))
    checks = {
        f"expected {expected} documents": found == expected,
        "every document has a current version": stats["documents_without_current_version"] == 0,
        "every job succeeded": stats["jobs"] == {"succeeded": expected},
        "no empty chunks": stats["chunks_empty"] == 0,
        "every chunk has spans": stats["chunks_without_spans"] == 0,
        "no chunk over the limit": stats["chunks_over_max"] == 0,
    }
    return [name for name, passed in checks.items() if not passed]


async def main() -> int:
    async with db.get_sessionmaker()() as session:
        stats = await collect(session)
    await db.close()
    public = [row for row in read_manifest(MANIFEST) if int(row["stage"]) <= STAGE]
    expected = len(public) + len(list(SOURCE_DIR.glob("*/*.md")))
    REPORT.write_text(json.dumps(stats, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(stats, indent=2))
    failures = gate_failures(stats, expected)
    for failure in failures:
        print(f"GATE FAILED: {failure}")
    print("gate passed" if not failures else f"{len(failures)} gate checks failed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
