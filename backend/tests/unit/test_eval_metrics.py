"""Hand-computed checks: an error here would make every reported number wrong."""

from uuid import UUID, uuid4

import pytest
from eval.runner.anchors import holds_quote, same_passage, squash
from eval.runner.dataset import DATASETS, EvalItem, load_items
from eval.runner.metrics import (
    bootstrap_ci,
    percentile,
    precision_at_5,
    precision_ceiling,
    recall_at_20,
    reciprocal_rank,
)
from eval.runner.retrieval import CONFIGS, CorpusChunk, anchor_chunks, check, find_leaks

QUOTE = "a bank must file a report within thirty calendar days of initial detection"


def ids(count: int) -> list[UUID]:
    return [uuid4() for _ in range(count)]


def test_precision_divides_by_five_even_with_few_results() -> None:
    ranked = ids(3)
    assert precision_at_5(ranked, {ranked[0], ranked[2]}) == 0.4


def test_precision_ignores_results_after_the_fifth() -> None:
    ranked = ids(6)
    assert precision_at_5(ranked, {ranked[5]}) == 0.0


def test_precision_ceiling_follows_the_relevant_chunks() -> None:
    assert precision_ceiling(set(ids(1))) == 0.2
    assert precision_ceiling(set(ids(9))) == 1.0


def test_recall_counts_anchors_not_chunks() -> None:
    ranked = ids(21)
    anchors = [{ranked[0], ranked[1]}, {ranked[19]}, {ranked[20]}, set(ids(1))]
    assert recall_at_20(ranked, anchors) == 0.5


def test_reciprocal_rank_stops_at_twenty() -> None:
    ranked = ids(21)
    assert reciprocal_rank(ranked, {ranked[3]}) == 0.25
    assert reciprocal_rank(ranked, {ranked[19]}) == 0.05
    assert reciprocal_rank(ranked, {ranked[20]}) == 0.0


def test_percentile_is_nearest_rank() -> None:
    values = [5.0, 1.0, 3.0, 2.0, 4.0]
    assert percentile(values, 0.5) == 3.0
    assert percentile(values, 0.95) == 5.0
    assert percentile(values, 0.0) == 1.0


def test_bootstrap_is_repeatable_and_brackets_the_mean() -> None:
    values = [0.0, 0.0, 1.0, 1.0, 1.0, 0.0, 1.0, 0.0]
    low, high = bootstrap_ci(values)
    assert (low, high) == bootstrap_ci(values)
    assert low < 0.5 < high


def test_bootstrap_of_a_constant_has_no_width() -> None:
    assert bootstrap_ci([0.4] * 10) == pytest.approx((0.4, 0.4))


@pytest.mark.parametrize(
    "chunk",
    [
        QUOTE,
        f"Intro. {QUOTE.upper()}. Outro.",
        QUOTE.replace(" ", "\n"),
        QUOTE.replace("calendar", "calen- dar"),
        QUOTE.replace("report", "report,"),
    ],
)
def test_a_quote_matches_despite_layout(chunk: str) -> None:
    assert holds_quote(chunk, QUOTE)


def test_a_cut_quote_needs_sixty_percent_of_its_tokens() -> None:
    tokens = QUOTE.split()  # 13 tokens, so 8 are needed
    assert holds_quote("start " + " ".join(tokens[:8]), QUOTE)
    assert holds_quote(" ".join(tokens[-8:]) + " end", QUOTE)
    assert not holds_quote("start " + " ".join(tokens[:7]), QUOTE)
    assert not holds_quote(" ".join(tokens[-7:]) + " end", QUOTE)


def test_a_partial_match_inside_a_chunk_does_not_count() -> None:
    """Only a chunk boundary may cut a quote; here the text goes on and contradicts it."""
    chunk = (
        "Background: a bank must file a report within thirty business days after approval. "
        "Additional guidance follows."
    )
    assert not holds_quote(chunk, QUOTE)


def test_a_quote_end_must_open_the_chunk_to_count() -> None:
    tokens = QUOTE.split()
    assert not holds_quote("Earlier text " + " ".join(tokens[-8:]) + " end", QUOTE)


def test_a_quote_start_must_close_the_chunk_to_count() -> None:
    tokens = QUOTE.split()
    assert not holds_quote("start " + " ".join(tokens[:8]) + " more text", QUOTE)


def test_a_longer_cut_part_still_counts() -> None:
    tokens = QUOTE.split()
    assert holds_quote("start " + " ".join(tokens[:11]), QUOTE)
    assert holds_quote(" ".join(tokens[-11:]) + " end", QUOTE)


def test_tokens_from_the_middle_do_not_count_as_a_cut_quote() -> None:
    tokens = QUOTE.split()
    assert not holds_quote(" ".join(tokens[3:11]), QUOTE)


def test_squash_folds_ligatures() -> None:
    assert squash("ﬁnancial") == "financial"


def item(**changes: object) -> EvalItem:
    fields: dict[str, object] = {
        "id": "dev-001",
        "query": "q",
        "answerable": True,
        "category": "concept",
        "data_kind": "real",
        "ask_as_tenant": "bluefin",
        "relevant": [{"doc_id": "doc-a", "page": 1, "quote": QUOTE}],
    }
    return EvalItem.model_validate(fields | changes)


def test_an_anchor_matches_only_inside_its_document() -> None:
    right, wrong = uuid4(), uuid4()
    corpus = {
        right: CorpusChunk(right, "doc-a", QUOTE, None),
        wrong: CorpusChunk(wrong, "doc-b", QUOTE, None),
    }
    assert anchor_chunks(item(), corpus) == [{right}]


def test_overlapping_quotes_are_the_same_passage() -> None:
    assert same_passage(QUOTE, " ".join(QUOTE.split()[:9]))
    assert same_passage(" ".join(QUOTE.split()[:11]), " ".join(QUOTE.split()[1:]))
    stock = "reasonable measures to determine whether"
    assert not same_passage(f"{stock} a customer is a PEP", f"{stock} a beneficiary is a PEP")
    assert not same_passage(
        QUOTE, "customers must be screened against the sanctions list each quarter"
    )


def test_a_repeated_passage_is_a_problem_only_within_one_document() -> None:
    chunk_id = uuid4()
    corpus = {chunk_id: CorpusChunk(chunk_id, "doc-a", QUOTE, None)}
    prefix = " ".join(QUOTE.split()[:9])
    twice = [{"doc_id": "doc-a", "page": 1, "quote": q} for q in (QUOTE, prefix)]
    assert any("same passage" in problem for problem in check([item(relevant=twice)], corpus))
    apart = [twice[0], {"doc_id": "doc-b", "page": 1, "quote": prefix}]
    assert not any("same passage" in problem for problem in check([item(relevant=apart)], corpus))


def test_an_answerable_item_needs_anchors() -> None:
    with pytest.raises(ValueError, match="needs anchors"):
        item(relevant=[])


def test_a_refusal_item_needs_its_reason() -> None:
    with pytest.raises(ValueError, match="needs expected_refusal"):
        item(answerable=False, relevant=[], category=None)


def test_a_chunk_of_another_tenant_is_a_leak() -> None:
    mine, other, chunk_id = uuid4(), uuid4(), uuid4()
    corpus = {chunk_id: CorpusChunk(chunk_id, "doc-a", "text", other)}
    assert find_leaks(item(), [chunk_id], mine, corpus)
    assert not find_leaks(item(), [chunk_id], other, corpus)


def test_a_forbidden_string_is_a_leak() -> None:
    tenant, chunk_id = uuid4(), uuid4()
    corpus = {chunk_id: CorpusChunk(chunk_id, "doc-a", "ref ABC-CANARY", None)}
    assert find_leaks(item(must_not_contain=["ABC-CANARY"]), [chunk_id], tenant, corpus)


def test_every_config_has_its_own_hash() -> None:
    hashes = {config.config_hash() for config in CONFIGS.values()}
    assert len(hashes) == len(CONFIGS)


def test_the_dev_set_is_well_formed() -> None:
    items = load_items(DATASETS / "dev.jsonl")
    assert len(items) == 50
    quotes = [anchor.quote for item in items for anchor in item.relevant]
    assert all(8 <= len(quote.split()) <= 20 for quote in quotes)
