"""LLM interface. Real providers arrive in M5-S1."""

from typing import Any, Protocol

from pydantic import BaseModel


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
