"""Uses fake models: CI has neither torch nor weights."""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from main import MAX_BATCH, app, embed_model, rerank_model, tokenizer


class Array(list):
    def tolist(self) -> list:
        return list(self)


class FakeEmbedModel:
    def __init__(self) -> None:
        self.seen: list[str] = []

    def encode(self, texts: list[str]) -> Array:
        self.seen = texts
        return Array([[1.0, 2.0] for _ in texts])


class FakeRerankModel:
    def __init__(self) -> None:
        self.seen: list[tuple[str, str]] = []

    def predict(self, pairs: list[tuple[str, str]]) -> Array:
        self.seen = pairs
        return Array([float(i) for i, _ in enumerate(pairs)])


class FakeTokenizer:
    def __init__(self) -> None:
        self.special_tokens: list[bool] = []

    def __call__(self, texts: list[str], add_special_tokens: bool) -> dict[str, list[list[int]]]:
        self.special_tokens.append(add_special_tokens)
        return {"input_ids": [[0] * len(text.split()) for text in texts]}


@pytest.fixture
def embedder() -> FakeEmbedModel:
    return FakeEmbedModel()


@pytest.fixture
def reranker() -> FakeRerankModel:
    return FakeRerankModel()


@pytest.fixture
def client(embedder: FakeEmbedModel, reranker: FakeRerankModel) -> Iterator[TestClient]:
    app.dependency_overrides[embed_model] = lambda: embedder
    app.dependency_overrides[rerank_model] = lambda: reranker
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_healthz_needs_no_model() -> None:
    assert TestClient(app).get("/healthz").json() == {"status": "ok"}


@pytest.mark.parametrize(
    ("kind", "expected"),
    [("document", "search_document: wire"), ("query", "search_query: wire")],
)
def test_embed_adds_the_task_prefix(
    client: TestClient, embedder: FakeEmbedModel, kind: str, expected: str
) -> None:
    response = client.post("/embed", json={"texts": ["wire"], "kind": kind})
    assert response.status_code == 200
    assert embedder.seen == [expected]
    assert response.json() == {"embeddings": [[1.0, 2.0]]}


@pytest.mark.parametrize(
    "body",
    [
        {"texts": ["wire"]},
        {"texts": ["wire"], "kind": "other"},
        {"texts": [], "kind": "query"},
        {"texts": ["x"] * 257, "kind": "query"},
    ],
)
def test_embed_rejects_bad_requests(client: TestClient, body: dict) -> None:
    assert client.post("/embed", json=body).status_code == 422


def test_rerank_scores_each_document_without_a_prefix(
    client: TestClient, reranker: FakeRerankModel
) -> None:
    response = client.post("/rerank", json={"query": "q", "documents": ["a", "b"]})
    assert reranker.seen == [("q", "a"), ("q", "b")]
    assert response.json() == {"scores": [0.0, 1.0]}


def test_tokens_counts_each_text_without_special_tokens() -> None:
    fake = FakeTokenizer()
    app.dependency_overrides[tokenizer] = lambda: fake
    try:
        response = TestClient(app).post("/tokens", json={"texts": ["one two", "three"]})
    finally:
        app.dependency_overrides.clear()
    assert response.json() == {"counts": [2, 1]}
    assert fake.special_tokens == [False]


@pytest.mark.parametrize("texts", [[], ["x"] * (MAX_BATCH + 1)], ids=["empty", "too-many"])
def test_tokens_rejects_a_bad_batch(texts: list[str]) -> None:
    app.dependency_overrides[tokenizer] = FakeTokenizer
    try:
        assert TestClient(app).post("/tokens", json={"texts": texts}).status_code == 422
    finally:
        app.dependency_overrides.clear()
