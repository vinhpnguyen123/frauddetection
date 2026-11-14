"""Q2 auxiliary metrics; historical chunk precision and anchor recall stay unchanged."""

from collections.abc import Mapping, Sequence
from uuid import UUID

from eval.runner.metrics import (
    bootstrap_ci,
    mean,
    precision_at_5,
    precision_ceiling,
    recall_at_20,
    reciprocal_rank,
)


def score_reviewed(
    ranked: Sequence[UUID],
    anchors: Sequence[set[UUID]],
    *,
    sufficiency: bool | None = None,
) -> dict[str, float | None]:
    """Run identically for original or explicitly adjudicated anchor sets.

    Unknown sufficiency stays null. Recall@5 is chunk-based; historical Recall@20
    remains anchor-based. Ceiling normalization is per-query and only auxiliary.
    """
    if not anchors or any(not a for a in anchors):
        raise ValueError("answerable reviewed queries need nonempty evidence anchor sets")
    relevant = set().union(*anchors)
    p5 = precision_at_5(ranked, relevant)
    ceiling = precision_ceiling(relevant)
    return {
        "p_at_5": p5,
        "recall_at_20": recall_at_20(ranked, anchors),
        "mrr": reciprocal_rank(ranked, relevant),
        "hit_at_5": float(bool(set(ranked[:5]) & relevant)),
        "recall_at_5": len(set(ranked[:5]) & relevant) / len(relevant),
        "p_at_5_ceiling": ceiling,
        "ceiling_normalized_p_at_5": p5 / ceiling,
        "evidence_sufficiency_at_5": None if sufficiency is None else float(sufficiency),
    }


def paired_difference(before: Mapping[str, float], after: Mapping[str, float]) -> dict[str, object]:
    """Fixed-seed query bootstrap of paired deltas, never subtract independent CIs."""
    if not before or before.keys() != after.keys():
        raise ValueError("paired comparison requires identical nonempty query IDs")
    differences = [after[k] - before[k] for k in sorted(before)]
    return {
        "n": len(differences),
        "mean_delta": mean(differences),
        "ci95": list(bootstrap_ci(differences)),
    }
