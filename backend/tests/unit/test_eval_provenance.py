"""Reports must not invent a human review or reuse it after a dataset changes."""

import hashlib
import json
from pathlib import Path

import pytest
from eval.runner import retrieval
from eval.runner.dataset import DATASETS, load_items, load_provenance
from eval.runner.retrieval import COMPARISON_CONFIGS, render_comparison


def write_metadata(path: Path, reviewer: str | None) -> None:
    path.with_suffix(".meta.json").write_text(
        json.dumps(
            {
                "dataset_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "drafted_by": "fixture drafter",
                "reviewed_by": reviewer,
            }
        )
    )


def test_unreviewed_labels_never_claim_a_human_review(tmp_path: Path) -> None:
    path = tmp_path / "test.jsonl"
    path.write_text("labels")
    write_metadata(path, None)
    description = load_provenance(path).description()
    assert description == "drafted by fixture drafter; not human-reviewed"
    assert "Vinh" not in description


def test_a_review_cannot_silently_follow_changed_labels(tmp_path: Path) -> None:
    path = tmp_path / "test.jsonl"
    path.write_text("original labels")
    write_metadata(path, "fixture reviewer")
    assert "reviewed item by item by fixture reviewer" in load_provenance(path).description()
    path.write_text("edited labels")
    with pytest.raises(ValueError, match="dataset hash mismatch"):
        load_provenance(path)


def test_missing_provenance_is_not_replaced_with_a_review_claim(tmp_path: Path) -> None:
    path = tmp_path / "test.jsonl"
    path.write_text("labels")
    with pytest.raises(FileNotFoundError):
        load_provenance(path)


def test_dataset_metadata_describes_the_current_bytes() -> None:
    for name in ("dev", "test"):
        assert load_provenance(DATASETS / f"{name}.jsonl").dataset_sha256


def test_test_draft_has_no_duplicate_queries_or_dev_queries() -> None:
    items = load_items(DATASETS / "test.jsonl")
    assert 30 <= len(items) <= 40
    # The same policy question under a different tenant is an intentional isolation case.
    queries = {(item.ask_as_tenant, item.query.casefold()) for item in items}
    assert len(queries) == len(items)
    assert queries.isdisjoint(
        {(i.ask_as_tenant, i.query.casefold()) for i in load_items(DATASETS / "dev.jsonl")}
    )
    assert {i.query.casefold() for i in items}.isdisjoint(
        {i.query.casefold() for i in load_items(DATASETS / "dev.jsonl")}
    )
    assert {item.ask_as_tenant for item in items} == {"bluefin", "granite", "lumen"}
    assert all(8 <= len(a.quote.split()) <= 20 for item in items for a in item.relevant)


def test_comparison_separates_the_seven_main_rows_from_expansion() -> None:
    group = {
        metric: {"mean": 0.5, "ci95": [0.4, 0.6]} for metric in ("p_at_5", "recall_at_20", "mrr")
    }
    group.update(n=1, p_ceiling=1.0)
    meta = {
        "set": "fixture",
        "set_size": 1,
        "date": "fixture",
        "git_sha": "fixture",
        "corpus": "fixture",
        "labels": "fixture",
        "chunks_over_rerank_limit": 0,
        "real": group,
        "synthetic": group,
        "real_by_category": {},
        "latency_ms": {"p50": 1.0, "p95": 2.0},
    }
    # Reverse the input order: the main table should still follow the documented order.
    reports = [
        {**meta, "config_name": name}
        for name in reversed((*COMPARISON_CONFIGS, "hybrid", "fts_raw", "bm25_raw"))
    ]
    text = render_comparison(reports, {})
    main, rest = text.split("## Query expansion experiments", 1)
    rows = [
        line.split(" | ")[0].removeprefix("| ")
        for line in main.splitlines()
        if line.startswith("| ")
    ][1:]
    assert rows == list(COMPARISON_CONFIGS)
    assert "| hybrid |" in rest
    assert "| fts_raw |" in rest
    assert "| bm25_raw |" in rest


def test_precommit_override_keeps_the_default_gate_and_fingerprints_inputs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "eval/datasets/test.jsonl"
    path.parent.mkdir(parents=True)
    path.write_text("labels")
    write_metadata(path, None)
    for folder in ("backend", "embedder"):
        (tmp_path / folder).mkdir()
        for name in ("pyproject.toml", "uv.lock"):
            (tmp_path / folder / name).write_text("fixture")
    source = tmp_path / "eval/runner/retrieval.py"
    source.parent.mkdir()
    source.write_text("original source")
    monkeypatch.setattr(retrieval, "ROOT", tmp_path)
    monkeypatch.setattr(retrieval.subprocess, "check_output", lambda *a, **kw: " M fixture")
    with pytest.raises(SystemExit, match="commit the labels"):
        retrieval.input_fingerprint(path)
    before = retrieval.input_fingerprint(path, allow_uncommitted_labels=True)
    assert before["working_tree_dirty"] is True
    assert before["allow_uncommitted_labels"] is True
    source.write_text("changed source")
    after = retrieval.input_fingerprint(path, allow_uncommitted_labels=True)
    assert before["input_sha256"] != after["input_sha256"]
