"""Uses fake models: CI has neither torch nor weights."""

from collections.abc import Iterator
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from config import get_settings
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


def test_healthz_names_the_reranker_without_loading_a_model() -> None:
    app.dependency_overrides[get_settings] = lambda: SimpleNamespace(rerank_model="some/model")
    response = TestClient(app).get("/healthz")
    app.dependency_overrides.clear()
    assert response.json() == {"status": "ok", "rerank_model": "some/model"}


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


def test_diagnostic_request_keeps_scores_and_returns_no_input_content(
    client: TestClient, reranker: FakeRerankModel, monkeypatch: pytest.MonkeyPatch
) -> None:
    import main

    monkeypatch.setattr(
        main,
        "get_settings",
        lambda: SimpleNamespace(
            rerank_model="fixture-model", rerank_model_revision="fixture-revision"
        ),
    )
    monkeypatch.setattr(main, "inspect_pairs", lambda model, pairs: [{"count_only": True}])
    normal = client.post(
        "/rerank", json={"query": "sensitive query", "documents": ["private passage"]}
    )
    detailed = client.post(
        "/rerank",
        json={"query": "sensitive query", "documents": ["private passage"], "diagnostics": True},
    )
    assert normal.json() == {"scores": [0.0]}
    assert detailed.json()["scores"] == normal.json()["scores"]
    assert detailed.json()["diagnostics"]["scores"] == normal.json()["scores"]
    assert "private passage" not in detailed.text and "sensitive query" not in detailed.text
    assert reranker.seen == [("sensitive query", "private passage")]


def test_model_metadata_uses_an_explicit_allowlist() -> None:
    settings = SimpleNamespace(
        embed_model="embed",
        embed_model_revision="e-rev",
        embed_code_revision="code-rev",
        rerank_model="rank",
        rerank_model_revision="r-rev",
        api_key="DO-NOT-EXPORT",
    )
    app.dependency_overrides[get_settings] = lambda: settings
    try:
        response = TestClient(app).get("/metadata")
    finally:
        app.dependency_overrides.clear()
    assert response.json()["rerank_model_revision"] == "r-rev"
    assert "DO-NOT-EXPORT" not in response.text and "api_key" not in response.text
