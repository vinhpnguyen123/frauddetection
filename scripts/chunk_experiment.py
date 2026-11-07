"""Chunking experiments on throwaway copies of the database. See docs/DATASET.md §5.

`verify` proves the default config still gives the stored chunks. `run <variant>` copies the
database, rebuilds its chunks, evaluates that copy and drops it. `report` writes the comparison.
Needs the stack and `make embedder`. No write ever reaches the main database.
"""

import asyncio
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass, replace
from datetime import date
from pathlib import Path
from uuid import UUID

from eval.runner.retrieval import ALLOW_UNMATCHED, REPORTS, RERANK_MAX_TOKENS, cell
from sqlalchemy import delete, func, make_url, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.config import get_settings
from app.embedder import HttpEmbedder, http_embedder
from app.ingestion.chunk import CHUNK_V1, Chunk, ChunkConfig, chunk_document, normalized_hash
from app.ingestion.parse import parse_pdf
from app.ingestion.pipeline import chunk_rows
from app.models import Chunk as ChunkRow
from app.models import Document, DocumentVersion, Section

ROOT = Path(__file__).resolve().parent.parent
EXPERIMENT_MARK = "_exp_"
SET_NAME = "dev"
CONFIGS = ("hybrid_raw", "rerank_top20")
SHORT_TOKENS = 20
URL = re.compile(r"https?://\S+")


@dataclass(frozen=True)
class Variant:
    chunking: ChunkConfig = CHUNK_V1
    rebuild: bool = True  # False keeps the stored chunks and embeddings
    strip_urls: bool = False
    embed_section_path: bool = False
    drop_short: bool = False


VARIANTS = {
    "chunk_v1": Variant(rebuild=False),  # control: must repeat the main rows exactly
    "chunk_300": Variant(chunking=ChunkConfig(target=300, max=450, overlap=30)),
    "paragraph": Variant(chunking=ChunkConfig(overlap=0, per_paragraph=True)),
    "strip_urls": Variant(strip_urls=True),
    "no_short": Variant(rebuild=False, drop_short=True),
    "section_context": Variant(embed_section_path=True),
}


def experiment_url(main_url: str, variant: str) -> str:
    url = make_url(main_url)
    name = f"{url.database}{EXPERIMENT_MARK}{variant}"
    return url.set(database=name).render_as_string(hide_password=False)


def require_experiment(url: str) -> None:
    """Every write below goes through this, so a wrong URL stops before touching any row."""
    if EXPERIMENT_MARK not in (make_url(url).database or ""):
        sys.exit("refusing to change a database that is not an experiment copy")


def postgres(script: str) -> None:
    """Run a shell line in the Postgres container, where its user and tools already exist."""
    subprocess.run(
        ["docker", "compose", "exec", "-T", "postgres", "sh", "-c", script], cwd=ROOT, check=True
    )


def drop_copy(name: str) -> None:
    postgres(f'dropdb --if-exists --force -U "$POSTGRES_USER" {name}')


def create_copy(name: str) -> None:
    """template0, because template1 here already holds the extensions that the dump creates."""
    drop_copy(name)
    postgres(
        f'createdb -T template0 -U "$POSTGRES_USER" {name} '
        f'&& pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB" '
        f'| psql -q -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -o /dev/null {name}'
    )


def without_urls(chunk: Chunk) -> Chunk:
    text = " ".join(URL.sub("", chunk.text).split(" ")).strip()
    return replace(chunk, text=text, content_hash=normalized_hash(text))


async def build_chunks(path: Path, variant: Variant, embedder: HttpEmbedder) -> list[Chunk]:
    chunks = await chunk_document(parse_pdf(path), embedder.count_tokens, variant.chunking)
    if not variant.strip_urls:
        return chunks
    stripped = [chunk for chunk in map(without_urls, chunks) if chunk.text]
    counts = await embedder.count_tokens([chunk.text for chunk in stripped])
    return [
        replace(chunk, token_count=count) for chunk, count in zip(stripped, counts, strict=True)
    ]


async def current_versions(
    sessions: async_sessionmaker[AsyncSession],
) -> list[tuple[Document, UUID, str]]:
    statement = (
        select(Document, DocumentVersion.id, DocumentVersion.storage_key)
        .join(DocumentVersion, DocumentVersion.document_id == Document.id)
        .where(DocumentVersion.is_current)
        .order_by(Document.doc_key)
    )
    async with sessions() as session:
        return [tuple(row) for row in await session.execute(statement)]  # type: ignore[misc]


async def rebuild(
    sessions: async_sessionmaker[AsyncSession], variant: Variant, embedder: HttpEmbedder
) -> None:
    storage = get_settings().storage_dir
    versions = await current_versions(sessions)
    async with sessions.begin() as session:
        await session.execute(delete(ChunkRow))
    for document, version_id, storage_key in versions:
        chunks = await build_chunks(storage / storage_key, variant, embedder)
        embed_texts = [
            f"{chunk.section_path}\n{chunk.text}" if variant.embed_section_path else chunk.text
            for chunk in chunks
        ]
        vectors = await embedder.embed_documents(embed_texts)
        async with sessions.begin() as session:
            found = await session.execute(
                select(Section.ordinal, Section.id).where(Section.version_id == version_id)
            )
            section_ids = {row.ordinal: row.id for row in found}
            rows = chunk_rows(chunks, vectors, section_ids, version_id, document)
            await session.execute(ChunkRow.__table__.insert(), rows)
            await session.execute(
                update(ChunkRow).where(ChunkRow.version_id == version_id).values(is_current=True)
            )
        print(f"{document.doc_key}: {len(chunks)} chunks", flush=True)


async def corpus_stats(sessions: async_sessionmaker[AsyncSession]) -> dict[str, float]:
    tokens = ChunkRow.token_count
    statement = select(
        func.count(),
        func.avg(tokens),
        func.count().filter(tokens > RERANK_MAX_TOKENS),
        func.count().filter(tokens < SHORT_TOKENS),
    ).where(ChunkRow.is_current)
    async with sessions() as session:
        count, average, over, short = (await session.execute(statement)).one()
    return {"chunks": count, "avg_tokens": float(average), "over_limit": over, "short": short}


async def prepare(url: str, variant: Variant) -> dict[str, float]:
    require_experiment(url)
    engine = create_async_engine(url, poolclass=NullPool)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    if variant.rebuild:
        await rebuild(sessions, variant, http_embedder())
    if variant.drop_short:
        async with sessions.begin() as session:
            await session.execute(delete(ChunkRow).where(ChunkRow.token_count < SHORT_TOKENS))
    stats = await corpus_stats(sessions)
    await engine.dispose()
    return stats


def stats_path(variant: str) -> Path:
    return REPORTS / f"{date.today().isoformat()}_{SET_NAME}_chunking_{variant}.json"


def run(variant: str) -> None:
    """Copy, rebuild, evaluate, and always drop the copy."""
    url = experiment_url(get_settings().database_url, variant)
    require_experiment(url)
    name = make_url(url).database
    assert name is not None
    try:
        create_copy(name)
        stats = asyncio.run(prepare(url, VARIANTS[variant]))
        stats_path(variant).write_text(json.dumps(stats, indent=2) + "\n")
        print(stats, flush=True)
        for config in CONFIGS:
            runner = [sys.executable, "-m", "eval.runner.retrieval"]
            command = [*runner, SET_NAME, config, variant, ALLOW_UNMATCHED]
            subprocess.run(command, env={**os.environ, "DATABASE_URL": url}, check=True)
    finally:
        drop_copy(name)


async def verify() -> None:
    """Rebuilding with the default config must give exactly the stored chunks."""
    engine = create_async_engine(get_settings().database_url, poolclass=NullPool)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    embedder = http_embedder()
    different = total = 0
    for document, version_id, storage_key in await current_versions(sessions):
        built = await build_chunks(get_settings().storage_dir / storage_key, Variant(), embedder)
        async with sessions() as session:
            stored = await session.scalars(
                select(ChunkRow.content_hash)
                .where(ChunkRow.version_id == version_id)
                .order_by(ChunkRow.ordinal)
            )
            hashes = list(stored)
        total += len(hashes)
        if hashes != [chunk.content_hash for chunk in built]:
            different += 1
            print(f"{document.doc_key}: chunks differ")
    await engine.dispose()
    print(f"{total} stored chunks checked, {different} documents differ")
    if different:
        sys.exit(1)


def latest(pattern: str) -> dict[str, object]:
    return json.loads(sorted(REPORTS.glob(pattern))[-1].read_text())


def render_report(rows: list[tuple[str, str, dict, dict]]) -> str:  # type: ignore[type-arg]
    """One line per variant and config. `rows` holds variant, config, stats and eval report."""
    first = rows[0][3]
    lines = ["# Chunking experiments", ""]
    lines += [f"- Set: `{first['set']}` ({first['set_size']} items), date {first['date']}"]
    lines += [f"- Git SHA: `{first['git_sha']}`", f"- Labels: {first['labels']}"]
    lines += ["- Metrics use `real` answerable items. Each variant ran on its own database copy."]
    lines += ["- Recall@20 and MRR are the main metrics: P@5 moves with the chunk size, because"]
    lines += ["  the number of relevant chunks changes, and 20 small chunks hold less text.", ""]
    lines += [
        "| Variant | Config | Chunks | Avg tokens | Over 512 | Under 20 | Unmatched anchors "
        "| P@5 (95% CI) | Recall@20 (95% CI) | MRR (95% CI) | p50/p95 ms |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for variant, config, stats, report in rows:
        latency = report["latency_ms"]
        lines.append(
            f"| {variant} | {config} | {stats['chunks']} | {stats['avg_tokens']:.1f} "
            f"| {stats['over_limit']} | {stats['short']} | {report['unmatched_anchors']} "
            f"| {cell(report['real'], 'p_at_5')} | {cell(report['real'], 'recall_at_20')} "
            f"| {cell(report['real'], 'mrr')} | {latency['p50']:.1f} / {latency['p95']:.1f} |"
        )
    lines.append("")
    return "\n".join(lines)


def report() -> None:
    rows = [
        (
            variant,
            config,
            latest(f"*_{SET_NAME}_chunking_{variant}.json"),
            latest(f"*_{SET_NAME}_{config}_{variant}.json"),
        )
        for variant in VARIANTS
        for config in CONFIGS
    ]
    path = REPORTS / f"{date.today().isoformat()}_{SET_NAME}_chunking.md"
    path.write_text(render_report(rows))
    print(path)


def main() -> None:
    action = sys.argv[1]
    if action == "verify":
        asyncio.run(verify())
    elif action == "run":
        run(sys.argv[2])
    elif action == "report":
        report()
    else:
        sys.exit(f"unknown action {action}")


if __name__ == "__main__":
    main()
