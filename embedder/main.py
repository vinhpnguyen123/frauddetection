"""Embedding and reranking over HTTP. Models load on first use, so /healthz needs no weights."""

from functools import lru_cache
from threading import Lock
from typing import Annotated, Any, Literal

from fastapi import Depends, FastAPI
from pydantic import BaseModel, Field

from config import get_settings

# Document and query embeddings need different task prefixes. They are added only here, so a
# client cannot forget them.
PREFIXES = {"document": "search_document: ", "query": "search_query: "}
MAX_BATCH = 256

# One model call at a time: the dev machine has 8 GB, and two loads at once would not fit.
model_lock = Lock()

app = FastAPI(title="FinbudAI embedder")


class EmbedRequest(BaseModel):
    texts: list[str] = Field(min_length=1, max_length=MAX_BATCH)
    kind: Literal["document", "query"]


class EmbedResponse(BaseModel):
    embeddings: list[list[float]]


class RerankRequest(BaseModel):
    query: str
    documents: list[str] = Field(min_length=1, max_length=MAX_BATCH)


class RerankResponse(BaseModel):
    scores: list[float]


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


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


# Plain `def`: FastAPI runs these in a thread, keeping slow model calls off the event loop.
@app.post("/embed")
def embed(request: EmbedRequest, model: Annotated[Any, Depends(embed_model)]) -> EmbedResponse:
    """Embed texts with the task prefix for `kind`."""
    prefix = PREFIXES[request.kind]
    with model_lock:
        vectors = model.encode([prefix + text for text in request.texts])
    return EmbedResponse(embeddings=vectors.tolist())


@app.post("/rerank")
def rerank(request: RerankRequest, model: Annotated[Any, Depends(rerank_model)]) -> RerankResponse:
    """Score each document against the query, in input order."""
    with model_lock:
        scores = model.predict([(request.query, document) for document in request.documents])
    return RerankResponse(scores=scores.tolist())
