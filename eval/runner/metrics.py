"""Retrieval metrics, as defined in docs/EVALUATION.md §2. Pure functions, no I/O."""

import math
import random
from collections.abc import Sequence
from uuid import UUID

BOOTSTRAP_RESAMPLES = 1000
BOOTSTRAP_SEED = 20261107
P_AT = 5
RECALL_AT = 20


def precision_at_5(ranked: Sequence[UUID], relevant: set[UUID]) -> float:
    """Relevant chunks in the top 5, over 5, however few chunks are relevant."""
    return sum(chunk in relevant for chunk in ranked[:P_AT]) / P_AT


def precision_ceiling(relevant: set[UUID]) -> float:
    """The best P@5 this item allows: with one relevant chunk it is 0.2."""
    return min(len(relevant), P_AT) / P_AT


def recall_at_20(ranked: Sequence[UUID], anchors: Sequence[set[UUID]]) -> float:
    """Labeled anchors with a chunk in the top 20, over labeled anchors."""
    top = set(ranked[:RECALL_AT])
    return sum(bool(anchor & top) for anchor in anchors) / len(anchors)


def reciprocal_rank(ranked: Sequence[UUID], relevant: set[UUID]) -> float:
    """1 / rank of the first relevant chunk, or 0 if none is in the top 20."""
    for rank, chunk in enumerate(ranked[:RECALL_AT], start=1):
        if chunk in relevant:
            return 1 / rank
    return 0.0


def mean(values: Sequence[float]) -> float:
    return sum(values) / len(values)


def percentile(values: Sequence[float], share: float) -> float:
    """Nearest-rank percentile; `share` is between 0 and 1."""
    ordered = sorted(values)
    return ordered[max(math.ceil(share * len(ordered)) - 1, 0)]


def bootstrap_ci(values: Sequence[float]) -> tuple[float, float]:
    """95% percentile interval of the mean, resampling queries with a fixed seed."""
    rng = random.Random(BOOTSTRAP_SEED)
    means = [mean(rng.choices(values, k=len(values))) for _ in range(BOOTSTRAP_RESAMPLES)]
    return percentile(means, 0.025), percentile(means, 0.975)
