"""Embedding and reranking over HTTP. Models load on first use, so /healthz needs no weights."""

from functools import lru_cache
from threading import Lock
from time import perf_counter
from typing import Annotated, Any, Literal

from fastapi import Depends, FastAPI
from pydantic import BaseModel, Field

from config import Settings, get_settings
from diagnostics import inspect_pairs

# Document and query embeddings need different task prefixes. They are added only here, so a
# client cannot forget them.
PREFIXES = {"document": "search_document: ", "query": "search_query: "}
MAX_BATCH = 256

# One model call at a time: the dev machine has 8 GB, and two loads at once would not fit.
model_lock = Lock()

app = FastAPI(title="FraudDetection embedder")


class EmbedRequest(BaseModel):
    texts: list[str] = Field(min_length=1, max_length=MAX_BATCH)
    kind: Literal["document", "query"]


class EmbedResponse(BaseModel):
    embeddings: list[list[float]]


class TokensRequest(BaseModel):
    texts: list[str] = Field(min_length=1, max_length=MAX_BATCH)


class TokensResponse(BaseModel):
    counts: list[int]


class RerankRequest(BaseModel):
    query: str
    documents: list[str] = Field(min_length=1, max_length=MAX_BATCH)
    diagnostics: bool = False


class RerankResponse(BaseModel):
    scores: list[float]
    diagnostics: dict[str, Any] | None = None  # Any: optional content-free ML diagnostics


# Any: sentence-transformers is an optional dependency, absent from CI.
@lru_cache
def load_embed_model() -> Any:
    from sentence_transformers import SentenceTransformer

    settings = get_settings()
    pin = {"code_revision": settings.embed_code_revision}
    return SentenceTransformer(
        settings.embed_model,
        revision=settings.embed_model_revision,
        trust_remote_code=True,  # required by nomic-embed; both revisions above are pinned
        model_kwargs=pin,
        config_kwargs=pin,
    )


# Any: transformers is an optional dependency, absent from CI.
@lru_cache
def load_tokenizer() -> Any:
    """Only the tokenizer, so counting tokens never loads the model weights."""
    from transformers import AutoTokenizer

    settings = get_settings()
    return AutoTokenizer.from_pretrained(
        settings.embed_model, revision=settings.embed_model_revision
    )


@lru_cache
def load_rerank_model() -> Any:
    from sentence_transformers import CrossEncoder

    settings = get_settings()
    return CrossEncoder(settings.rerank_model, revision=settings.rerank_model_revision)


def embed_model() -> Any:
    with model_lock:
        return load_embed_model()


def rerank_model() -> Any:
    with model_lock:
        return load_rerank_model()


def tokenizer() -> Any:
    with model_lock:
        return load_tokenizer()


@app.get("/healthz")
def healthz(settings: Annotated[Settings, Depends(get_settings)]) -> dict[str, str]:
    """Name the reranker from settings, so eval reports record it without loading weights."""
    return {"status": "ok", "rerank_model": settings.rerank_model}


@app.get("/metadata")
def metadata(settings: Annotated[Settings, Depends(get_settings)]) -> dict[str, str]:
    """Pinned model identities only; never expose arbitrary environment variables."""
    return {
        "embed_model": settings.embed_model,
        "embed_model_revision": settings.embed_model_revision,
        "embed_code_revision": settings.embed_code_revision,
        "rerank_model": settings.rerank_model,
        "rerank_model_revision": settings.rerank_model_revision,
    }


# Plain `def`: FastAPI runs these in a thread, keeping slow model calls off the event loop.
@app.post("/embed")
def embed(request: EmbedRequest, model: Annotated[Any, Depends(embed_model)]) -> EmbedResponse:
    """Embed texts with the task prefix for `kind`."""
    prefix = PREFIXES[request.kind]
    with model_lock:
        vectors = model.encode([prefix + text for text in request.texts])
    return EmbedResponse(embeddings=vectors.tolist())


@app.post("/tokens")
def tokens(request: TokensRequest, counter: Annotated[Any, Depends(tokenizer)]) -> TokensResponse:
    """Count tokens without the task prefix or special tokens, as chunk sizes are measured."""
    encoded = counter(request.texts, add_special_tokens=False)
    return TokensResponse(counts=[len(ids) for ids in encoded["input_ids"]])


@app.post("/rerank", response_model_exclude_none=True)
def rerank(
    request: RerankRequest,
    model: Annotated[Any, Depends(rerank_model)],
) -> RerankResponse:
    """Score each document against the query, in input order."""
    with model_lock:
        pairs = [(request.query, document) for document in request.documents]
        if not request.diagnostics:
            return RerankResponse(scores=model.predict(pairs).tolist())
        started = perf_counter()
        scores = model.predict(pairs).tolist()
        scoring_ms = (perf_counter() - started) * 1000
        details = None
        if request.diagnostics:
            settings = get_settings()
            started = perf_counter()
            tokens = inspect_pairs(model, pairs)
            details = {
                "model": settings.rerank_model,
                "model_revision": settings.rerank_model_revision,
                "tokenizer_revision": settings.rerank_model_revision,
                "scoring_ms": scoring_ms,
                "token_inspection_ms": (perf_counter() - started) * 1000,
                "scores": scores,
                "tokens": tokens,
            }
    return RerankResponse(scores=scores, diagnostics=details)
