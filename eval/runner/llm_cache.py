"""Disk cache for eval LLM calls (docs/EVALUATION.md §5), itself an LLMProvider.

Re-runs only call the API for changed inputs, and a run cut off by a 429 resumes from here.
Only validated results are written, so an error or invalid output is never cached.
"""

import hashlib
import json
import os
from pathlib import Path

from pydantic import BaseModel

from app.generation.llm import LLMProvider

DEFAULT_DIR = Path(__file__).resolve().parents[1] / ".cache" / "llm"  # eval/.cache is ignored


class CachedLLMProvider:
    def __init__(
        self,
        inner: LLMProvider,
        *,
        provider: str,
        model: str,
        prompt_version: str,
        directory: Path = DEFAULT_DIR,
    ) -> None:
        self.inner = inner
        self.provider = provider
        self.model = model
        self.prompt_version = prompt_version
        self.directory = directory

    def key(self, system: str, user: str, schema: type[BaseModel], temperature: float) -> str:
        # EVALUATION §5 key plus temperature: a changed temperature must not hit an old answer.
        parts = [
            self.provider,
            self.model,
            self.prompt_version,
            system,
            user,
            schema.model_json_schema(),
            temperature,
        ]
        return hashlib.sha256(json.dumps(parts, sort_keys=True).encode()).hexdigest()

    async def generate_json(
        self, *, system: str, user: str, schema: type[BaseModel], temperature: float = 0.0
    ) -> BaseModel:
        path = self.directory / f"{self.key(system, user, schema, temperature)}.json"
        if path.exists():
            return schema.model_validate_json(path.read_text())
        result = await self.inner.generate_json(
            system=system, user=user, schema=schema, temperature=temperature
        )
        self.directory.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".tmp")
        temporary.write_text(result.model_dump_json())
        os.replace(temporary, path)  # atomic: a crash never leaves half a file to read back
        return result
