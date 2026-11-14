"""Content-free diagnostics returned only for explicitly instrumented model calls."""

from pydantic import BaseModel, ConfigDict, Field


class TokenVisibility(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query_tokens: int = Field(ge=0)
    document_tokens: int = Field(ge=0)
    special_tokens: int = Field(ge=0)
    input_tokens: int = Field(ge=0)
    effective_tokens: int = Field(ge=0)
    retained_query_tokens: int = Field(ge=0)
    retained_document_tokens: int = Field(ge=0)
    effective_limit: int = Field(gt=0)
    truncated: bool
    document_visible_ranges: list[tuple[int, int]]
    input_ids_sha256: str


class RerankDiagnostics(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model: str
    model_revision: str
    tokenizer_revision: str
    scoring_ms: float = Field(ge=0)
    token_inspection_ms: float = Field(ge=0)
    scores: list[float]
    tokens: list[TokenVisibility]
