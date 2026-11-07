"""Retrieval configuration. Its hash identifies an eval run."""

import hashlib
from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.retrieval.dense import DenseMode


class RetrievalConfig(BaseModel):
    """Grows with the methods: hybrid and rerank fields arrive in M4."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    method: Literal["fts", "bm25", "dense"]
    dense_mode: DenseMode | None = None
    query_expansion: bool = False

    def config_hash(self) -> str:
        return hashlib.sha256(self.model_dump_json().encode()).hexdigest()[:12]
