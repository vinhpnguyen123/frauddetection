"""Reproducible corpus/index fingerprints and bounded machine/model metadata."""

import hashlib
import json
import os
import platform
import struct
import subprocess
from datetime import UTC, datetime

from sqlalchemy import column, func, select, table
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.embedder import HttpEmbedder
from app.models import Chunk, DocumentVersion


def machine_conditions() -> dict[str, object]:
    result: dict[str, object] = {
        "utc": datetime.now(UTC).isoformat(),
        "platform": platform.platform(),
        "machine": platform.machine(),
        "load_average": list(os.getloadavg()),
    }
    if platform.system() == "Darwin":
        for name, command in {
            "memory_bytes": ["sysctl", "-n", "hw.memsize"],
            "swap": ["sysctl", "vm.swapusage"],
            "thermal": ["pmset", "-g", "therm"],
        }.items():
            response = subprocess.run(command, capture_output=True, text=True, check=False)
            result[name] = response.stdout.strip() if response.returncode == 0 else "unavailable"
    return result


async def capture_metadata(
    sessions: async_sessionmaker[AsyncSession], embedder: HttpEmbedder
) -> dict[str, object]:
    """Administrative evaluation fingerprint, not a user-facing retrieval path."""
    digest = hashlib.sha256()
    count = 0
    statement = (
        select(
            Chunk.id,
            Chunk.version_id,
            Chunk.content_hash,
            Chunk.section_path,
            Chunk.embedding,
            DocumentVersion.content_hash.label("pdf_hash"),
        )
        .join(DocumentVersion, Chunk.version_id == DocumentVersion.id)
        .where(Chunk.is_current)
        .order_by(Chunk.id)
    )
    indexes = table("pg_indexes", column("schemaname"), column("indexname"), column("indexdef"))
    extensions = table("pg_extension", column("extname"), column("extversion"))
    async with sessions() as session:
        for row in await session.execute(statement):
            digest.update(
                json.dumps(
                    [
                        str(row.id),
                        str(row.version_id),
                        row.content_hash,
                        row.section_path,
                        row.pdf_hash,
                    ]
                ).encode()
            )
            digest.update(struct.pack(f"<{len(row.embedding)}f", *row.embedding))
            count += 1
        definitions = [
            list(r)
            for r in await session.execute(
                select(indexes.c.indexname, indexes.c.indexdef)
                .where(indexes.c.schemaname == "public")
                .order_by(indexes.c.indexname)
            )
        ]
        versions = dict(
            (await session.execute(select(extensions.c.extname, extensions.c.extversion))).all()
        )
        postgres = await session.scalar(select(func.version()))
    return {
        "schema_version": "retrieval-trace-manifest/v1",
        "chunks": count,
        "corpus_vectors_sha256": digest.hexdigest(),
        "index_definitions_sha256": hashlib.sha256(json.dumps(definitions).encode()).hexdigest(),
        "index_definitions": definitions,
        "postgres_version": postgres,
        "extensions": versions,
        "models": await embedder.model_metadata(),
        "machine_before": machine_conditions(),
    }
