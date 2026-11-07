"""The embedder client, on a fake transport: nothing here touches the network."""

import json
from collections.abc import Callable
from uuid import UUID

import httpx
import pytest

from app.embedder import EMBED_BATCH, EMBED_DIMENSIONS, MAX_ATTEMPTS, TOKENS_BATCH, HttpEmbedder

Handler = Callable[[httpx.Request], httpx.Response]
VECTOR = [0.5] * EMBED_DIMENSIONS


def client_for(handler: Handler, sleeps: list[float] | None = None) -> HttpEmbedder:
    seen = [] if sleeps is None else sleeps

    async def sleep(seconds: float) -> None:
        seen.append(seconds)

    transport = httpx.MockTransport(handler)
    return HttpEmbedder(httpx.AsyncClient(transport=transport, base_url="http://e.test"), sleep)


def embed_ok(request: httpx.Request) -> httpx.Response:
    texts = json.loads(request.content)["texts"]
    return httpx.Response(200, json={"embeddings": [VECTOR for _ in texts]})


def scores_ok(*scores: float) -> Handler:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/rerank"
        return httpx.Response(200, json={"scores": list(scores)})

    return handler


LOW = UUID(int=1)
HIGH = UUID(int=2)
CANDIDATES = [(LOW, "low id"), (HIGH, "high id")]


async def test_rerank_orders_by_score_and_applies_top_k() -> None:
    hits = await client_for(scores_ok(0.1, 0.9)).rerank("query", CANDIDATES, 1)
    assert [(hit.chunk_id, hit.score, hit.rank, hit.method) for hit in hits] == [
        (HIGH, 0.9, 1, "rerank")
    ]


async def test_rerank_sends_documents_in_candidate_order() -> None:
    sent: list[dict[str, object]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        sent.append(json.loads(request.content))
        return httpx.Response(200, json={"scores": [0.1, 0.2]})

    await client_for(handler).rerank("query", CANDIDATES, 2)
    assert sent == [{"query": "query", "documents": ["low id", "high id"]}]


async def test_rerank_tie_goes_to_the_lower_chunk_id() -> None:
    hits = await client_for(scores_ok(0.5, 0.5)).rerank("query", CANDIDATES[::-1], 2)
    assert [hit.chunk_id for hit in hits] == [LOW, HIGH]


async def test_rerank_without_candidates_sends_no_request() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("no request expected")

    assert await client_for(handler).rerank("query", [], 5) == []


async def test_rerank_rejects_a_wrong_score_count() -> None:
    with pytest.raises(ValueError, match="expected 2 scores"):
        await client_for(scores_ok(0.5)).rerank("query", CANDIDATES, 2)


async def test_rerank_model_comes_from_the_service() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/healthz"
        return httpx.Response(200, json={"status": "ok", "rerank_model": "some/model"})

    assert await client_for(handler).rerank_model() == "some/model"


async def test_documents_are_sent_in_batches_and_keep_their_order() -> None:
    sizes: list[int] = []
    kinds: set[str] = set()

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        sizes.append(len(payload["texts"]))
        kinds.add(payload["kind"])
        vectors = [[float(text)] * EMBED_DIMENSIONS for text in payload["texts"]]
        return httpx.Response(200, json={"embeddings": vectors})

    texts = [str(index) for index in range(EMBED_BATCH + 5)]
    vectors = await client_for(handler).embed_documents(texts)
    assert sizes == [EMBED_BATCH, 5]
    assert kinds == {"document"}
    assert [vector[0] for vector in vectors] == [float(text) for text in texts]


async def test_query_uses_the_query_kind() -> None:
    kinds: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        kinds.append(json.loads(request.content)["kind"])
        return embed_ok(request)

    assert await client_for(handler).embed_query("wire") == VECTOR
    assert kinds == ["query"]


async def test_no_texts_means_no_request() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("no request expected")

    client = client_for(handler)
    assert await client.embed_documents([]) == []
    assert await client.count_tokens([]) == []


@pytest.mark.parametrize(
    "embeddings", [[[0.5, 0.5]], [VECTOR, VECTOR]], ids=["wrong-size", "wrong-count"]
)
async def test_a_wrong_response_is_rejected(embeddings: list[list[float]]) -> None:
    client = client_for(lambda _: httpx.Response(200, json={"embeddings": embeddings}))
    with pytest.raises(ValueError, match="768"):
        await client.embed_documents(["one"])


async def test_token_counts_are_batched() -> None:
    sizes: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        texts = json.loads(request.content)["texts"]
        sizes.append(len(texts))
        return httpx.Response(200, json={"counts": [1 for _ in texts]})

    counts = await client_for(handler).count_tokens(["x"] * (TOKENS_BATCH + 1))
    assert sizes == [TOKENS_BATCH, 1]
    assert len(counts) == TOKENS_BATCH + 1


async def test_server_errors_are_retried_with_backoff() -> None:
    answers = [httpx.Response(503), httpx.Response(503)]
    sleeps: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        return answers.pop() if answers else embed_ok(request)

    assert await client_for(handler, sleeps).embed_documents(["x"]) == [VECTOR]
    assert sleeps == [2.0, 4.0]


async def test_retries_give_up() -> None:
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(503)

    with pytest.raises(httpx.HTTPStatusError):
        await client_for(handler).embed_documents(["x"])
    assert len(calls) == MAX_ATTEMPTS


async def test_transport_errors_give_up() -> None:
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        raise httpx.ConnectError("down")

    with pytest.raises(httpx.ConnectError):
        await client_for(handler).embed_query("x")
    assert len(calls) == MAX_ATTEMPTS


async def test_a_bad_request_is_not_retried() -> None:
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(422)

    with pytest.raises(httpx.HTTPStatusError):
        await client_for(handler).embed_documents(["x"])
    assert calls == [1]
