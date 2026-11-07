"""Retrieval configuration. Its hash identifies an eval run."""

import hashlib
from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.retrieval.dense import DenseMode


class RetrievalConfig(BaseModel):
    """Grows with the methods. `k_bm25`, `k_dense` and `rrf_k` apply to hybrid only."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    method: Literal["fts", "bm25", "dense", "hybrid"]
    dense_mode: DenseMode | None = None
    query_expansion: bool = False
    k_bm25: int = 50
    k_dense: int = 50
    rrf_k: int = 60

    def config_hash(self) -> str:
        return hashlib.sha256(self.model_dump_json().encode()).hexdigest()[:12]
