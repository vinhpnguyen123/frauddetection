"""Uses fake models: CI has neither torch nor weights."""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from main import app, embed_model, rerank_model


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
