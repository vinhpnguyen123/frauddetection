"""The answer contract: what the LLM must return, and what the caller gets back."""

from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel

RefusalCode = Literal["out_of_scope", "insufficient_evidence", "conflicting_evidence"]


# --- LLM output (docs/ARCHITECTURE.md §6). Citations are evidence labels such as "E2";
# code maps them back to chunk ids, because copying 36-character UUIDs invites typos.
# Every field is required (no defaults) so the JSON schema sent to Gemini stays plain.


class LLMClaim(BaseModel):
    text: str
    citations: list[str]


class LLMRefusal(BaseModel):
    code: RefusalCode
    message: str


class LLMAnswer(BaseModel):
    type: Literal["answer", "refusal"]
    claims: list[LLMClaim]
    refusal: LLMRefusal | None


# --- Returned to the caller (eval now, `/ask` from M6-S2).


class Citation(BaseModel):
    chunk_id: UUID
    version_id: UUID
    title: str
    spans: list[dict[str, Any]]  # Any: [{"page": int, "bbox": [...]}] for the PDF highlight
    excerpt: str


class Claim(BaseModel):
    text: str
    citations: list[Citation]


class Refusal(BaseModel):
    code: RefusalCode
    message: str


class Answer(BaseModel):
    type: Literal["answer", "refusal"]
    claims: list[Claim]
    refusal: Refusal | None
    dropped_claims: int  # claims removed because their citations stayed invalid after a retry
    retried: bool
    prompt_version: str
