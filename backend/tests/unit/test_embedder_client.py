"""The embedder client, on a fake transport: nothing here touches the network."""

import json
from collections.abc import Callable

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
