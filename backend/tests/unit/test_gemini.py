"""GeminiProvider against a mock transport: no network, every failure path."""

import json
from typing import Any

import httpx
import pytest
from pydantic import BaseModel

from app.errors import LLMOutputInvalid, RateLimited
from app.generation.llm import MAX_ATTEMPTS, GeminiProvider


class Claim(BaseModel):
    text: str
    citations: list[str]


class Answer(BaseModel):
    claims: list[Claim]


GOOD = {"claims": [{"text": "A CTR is filed over $10,000.", "citations": ["c1"]}]}


def ok(payload: Any, finish: str = "STOP") -> httpx.Response:
    text = payload if isinstance(payload, str) else json.dumps(payload)
    body = {"candidates": [{"content": {"parts": [{"text": text}]}, "finishReason": finish}]}
    return httpx.Response(200, json=body)


def provider(*responses: httpx.Response | Exception) -> tuple[GeminiProvider, list[Any]]:
    queue = list(responses)
    requests: list[httpx.Request] = []
    sleeps: list[float] = []

    def handle(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        item = queue.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    async def sleep(seconds: float) -> None:
        sleeps.append(seconds)

    client = httpx.AsyncClient(
        base_url="https://gemini.test/v1beta", transport=httpx.MockTransport(handle)
    )
    return GeminiProvider(client, model="flash-test", sleep=sleep), [requests, sleeps]


async def ask(llm: GeminiProvider) -> BaseModel:
    return await llm.generate_json(system="sys", user="question", schema=Answer)


async def test_valid_answer_is_parsed_and_request_has_schema() -> None:
    llm, (requests, _) = provider(ok(GOOD))
    assert await ask(llm) == Answer.model_validate(GOOD)
    request = requests[0]
    assert request.url.path == "/v1beta/models/flash-test:generateContent"
    body = json.loads(request.content)
    assert body["systemInstruction"] == {"parts": [{"text": "sys"}]}
    assert body["contents"] == [{"role": "user", "parts": [{"text": "question"}]}]
    config = body["generationConfig"]
    assert config["responseMimeType"] == "application/json"
    assert config["responseJsonSchema"] == Answer.model_json_schema()
    assert config["temperature"] == 0.0


async def test_429_raises_rate_limited_without_retry() -> None:
    llm, (requests, sleeps) = provider(httpx.Response(429))
    with pytest.raises(RateLimited):
        await ask(llm)
    assert len(requests) == 1 and sleeps == []


async def test_5xx_then_success_retries_with_backoff() -> None:
    llm, (requests, sleeps) = provider(httpx.Response(503), ok(GOOD))
    assert await ask(llm) == Answer.model_validate(GOOD)
    assert len(requests) == 2 and sleeps == [2.0]


async def test_timeouts_stop_after_max_attempts() -> None:
    errors = [httpx.ReadTimeout("slow") for _ in range(MAX_ATTEMPTS)]
    llm, (requests, _) = provider(*errors)
    with pytest.raises(httpx.ReadTimeout):
        await ask(llm)
    assert len(requests) == MAX_ATTEMPTS


async def test_persistent_5xx_raises_after_max_attempts() -> None:
    llm, (requests, _) = provider(*[httpx.Response(500) for _ in range(MAX_ATTEMPTS)])
    with pytest.raises(httpx.HTTPStatusError):
        await ask(llm)
    assert len(requests) == MAX_ATTEMPTS


async def test_client_error_is_not_retried() -> None:
    llm, (requests, _) = provider(httpx.Response(400))
    with pytest.raises(httpx.HTTPStatusError):
        await ask(llm)
    assert len(requests) == 1


@pytest.mark.parametrize(
    "response",
    [
        ok("not json"),
        ok({"claims": [{"text": "no citations field"}]}),
        ok(GOOD, finish="MAX_TOKENS"),
        httpx.Response(200, json={"promptFeedback": {"blockReason": "SAFETY"}}),
        httpx.Response(200, json={"candidates": []}),
    ],
    ids=["bad-json", "wrong-schema", "truncated", "blocked", "no-candidates"],
)
async def test_unusable_output_raises_llm_output_invalid(response: httpx.Response) -> None:
    llm, _ = provider(response)
    with pytest.raises(LLMOutputInvalid):
        await ask(llm)


async def test_thought_parts_are_skipped() -> None:
    parts = [{"text": "thinking...", "thought": True}, {"text": json.dumps(GOOD)}]
    body = {"candidates": [{"content": {"parts": parts}, "finishReason": "STOP"}]}
    llm, _ = provider(httpx.Response(200, json=body))
    assert await ask(llm) == Answer.model_validate(GOOD)
