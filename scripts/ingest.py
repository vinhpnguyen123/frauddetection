"""Enqueue every stage 1 document and synthetic policy for ingestion. Safe to run repeatedly.

Needs `make up`, `make migrate`, `make seed`, `make synthetic` and `make embedder`.
"""

import asyncio
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

from scripts.download import MANIFEST, RAW_DIR, file_hash, read_manifest, target_path
from scripts.render_synthetic import OUTPUT_DIR, SOURCE_DIR
from sqlalchemy import select

from app import db, embedder
from app.config import get_settings
from app.ingestion.pipeline import IngestItem, VersionMeta, register
from app.ingestion.tasks import ingest_document
from app.models import Tenant

STAGE = 1


@dataclass(frozen=True)
class Planned:
    item: IngestItem
    meta: VersionMeta
    file: Path


def public_documents() -> list[Planned]:
    planned = []
    for row in read_manifest(MANIFEST):
        if int(row["stage"]) > STAGE:
            continue
        file = target_path(row, RAW_DIR)
        if not file.exists() or file_hash(file) != row["sha256"]:
            sys.exit(f"{row['doc_id']}: missing or changed, run `make download` first")
        item = IngestItem(
            doc_key=row["doc_id"],
            title=row["title"],
            source=row["source"],
            collections=tuple(row["collections"].split(";")),
            tenant_id=None,
            scope="public",
            content_hash=row["sha256"],
        )
        meta = VersionMeta(
            source_url=row["url"],
            published_date=row["published_date"] or None,
            status=row["status"],
            authority=row["authority"],
        )
        planned.append(Planned(item, meta, file))
    return planned


def synthetic_documents(tenants: dict[str, UUID]) -> list[Planned]:
    planned = []
    for source in sorted(SOURCE_DIR.glob("*/*.md")):
        slug = source.parent.name
        file = OUTPUT_DIR / slug / f"{source.stem}.pdf"
        if slug not in tenants:
            sys.exit(f"no tenant {slug}, run `make seed` first")
        if not file.exists():
            sys.exit(f"{file.name}: missing, run `make synthetic` first")
        title = source.read_text(encoding="utf-8").splitlines()[0].removeprefix("# ")
        item = IngestItem(
            doc_key=f"synthetic-{source.stem}",
            title=title,
            source="synthetic",
            collections=("internal_policies",),
            tenant_id=tenants[slug],
            scope=slug,
            content_hash=file_hash(file),
        )
        meta = VersionMeta(None, None, "active", "internal_policy")
        planned.append(Planned(item, meta, file))
    return planned


def store(planned: Planned, storage_dir: Path) -> None:
    target = storage_dir / planned.item.storage_key
    if not target.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(planned.file, target)


async def main() -> None:
    await embedder.ping()
    async with db.get_sessionmaker().begin() as session:
        rows = await session.execute(select(Tenant.slug, Tenant.id))
        planned = public_documents() + synthetic_documents({row.slug: row.id for row in rows})
        jobs = []
        for document in planned:
            store(document, get_settings().storage_dir)
            job_id, needs_run = await register(session, document.item)
            if needs_run:
                jobs.append((job_id, document.meta))
    await db.close()
    # After the commit, so a worker never picks up a job it cannot see yet.
    for job_id, meta in jobs:
        ingest_document.delay(str(job_id), meta.as_task_argument())
    print(f"{len(planned)} documents: {len(jobs)} enqueued, {len(planned) - len(jobs)} skipped")


if __name__ == "__main__":
    asyncio.run(main())
