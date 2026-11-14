"""Review pooling is blind, deterministic, provenance-preserving and label-neutral."""

from uuid import UUID

import pytest
from eval.runner.dataset import EvalItem
from eval.runner.relevance_review import make_pool, review_id
from eval.runner.review_metrics import paired_difference, score_reviewed
from eval.runner.tracing import Candidate, GoldEvidence, QueryTrace, Stage

from app.retrieval.config import RetrievalConfig


def uid(n: int) -> UUID:
    return UUID(int=n)


def fixtures() -> tuple[EvalItem, QueryTrace, list[dict[str, object]]]:
    item = EvalItem(
        id="dev-fixture",
        query="fixture question",
        answerable=True,
        category="concept",
        data_kind="real",
        ask_as_tenant="fixture",
        relevant=[{"doc_id": "source", "page": 1, "quote": "fixture evidence"}],
    )
    config = RetrievalConfig(method="hybrid", dense_mode="exact")
    candidate = Candidate(
        chunk_id=uid(1), document_id=uid(10), version_id=uid(20), rank=1, score=1, method="fixture"
    )
    trace = QueryTrace(
        query_id=item.id,
        config_hash=config.config_hash(),
        config=config,
        gold=[GoldEvidence(anchor_id="a1", chunk_ids=[uid(2)])],
        stages=[
            Stage(
                name=n,
                candidates=[candidate],
                retained_anchor_ids=[],
                elapsed_ms=0,
                timing="inclusive",
            )
            for n in ("bm25", "dense", "rrf_top20", "final_top20")
        ],
        reranker_inputs=[],
        reranker_metadata={},
        diagnostics={},
    )
    passages = [
        dict(
            id=uid(i),
            version_id=uid(20),
            ordinal=i,
            section_path="section",
            spans=[{"page": i}],
            text="fixture evidence" if i < 3 else "neighbor",
            doc_key="source",
            title="source",
            status="active",
            authority="advisory",
        )
        for i in (1, 2, 3)
    ]
    return item, trace, passages


def test_pool_blinds_rank_gold_and_method_and_retains_duplicate_occurrences() -> None:
    item, trace, passages = fixtures()
    cards, keys, summary = make_pool(item, trace, passages)
    assert summary == {
        "query_id": item.id,
        "gold_chunks": 1,
        "pooled_chunks": 3,
        "review_units": 2,
        "judged_units": 0,
    }
    assert all(c["judgment"] is None for c in cards)
    for card in cards:
        assert not {"sources", "rank", "score", "existing_relevant"} & card.keys()
        for occurrence in card["occurrences"]:
            assert not {"sources", "rank", "score", "existing_relevant"} & occurrence.keys()
    merged = next(c for c in cards if len(c["occurrences"]) == 2)
    key = next(k for k in keys if k["review_id"] == merged["review_id"])
    assert [o["existing_relevant"] for o in key["occurrences"]] == [False, True]
    assert make_pool(item, trace, list(reversed(passages))) == (cards, keys, summary)
    assert len(item.relevant) == 1  # building never changes the original dataset item


def test_pool_refuses_unreadable_or_stale_candidate() -> None:
    item, trace, passages = fixtures()
    with pytest.raises(ValueError, match="unauthorized"):
        make_pool(item, trace, passages[1:])


def test_dedup_does_not_merge_distinct_documents_or_versions() -> None:
    assert review_id("q", "d", "v", "same") != review_id("q", "other", "v", "same")
    assert review_id("q", "d", "v", "same") != review_id("q", "d", "next", "same")


def test_auxiliary_metrics_keep_anchor_and_chunk_recall_distinct() -> None:
    result = score_reviewed([uid(1)], [{uid(1), uid(2)}, {uid(1)}])
    assert result["p_at_5"] == 0.2
    assert result["recall_at_20"] == 1
    assert result["recall_at_5"] == 0.5
    assert result["p_at_5_ceiling"] == 0.4
    assert result["ceiling_normalized_p_at_5"] == 0.5
    assert result["evidence_sufficiency_at_5"] is None
    assert score_reviewed([uid(1)], [{uid(1)}], sufficiency=False)["evidence_sufficiency_at_5"] == 0


def test_paired_bootstrap_requires_same_queries() -> None:
    assert paired_difference({"a": 0, "b": 1}, {"a": 1, "b": 2}) == {
        "n": 2,
        "mean_delta": 1,
        "ci95": [1, 1],
    }
    with pytest.raises(ValueError):
        paired_difference({"a": 1}, {"b": 1})
    with pytest.raises(ValueError):
        score_reviewed([], [set()])


def test_sufficiency_sets_are_blinded_deduplicated_and_unjudged() -> None:
    from eval.runner.relevance_review import sufficiency_sets

    item, trace, passages = fixtures()
    cards, _, _ = make_pool(item, trace, passages)
    sets, key = sufficiency_sets(trace, cards)
    assert len(sets) == 1  # all four methods returned the same top-five set in this fixture
    assert len(key) == 4
    assert sets[0]["sufficient"] is None
    assert "method" not in sets[0]
    assert "rank" not in sets[0]
    assert len(sets[0]["review_ids"]) == 1
