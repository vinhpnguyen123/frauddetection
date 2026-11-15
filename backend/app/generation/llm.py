"""LLM interface and providers. Business logic depends on `LLMProvider` only."""

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any, Protocol

import httpx
from pydantic import BaseModel, ValidationError

from app.config import get_settings
from app.errors import LLMOutputInvalid, RateLimited

MAX_ATTEMPTS = 3
RETRYABLE_STATUS = {500, 502, 503, 504}  # 429 is not here: it surfaces as RateLimited


class LLMProvider(Protocol):
    async def generate_json(
        self, *, system: str, user: str, schema: type[BaseModel], temperature: float = 0.0
    ) -> BaseModel: ...


class FakeLLMProvider:
    """Returns recorded responses in order, so tests never touch the network."""

    # Any: recorded JSON, checked against `schema` when it is returned.
    def __init__(self, responses: list[dict[str, Any]]) -> None:
        self._responses = list(responses)

    async def generate_json(
        self, *, system: str, user: str, schema: type[BaseModel], temperature: float = 0.0
    ) -> BaseModel:
        return schema.model_validate(self._responses.pop(0))


class GeminiProvider:
    """Gemini `generateContent` over REST, with the output constrained to `schema`.

    Guarantees: the result is validated by Pydantic, or `LLMOutputInvalid` is raised;
    a 429 raises `RateLimited` at once; only timeouts, connection errors and 5xx are retried,
    at most MAX_ATTEMPTS times. Prompts and answers are never logged.
    """

    def __init__(
        self,
        client: httpx.AsyncClient,
        *,
        model: str,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self.client = client
        self.model = model
        self.sleep = sleep

    async def generate_json(
        self, *, system: str, user: str, schema: type[BaseModel], temperature: float = 0.0
    ) -> BaseModel:
        body = {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": user}]}],
            "generationConfig": {
                # The docs say newer Flash models ignore temperature; sent for older ones.
                "temperature": temperature,
                "responseMimeType": "application/json",
                "responseJsonSchema": schema.model_json_schema(),
            },
        }
        text = response_text(await self._post(body))
        try:
            return schema.model_validate_json(text)
        except ValidationError as error:
            raise LLMOutputInvalid(f"output does not match {schema.__name__}") from error

    async def _post(self, body: dict[str, Any]) -> dict[str, Any]:
        path = f"/models/{self.model}:generateContent"
        for attempt in range(1, MAX_ATTEMPTS + 1):
            try:
                response = await self.client.post(path, json=body)
            except httpx.TransportError:  # includes timeouts
                if attempt == MAX_ATTEMPTS:
                    raise
            else:
                if response.status_code == 429:
                    raise RateLimited(f"gemini 429 on {self.model}")
                if response.status_code not in RETRYABLE_STATUS or attempt == MAX_ATTEMPTS:
                    response.raise_for_status()  # 400/401/404 = config bug: fail loudly
                    result: dict[str, Any] = response.json()
                    return result
            await self.sleep(2.0**attempt)
        raise AssertionError("unreachable: the last attempt returns or raises")


# Any: the raw Gemini response body, read field by field below.
def response_text(data: dict[str, Any]) -> str:
    """Return the answer text, or raise LLMOutputInvalid if the call produced no usable answer.

    A blocked prompt has no candidates; any finish other than STOP (e.g. MAX_TOKENS) means the
    JSON may be cut off, so it is rejected rather than parsed. Thought parts are skipped.
    """
    block = data.get("promptFeedback", {}).get("blockReason")
    if block:
        raise LLMOutputInvalid(f"prompt blocked: {block}")
    candidates = data.get("candidates") or []
    if not candidates:
        raise LLMOutputInvalid("no candidates")
    candidate = candidates[0]
    if candidate.get("finishReason") != "STOP":
        raise LLMOutputInvalid(f"finish reason {candidate.get('finishReason')}")
    parts = candidate.get("content", {}).get("parts", [])
    return "".join(part.get("text", "") for part in parts if not part.get("thought"))


def gemini_provider(client: httpx.AsyncClient | None = None) -> GeminiProvider:
    """Build the provider from settings. The caller owns closing the client."""
    settings = get_settings()
    # Empty values count as missing: .env.example ships them blank.
    if not settings.gemini_api_key or not settings.gemini_api_key.get_secret_value():
        raise ValueError("GEMINI_API_KEY and GEMINI_MODEL must be set to call Gemini")
    if not settings.gemini_model:
        raise ValueError("GEMINI_API_KEY and GEMINI_MODEL must be set to call Gemini")
    client = client or httpx.AsyncClient(
        base_url=settings.gemini_base_url,
        # Header, not query string, so the key never appears in a logged URL.
        headers={"x-goog-api-key": settings.gemini_api_key.get_secret_value()},
        timeout=settings.llm_timeout_seconds,
    )
    return GeminiProvider(client, model=settings.gemini_model)
