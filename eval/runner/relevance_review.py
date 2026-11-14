"""Q2: create a blinded local review pool from Q1 traces; never change labels."""

import argparse
import asyncio
import hashlib
import json
from pathlib import Path
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app import db
from app.models import Chunk, Document, DocumentVersion, Tenant
from app.retrieval.acl import access_predicate
from app.retrieval.protocols import RetrievalContext
from eval.runner.anchors import squash
from eval.runner.dataset import DATASETS, ROOT, EvalItem, load_items, load_provenance
from eval.runner.tracing import QueryTrace

SCHEMA = "relevance-review/v1"
STAGES = {"bm25": "bm25", "dense": "dense", "hybrid": "rrf_top20", "reranked": "final_top20"}


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def review_id(query_id: str, document: str, version: str, passage: str) -> str:
    """Exact normalized duplicates within one document version share a review unit."""
    return digest(json.dumps([SCHEMA, query_id, document, version, squash(passage)]))[:24]


async def authorized_passages(
    sessions: async_sessionmaker[AsyncSession], context: RetrievalContext
) -> list[dict[str, object]]:
    """Only the central SQL predicate authorizes passage export, including neighbors."""
    statement = (
        select(
            Chunk.id,
            Chunk.version_id,
            Chunk.ordinal,
            Chunk.section_path,
            Chunk.spans,
            Chunk.text,
            Document.doc_key,
            Document.title,
            DocumentVersion.status,
            DocumentVersion.authority,
        )
        .join(Document, Chunk.document_id == Document.id)
        .join(DocumentVersion, Chunk.version_id == DocumentVersion.id)
        .where(access_predicate(context))
        .order_by(Chunk.version_id, Chunk.ordinal)
    )
    async with sessions() as session:
        return [dict(row._mapping) for row in await session.execute(statement)]


def make_pool(
    item: EvalItem, trace: QueryTrace, passages: list[dict[str, object]]
) -> tuple[list[dict[str, object]], list[dict[str, object]], dict[str, object]]:
    """Separate blinded review cards from the administrator's ranking/label key."""
    by_id = {str(p["id"]): p for p in passages}
    sources: dict[str, list[dict[str, object]]] = {}
    for method, stage_name in STAGES.items():
        stage = next(s for s in trace.stages if s.name == stage_name)
        for candidate in stage.candidates[:20]:
            sources.setdefault(str(candidate.chunk_id), []).append(
                {"method": method, "rank": candidate.rank, "score": candidate.score}
            )
    gold = {str(c) for a in trace.gold for c in a.chunk_ids}
    selected = set(sources) | gold
    if not selected.issubset(by_id):
        raise ValueError("pool contains stale or unauthorized candidate IDs")
    positions = {(str(p["version_id"]), int(p["ordinal"])): str(p["id"]) for p in passages}
    seeds = set(selected)
    for chunk_id in seeds:
        p = by_id[chunk_id]
        for offset in (-1, 1):
            neighbor = positions.get((str(p["version_id"]), int(p["ordinal"]) + offset))
            if neighbor:
                selected.add(neighbor)
    cards: dict[str, dict[str, object]] = {}
    keys: dict[str, dict[str, object]] = {}
    for chunk_id in sorted(selected):
        p = by_id[chunk_id]
        unit = review_id(item.id, str(p["doc_key"]), str(p["version_id"]), str(p["text"]))
        occurrence = {
            "chunk_id": chunk_id,
            "ordinal": p["ordinal"],
            "section": p["section_path"],
            "spans": p["spans"],
        }
        if unit not in cards:
            cards[unit] = {
                "schema_version": SCHEMA,
                "query_id": item.id,
                "review_id": unit,
                "query": item.query,
                "document": p["doc_key"],
                "title": p["title"],
                "version_id": str(p["version_id"]),
                "status": p["status"],
                "authority": p["authority"],
                "passage": p["text"],
                "occurrences": [],
                "judgment": None,
                "rationale": None,
                "reviewer": None,
                "evidence_scope": None,
            }
            keys[unit] = {
                "query_id": item.id,
                "review_id": unit,
                "occurrences": [],
            }
        cards[unit]["occurrences"].append(occurrence)
        keys[unit]["occurrences"].append(
            {
                "chunk_id": chunk_id,
                "existing_relevant": chunk_id in gold,
                "sources": sources.get(chunk_id, []),
                "neighbor_only": chunk_id not in seeds,
            }
        )
    # Hash order is deterministic and does not expose original rank or retrieval method.
    ordered = sorted(cards)
    summary = {
        "query_id": item.id,
        "gold_chunks": len(gold),
        "pooled_chunks": len(selected),
        "review_units": len(cards),
        "judged_units": 0,
    }
    return [cards[k] for k in ordered], [keys[k] for k in ordered], summary


def sufficiency_sets(
    trace: QueryTrace, cards: list[dict[str, object]]
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    """Blind set-level top-five judgments; identical sets are reviewed only once."""
    unit_by_chunk = {
        occurrence["chunk_id"]: card["review_id"]
        for card in cards
        for occurrence in card["occurrences"]
    }
    sets: dict[str, dict[str, object]] = {}
    key = []
    for method, stage_name in STAGES.items():
        stage = next(s for s in trace.stages if s.name == stage_name)
        chunk_ids = sorted(str(c.chunk_id) for c in stage.candidates[:5])
        set_id = digest(json.dumps([trace.query_id, chunk_ids]))[:24]
        sets[set_id] = {
            "query_id": trace.query_id,
            "set_id": set_id,
            "review_ids": sorted({unit_by_chunk[c] for c in chunk_ids}),
            "occurrence_chunk_ids": chunk_ids,
            "sufficient": None,
            "missing_facets": [],
            "rationale": None,
            "reviewer": None,
        }
        key.append({"query_id": trace.query_id, "set_id": set_id, "method": method})
    return [sets[k] for k in sorted(sets)], key


async def build(trace_path: Path, output: Path) -> None:
    """Passages/queries stay under gitignored eval/.cache, never public reports."""
    cache = (ROOT / "eval" / ".cache").resolve()
    output = output.resolve()
    if not output.is_relative_to(cache):
        raise ValueError("review content must stay inside gitignored eval/.cache")
    if output.exists():
        raise ValueError("review output exists; choose a new version directory")
    source = trace_path.with_name(trace_path.name.replace(".trace.jsonl", ".json"))
    run = json.loads(source.read_text())
    dataset = DATASETS / "dev.jsonl"
    provenance = load_provenance(dataset)
    if run["set"] != "dev" or run["dataset_sha256"] != provenance.dataset_sha256:
        raise ValueError("trace must use the unchanged development dataset")
    if run["config_key"] != "rerank_top20":
        raise ValueError("pool v1 freezes rerank_top20 as its reranked source")
    traces = [QueryTrace.model_validate_json(line) for line in trace_path.read_text().splitlines()]
    by_query = {t.query_id: t for t in traces}
    if len(by_query) != len(traces):
        raise ValueError("duplicate trace query")
    items = [i for i in load_items(dataset) if i.answerable and i.data_kind == "real"]
    sessions = db.get_sessionmaker()
    async with sessions() as session:
        tenants = dict((await session.execute(select(Tenant.slug, Tenant.id))).all())
    cards, keys, summaries = [], [], []
    sets, set_keys = [], []
    for item in items:
        context = RetrievalContext(
            uuid4(), tenants[item.ask_as_tenant], frozenset({"public", "tenant_private"})
        )
        passages = await authorized_passages(sessions, context)
        c, k, s = make_pool(item, by_query[item.id], passages)
        sc, sk = sufficiency_sets(by_query[item.id], c)
        sets.extend(sc)
        set_keys.extend(sk)
        cards.extend(c)
        keys.extend(k)
        summaries.append(s)
    output.mkdir(parents=True, mode=0o700)
    for name, rows in (
        ("reviewer.jsonl", cards),
        ("administrator_key.jsonl", keys),
        ("sufficiency_reviewer.jsonl", sets),
        ("sufficiency_administrator_key.jsonl", set_keys),
    ):
        p = output / name
        p.write_text("".join(json.dumps(r, default=str) + "\n" for r in rows))
        p.chmod(0o600)
    manifest = {
        "schema_version": SCHEMA,
        "status": "awaiting_independent_review",
        "dataset_sha256": provenance.dataset_sha256,
        "trace_sha256": digest(trace_path.read_text()),
        "trace_file": trace_path.name,
        "corpus_vectors_sha256": run["trace_manifest"]["corpus_vectors_sha256"],
        "deduplication": "exact normalized passage within document/version; occurrences retained",
        "reviewer_sha256": digest((output / "reviewer.jsonl").read_text()),
        "administrator_key_sha256": digest((output / "administrator_key.jsonl").read_text()),
        "queries": summaries,
    }
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"Prepared {len(cards)} blinded units for {len(items)} queries; no labels accepted")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("trace", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    asyncio.run(build(args.trace, args.output))


if __name__ == "__main__":
    main()
