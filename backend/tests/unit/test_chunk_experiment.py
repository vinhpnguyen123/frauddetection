import pytest
from scripts.chunk_experiment import (
    VARIANTS,
    experiment_url,
    render_report,
    require_experiment,
    without_urls,
)

from app.ingestion.chunk import Chunk, normalized_hash

MAIN = "postgresql+asyncpg://user:secret@127.0.0.1:55432/frauddetection"


def test_the_main_database_is_refused() -> None:
    with pytest.raises(SystemExit, match="not an experiment copy"):
        require_experiment(MAIN)


@pytest.mark.parametrize("variant", list(VARIANTS))
def test_every_variant_gets_its_own_copy(variant: str) -> None:
    url = experiment_url(MAIN, variant)
    require_experiment(url)
    assert url.endswith(f"/frauddetection_exp_{variant}")


def test_urls_leave_the_chunk_and_its_hash_follows() -> None:
    chunk = Chunk(0, 0, "path", "See https://a.example/x for it.", 7, (), "old")
    stripped = without_urls(chunk)
    assert "https" not in stripped.text
    assert stripped.content_hash == normalized_hash(stripped.text)


def test_the_report_has_one_row_per_run() -> None:
    group = {"p_at_5": {"mean": 0.5, "ci95": [0.4, 0.6]}}
    group |= {"recall_at_20": group["p_at_5"], "mrr": group["p_at_5"]}
    stats = {"chunks": 10, "avg_tokens": 300.0, "over_limit": 0, "short": 1}
    report = {
        "set": "dev",
        "set_size": 50,
        "date": "2026-11-07",
        "git_sha": "abc1234",
        "labels": "fixture",
        "latency_ms": {"p50": 1.0, "p95": 2.0},
        "unmatched_anchors": 2,
        "real": group,
    }
    text = render_report([("chunk_300", "hybrid_raw", stats, report)])
    assert "| chunk_300 | hybrid_raw | 10 | 300.0 | 0 | 1 | 2 | 0.500 (0.400-0.600)" in text
