"""Eval disk cache: hit, miss on any key change, and errors never cached."""

from pathlib import Path

import pytest
from eval.runner.llm_cache import CachedLLMProvider
from pydantic import BaseModel

from app.errors import RateLimited
from app.generation.llm import FakeLLMProvider


class Out(BaseModel):
    text: str


class Counting(FakeLLMProvider):
    calls = 0

    async def generate_json(
        self, *, system: str, user: str, schema: type[BaseModel], temperature: float = 0.0
    ) -> BaseModel:
        self.calls += 1
        return await super().generate_json(
            system=system, user=user, schema=schema, temperature=temperature
        )


def cached(inner: FakeLLMProvider, directory: Path, version: str = "V1") -> CachedLLMProvider:
    return CachedLLMProvider(
        inner, provider="gemini", model="m", prompt_version=version, directory=directory
    )


async def test_second_identical_call_is_served_from_disk(tmp_path: Path) -> None:
    inner = Counting([{"text": "first"}])
    llm = cached(inner, tmp_path)
    first = await llm.generate_json(system="s", user="u", schema=Out)
    again = await cached(Counting([]), tmp_path).generate_json(system="s", user="u", schema=Out)
    assert first == again == Out(text="first")
    assert inner.calls == 1


async def test_changed_prompt_version_or_input_misses(tmp_path: Path) -> None:
    inner = Counting([{"text": "a"}, {"text": "b"}, {"text": "c"}])
    await cached(inner, tmp_path).generate_json(system="s", user="u", schema=Out)
    await cached(inner, tmp_path, "V2").generate_json(system="s", user="u", schema=Out)
    await cached(inner, tmp_path).generate_json(system="s", user="other", schema=Out)
    assert inner.calls == 3


async def test_errors_are_not_cached(tmp_path: Path) -> None:
    class Limited(FakeLLMProvider):
        async def generate_json(
            self, *, system: str, user: str, schema: type[BaseModel], temperature: float = 0.0
        ) -> BaseModel:
            raise RateLimited("429")

    with pytest.raises(RateLimited):
        await cached(Limited([]), tmp_path).generate_json(system="s", user="u", schema=Out)
    assert list(tmp_path.iterdir()) == []
