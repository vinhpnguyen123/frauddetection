"""Retrieval eval: `python -m eval.runner.retrieval <set> <config|all> [label]`, or `--check <set>`.

Reports go to eval/reports/. Needs the stack and `make embedder`. No LLM is called.
"""

import asyncio
import json
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from datetime import date
from itertools import combinations
from pathlib import Path
from uuid import UUID, uuid4

from scripts.hnsw_recall import K, measure
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app import db
from app.config import get_settings
from app.embedder import HttpEmbedder, http_embedder
from app.models import Chunk, Document, Tenant
from app.retrieval.bm25 import Bm25Retriever
from app.retrieval.config import RetrievalConfig
from app.retrieval.dense import DenseRetriever
from app.retrieval.fts import FtsRetriever
from app.retrieval.hybrid import HybridRetriever
from app.retrieval.protocols import Embedder, Reranker, RetrievalContext, Retriever
from app.retrieval.query_processing import expand_query
from app.retrieval.rerank import RerankRetriever
from eval.runner.anchors import holds_quote, same_passage
from eval.runner.dataset import DATASETS, ROOT, EvalItem, load_items
from eval.runner.metrics import (
    RECALL_AT,
    bootstrap_ci,
    mean,
    percentile,
    precision_at_5,
    precision_ceiling,
    recall_at_20,
    reciprocal_rank,
)

REPORTS = ROOT / "eval" / "reports"
LEVELS = frozenset({"public", "tenant_private"})
METRICS = ("p_at_5", "recall_at_20", "mrr")
ALLOW_UNMATCHED = "--allow-unmatched"
RERANK_MAX_TOKENS = 512  # the tokenizer limit of the cross-encoder; longer input is cut off
# The rows of docs/EVALUATION.md §3. The `_raw` configs measure what expansion adds.
# Rerank builds on `hybrid_raw`; the run fills in the model the service reports.
CONFIGS = {
    "fts": RetrievalConfig(method="fts", query_expansion=True),
    "bm25": RetrievalConfig(method="bm25", query_expansion=True),
    "dense_exact": RetrievalConfig(method="dense", dense_mode="exact"),
    "dense_hnsw": RetrievalConfig(method="dense", dense_mode="hnsw"),
    "hybrid": RetrievalConfig(method="hybrid", dense_mode="exact", query_expansion=True),
    "fts_raw": RetrievalConfig(method="fts"),
    "bm25_raw": RetrievalConfig(method="bm25"),
    "hybrid_raw": RetrievalConfig(method="hybrid", dense_mode="exact"),
    "rerank_top20": RetrievalConfig(method="rerank", dense_mode="exact", rerank_top_n=20),
    "rerank_top50": RetrievalConfig(method="rerank", dense_mode="exact", rerank_top_n=50),
}


@dataclass(frozen=True)
class CorpusChunk:
    id: UUID
    doc_key: str
    text: str
    tenant_id: UUID | None


@dataclass(frozen=True)
class ItemResult:
    id: str
    category: str | None
    data_kind: str
    answerable: bool
    p_at_5: float | None
    p_ceiling: float | None
    recall_at_20: float | None
    mrr: float | None
    latency_ms: float
    leaks: list[str]


def build_retriever(
    config: RetrievalConfig,
    sessions: async_sessionmaker[AsyncSession],
    embedder: Embedder,
    reranker: Reranker | None = None,
) -> Retriever:
    if config.method == "fts":
        return FtsRetriever(sessions)
    if config.method == "bm25":
        return Bm25Retriever(sessions)
    assert config.dense_mode is not None
    dense = DenseRetriever(sessions, embedder, config.dense_mode)
    if config.method == "dense":
        return dense
    hybrid = HybridRetriever(
        Bm25Retriever(sessions),
        dense,
        k_bm25=config.k_bm25,
        k_dense=config.k_dense,
        rrf_k=config.rrf_k,
        query_expansion=config.query_expansion,
    )
    if config.method == "hybrid":
        return hybrid
    assert reranker is not None and config.rerank_top_n is not None
    return RerankRetriever(hybrid, reranker, sessions, top_n=config.rerank_top_n)


async def load_corpus(sessions: async_sessionmaker[AsyncSession]) -> dict[UUID, CorpusChunk]:
    """Every current chunk. The harness grades results with this; it is not a retrieval path."""
    statement = (
        select(Chunk.id, Document.doc_key, Chunk.text, Chunk.tenant_id)
        .join(Document, Chunk.document_id == Document.id)
        .where(Chunk.is_current)
    )
    async with sessions() as session:
        rows = await session.execute(statement)
        return {row.id: CorpusChunk(*row) for row in rows}


def anchor_chunks(item: EvalItem, corpus: dict[UUID, CorpusChunk]) -> list[set[UUID]]:
    """For each anchor, the chunks of its document that hold its quote."""
    return [
        {
            chunk.id
            for chunk in corpus.values()
            if chunk.doc_key == anchor.doc_id and holds_quote(chunk.text, anchor.quote)
        }
        for anchor in item.relevant
    ]


def find_leaks(
    item: EvalItem, ranked: list[UUID], tenant_id: UUID, corpus: dict[UUID, CorpusChunk]
) -> list[str]:
    """Name any chunk of another tenant, or any forbidden string, in the results."""
    leaks = []
    for chunk_id in ranked:
        chunk = corpus[chunk_id]
        if chunk.tenant_id not in (None, tenant_id):
            leaks.append(f"{item.id}: chunk {chunk_id} of another tenant")
        leaks += [f"{item.id}: {s}" for s in item.must_not_contain if s in chunk.text]
    return leaks


async def run_item(
    item: EvalItem,
    config: RetrievalConfig,
    retriever: Retriever,
    tenant_id: UUID,
    corpus: dict[UUID, CorpusChunk],
) -> ItemResult:
    # Hybrid expands inside the retriever, because only its BM25 input may change.
    expand = config.query_expansion and config.method not in ("hybrid", "rerank")
    query = expand_query(item.query) if expand else item.query
    context = RetrievalContext(uuid4(), tenant_id, LEVELS)
    started = time.perf_counter()
    hits = await retriever.search(query, context=context, limit=RECALL_AT)
    latency_ms = (time.perf_counter() - started) * 1000
    ranked = [hit.chunk_id for hit in hits]
    scores: dict[str, float | None] = {
        "p_at_5": None,
        "p_ceiling": None,
        "recall_at_20": None,
        "mrr": None,
    }
    if item.answerable:
        anchors = anchor_chunks(item, corpus)
        relevant = set().union(*anchors)
        scores = {
            "p_at_5": precision_at_5(ranked, relevant),
            "p_ceiling": precision_ceiling(relevant),
            "recall_at_20": recall_at_20(ranked, anchors),
            "mrr": reciprocal_rank(ranked, relevant),
        }
    return ItemResult(
        id=item.id,
        category=item.category,
        data_kind=item.data_kind,
        answerable=item.answerable,
        latency_ms=latency_ms,
        leaks=find_leaks(item, ranked, tenant_id, corpus),
        **scores,  # type: ignore[arg-type]
    )


def summarize(results: list[ItemResult]) -> dict[str, object]:
    """Mean and 95% CI of each metric, over answerable items of one group."""
    summary: dict[str, object] = {"n": len(results)}
    if not results:
        return summary
    for metric in METRICS:
        values = [float(getattr(result, metric)) for result in results]
        low, high = bootstrap_ci(values)
        summary[metric] = {"mean": mean(values), "ci95": [low, high]}
    summary["p_ceiling"] = mean([float(result.p_ceiling or 0) for result in results])
    return summary


def build_report(
    name: str, config: RetrievalConfig, results: list[ItemResult], meta: dict[str, object]
) -> dict[str, object]:
    """Headline numbers use `real` items only; `synthetic` is always a separate group."""
    answerable = [result for result in results if result.answerable]
    real = [result for result in answerable if result.data_kind == "real"]
    latencies = [result.latency_ms for result in results]
    return {
        **meta,
        "config_name": name,
        "config_hash": config.config_hash(),
        "config": config.model_dump(),
        "real": summarize(real),
        "synthetic": summarize([r for r in answerable if r.data_kind == "synthetic"]),
        "real_by_category": {
            category: summarize([r for r in real if r.category == category])
            for category in ("identifier", "concept", "multi_hop")
        },
        "latency_ms": {"p50": percentile(latencies, 0.5), "p95": percentile(latencies, 0.95)},
        "leaks": [leak for result in results for leak in result.leaks],
        "failures": [r.id for r in answerable if r.recall_at_20 == 0],
        "items": [asdict(result) for result in results],
    }


def cell(group: object, metric: str) -> str:
    """Format `0.412 (0.31-0.52)`, or a dash for an empty group."""
    assert isinstance(group, dict)
    if metric not in group:
        return "-"
    low, high = group[metric]["ci95"]
    return f"{group[metric]['mean']:.3f} ({low:.3f}-{high:.3f})"


def table(rows: list[tuple[str, object]]) -> list[str]:
    lines = [
        "| Group | n | P@5 (95% CI) | P@5 ceiling | Recall@20 (95% CI) | MRR (95% CI) |",
        "|---|---|---|---|---|---|",
    ]
    for label, group in rows:
        assert isinstance(group, dict)
        ceiling = f"{group['p_ceiling']:.3f}" if "p_ceiling" in group else "-"
        lines.append(
            f"| {label} | {group['n']} | {cell(group, 'p_at_5')} | {ceiling} "
            f"| {cell(group, 'recall_at_20')} | {cell(group, 'mrr')} |"
        )
    return lines


def header(report: dict[str, object]) -> list[str]:
    return [
        f"- Set: `{report['set']}` ({report['set_size']} items), date {report['date']}",
        f"- Git SHA: `{report['git_sha']}`",
        f"- Corpus: {report['corpus']}",
        f"- Labels: {report['labels']}",
        "- Metrics use answerable items; the headline rows use `real` items only.",
        "- P@5 ceiling: the best P@5 the labels allow, since few chunks may be relevant.",
    ]


def render_config(report: dict[str, object]) -> str:
    latency = report["latency_ms"]
    assert isinstance(latency, dict) and isinstance(report["real_by_category"], dict)
    rows: list[tuple[str, object]] = [("real", report["real"]), ("synthetic", report["synthetic"])]
    rows += [(f"real / {k}", v) for k, v in report["real_by_category"].items()]
    lines = [f"# Retrieval eval: {report['config_name']}", "", *header(report)]
    lines += [f"- Config `{report['config_hash']}`: `{json.dumps(report['config'])}`", ""]
    lines += [*table(rows), ""]
    lines += [f"Latency p50 {latency['p50']:.1f} ms, p95 {latency['p95']:.1f} ms.", ""]
    lines += [f"Leaks: {len(report['leaks'])}. Items with Recall@20 of 0: {report['failures']}", ""]  # type: ignore[arg-type]
    return "\n".join(lines)


def render_comparison(reports: list[dict[str, object]], hnsw: dict[str, float]) -> str:
    lines = ["# Retrieval comparison", "", *header(reports[0]), ""]
    lines += ["## real items", ""]
    lines += ["| Config | P@5 (95% CI) | Recall@20 (95% CI) | MRR (95% CI) | p50/p95 ms |"]
    lines += ["|---|---|---|---|---|"]
    for report in reports:
        latency = report["latency_ms"]
        assert isinstance(latency, dict)
        lines.append(
            f"| {report['config_name']} | {cell(report['real'], 'p_at_5')} "
            f"| {cell(report['real'], 'recall_at_20')} | {cell(report['real'], 'mrr')} "
            f"| {latency['p50']:.1f} / {latency['p95']:.1f} |"
        )
    lines += ["", "## By group, P@5 / Recall@20 / MRR means", ""]
    for report in reports:
        by_category = report["real_by_category"]
        assert isinstance(by_category, dict)
        rows: list[tuple[str, object]] = [(f"real / {k}", v) for k, v in by_category.items()]
        rows.append(("synthetic", report["synthetic"]))
        lines += [f"### {report['config_name']}", "", *table(rows), ""]
    lines += ["## Reranking", ""]
    lines += ["- `rerank_top20` only reorders the `hybrid_raw` top 20, so its Recall@20 equals"]
    lines += ["  that row by construction. `rerank_top50` can bring in other chunks."]
    lines += ["- Rows return 20 results so all metrics stay comparable; generation keeps fewer."]
    lines += [
        f"- Chunks over {RERANK_MAX_TOKENS} tokens, counted with the embedding tokenizer: "
        f"{reports[0]['chunks_over_rerank_limit']}. The cross-encoder cuts off the end of these.",
        "",
    ]
    lines += [f"## HNSW recall@{K} against exact search", ""]
    lines += ["The HNSW row is forced per transaction, not what the planner would pick here.", ""]
    lines += [f"- {group}: {value:.4f}" for group, value in hnsw.items()]
    lines.append("")
    return "\n".join(lines)


def git_sha() -> str:
    command = ["git", "rev-parse", "--short", "HEAD"]
    return subprocess.check_output(command, cwd=ROOT, text=True).strip()


def require_committed(path: Path) -> None:
    """Labels must be frozen in a commit before a run, so results cannot have shaped them."""
    command = ["git", "status", "--porcelain", "--", str(path)]
    if subprocess.check_output(command, cwd=ROOT, text=True).strip():
        sys.exit(f"{path.name} has uncommitted changes: commit the labels before an eval run")


async def corpus_summary(sessions: async_sessionmaker[AsyncSession]) -> str:
    async with sessions() as session:
        chunks = await session.scalar(
            select(func.count()).select_from(Chunk).where(Chunk.is_current)
        )
        documents = await session.scalar(select(func.count()).select_from(Document))
    return f"{documents} documents, {chunks} chunks, {get_settings().embed_model}"


async def chunks_over_rerank_limit(sessions: async_sessionmaker[AsyncSession]) -> int:
    statement = (
        select(func.count())
        .select_from(Chunk)
        .where(Chunk.is_current, Chunk.token_count > RERANK_MAX_TOKENS)
    )
    async with sessions() as session:
        return await session.scalar(statement) or 0


async def resolve_config(name: str, embedder: HttpEmbedder) -> RetrievalConfig:
    """Record the model the service runs, so the report and its config hash name the real one."""
    config = CONFIGS[name]
    if config.method != "rerank":
        return config
    return config.model_copy(update={"rerank_model": await embedder.rerank_model()})


def unmatched_anchors(items: list[EvalItem], corpus: dict[UUID, CorpusChunk]) -> list[str]:
    """One problem per anchor that matches no chunk."""
    return [
        f"{item.id}: no chunk of {anchor.doc_id} holds: {anchor.quote}"
        for item in items
        for anchor, chunks in zip(item.relevant, anchor_chunks(item, corpus), strict=True)
        if not chunks
    ]


def duplicate_passages(items: list[EvalItem]) -> list[str]:
    """One problem per anchor pair repeating a passage: Recall would count it twice."""
    return [
        f"{item.id}: same passage twice in {first.doc_id}: {first.quote}"
        for item in items
        for first, second in combinations(item.relevant, 2)
        if first.doc_id == second.doc_id and same_passage(first.quote, second.quote)
    ]


def check(items: list[EvalItem], corpus: dict[UUID, CorpusChunk]) -> list[str]:
    return unmatched_anchors(items, corpus) + duplicate_passages(items)


def blocking_problems(
    items: list[EvalItem], corpus: dict[UUID, CorpusChunk], *, allow_unmatched: bool
) -> list[str]:
    """What stops a run. Only a chunking experiment may lose an anchor: other boundaries can split
    a quote too evenly to match, and it then counts as a miss. Duplicates always stop a run."""
    if allow_unmatched:
        return duplicate_passages(items)
    return check(items, corpus)


async def tenant_ids(sessions: async_sessionmaker[AsyncSession]) -> dict[str, UUID]:
    async with sessions() as session:
        rows = await session.execute(select(Tenant.slug, Tenant.id))
        return {row.slug: row.id for row in rows}


async def hnsw_recall(
    items: list[EvalItem], sessions: async_sessionmaker[AsyncSession], embedder: Embedder
) -> dict[str, float]:
    """Mean recall per group, so a mean over mostly public results cannot hide private ones."""
    groups = {"all items": items}
    for kind in ("real", "synthetic"):
        groups[kind] = [item for item in items if item.answerable and item.data_kind == kind]
    return {
        group: mean(
            await measure([(i.query, i.ask_as_tenant) for i in members], sessions, embedder)
        )
        for group, members in groups.items()
        if members
    }


async def evaluate(
    set_name: str, config_name: str, label: str | None = None, *, allow_unmatched: bool = False
) -> None:
    """Run one config or `all`. `label` keeps an experiment's report apart from the main row."""
    if label and config_name == "all":
        sys.exit("a label needs a single config")
    path = DATASETS / f"{set_name}.jsonl"
    require_committed(path)
    items = load_items(path)
    sessions = db.get_sessionmaker()
    embedder = http_embedder()
    corpus = await load_corpus(sessions)
    problems = blocking_problems(items, corpus, allow_unmatched=allow_unmatched)
    if problems:
        sys.exit("\n".join(problems))
    tenants = await tenant_ids(sessions)
    await embedder.embed_query("warm up")  # the first call loads the model
    names = list(CONFIGS) if config_name == "all" else [config_name]
    if any(CONFIGS[name].method == "rerank" for name in names):
        await embedder.rerank("warm up", [(uuid4(), "warm up")], 1)
    today = date.today().isoformat()
    meta: dict[str, object] = {
        "set": set_name,
        "set_size": len(items),
        "date": today,
        "git_sha": git_sha(),
        "corpus": await corpus_summary(sessions),
        "labels": "drafted by Claude (an AI model), reviewed item by item by Vinh",
        "chunks_over_rerank_limit": await chunks_over_rerank_limit(sessions),
        "unmatched_anchors": len(unmatched_anchors(items, corpus)),
    }
    REPORTS.mkdir(exist_ok=True)
    reports = []
    for config_key in names:
        config = await resolve_config(config_key, embedder)
        retriever = build_retriever(config, sessions, embedder, embedder)
        results = [
            await run_item(item, config, retriever, tenants[item.ask_as_tenant], corpus)
            for item in items
        ]
        name = f"{config_key}_{label}" if label else config_key
        report = build_report(name, config, results, meta)
        reports.append(report)
        stem = REPORTS / f"{today}_{set_name}_{name}"
        stem.with_suffix(".json").write_text(json.dumps(report, indent=2) + "\n")
        stem.with_suffix(".md").write_text(render_config(report))
        print(f"{name}: {cell(report['real'], 'p_at_5')}")
    if config_name == "all":
        hnsw = await hnsw_recall(items, sessions, embedder)
        comparison = render_comparison(reports, hnsw)
        (REPORTS / f"{today}_{set_name}_comparison.md").write_text(comparison)
    leaks = [leak for report in reports for leak in report["leaks"]]  # type: ignore[attr-defined]
    if leaks:
        sys.exit("cross-tenant leak:\n" + "\n".join(leaks))


async def run_check(set_name: str) -> None:
    items = load_items(DATASETS / f"{set_name}.jsonl")
    problems = check(items, await load_corpus(db.get_sessionmaker()))
    print("\n".join(problems) or f"{len(items)} items, every anchor matches a chunk")
    if problems:
        sys.exit(1)


def main() -> None:
    args = [arg for arg in sys.argv[1:] if arg != ALLOW_UNMATCHED]
    if args[0] == "--check":
        asyncio.run(run_check(args[1]))
    else:
        asyncio.run(evaluate(*args[:3], allow_unmatched=ALLOW_UNMATCHED in sys.argv))


if __name__ == "__main__":
    main()
