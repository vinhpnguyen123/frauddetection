"""Eval set items, as specified in docs/EVALUATION.md §1."""

import hashlib
from pathlib import Path
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, model_validator

ROOT = Path(__file__).resolve().parents[2]
DATASETS = ROOT / "eval" / "datasets"


class LabelProvenance(BaseModel):
    """Bind a labeling declaration to the exact dataset bytes it describes."""

    model_config = ConfigDict(extra="forbid")

    dataset_sha256: str
    drafted_by: str
    reviewed_by: str | None

    def description(self) -> str:
        review = (
            f"reviewed item by item by {self.reviewed_by}"
            if self.reviewed_by
            else "not human-reviewed"
        )
        return f"drafted by {self.drafted_by}; {review}"


def load_provenance(path: Path) -> LabelProvenance:
    """Reject stale provenance rather than carry a review claim onto edited labels."""
    metadata = path.with_suffix(".meta.json")
    provenance = LabelProvenance.model_validate_json(metadata.read_text())
    if provenance.dataset_sha256 != hashlib.sha256(path.read_bytes()).hexdigest():
        raise ValueError(f"{metadata.name}: dataset hash mismatch; update labeling provenance")
    return provenance


class Anchor(BaseModel):
    model_config = ConfigDict(extra="forbid")

    doc_id: str
    page: int
    quote: str


class EvalItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    query: str
    answerable: bool
    category: Literal["identifier", "concept", "multi_hop"] | None = None
    data_kind: Literal["real", "synthetic", "adversarial"]
    ask_as_tenant: str
    relevant: list[Anchor]
    expected_refusal: (
        Literal["out_of_scope", "insufficient_evidence", "conflicting_evidence"] | None
    ) = None
    must_not_contain: list[str] = []
    notes: str = ""

    @model_validator(mode="after")
    def labels_match_answerable(self) -> Self:
        """An answerable item needs anchors and a category; a refusal has neither."""
        if self.answerable and (not self.relevant or not self.category):
            raise ValueError(f"{self.id}: an answerable item needs anchors and a category")
        if not self.answerable and (self.relevant or not self.expected_refusal):
            raise ValueError(f"{self.id}: a refusal item needs expected_refusal and no anchors")
        return self


def load_items(path: Path) -> list[EvalItem]:
    """Read a JSONL set. Raises on a malformed item or a repeated id."""
    lines = [line for line in path.read_text().splitlines() if line.strip()]
    items = [EvalItem.model_validate_json(line) for line in lines]
    if len({item.id for item in items}) != len(items):
        raise ValueError(f"{path.name}: repeated item id")
    return items
