"""One live Gemini call (M5-S1 check). Needs GEMINI_API_KEY and GEMINI_MODEL in .env.

The schema is nested on purpose: Pydantic emits `$defs`/`$ref` for it, which is the shape the
answer schema will have, so this proves Gemini accepts it. Sends only a public-domain question.
"""

import asyncio
import time

from pydantic import BaseModel

from app.generation.llm import gemini_provider


class Claim(BaseModel):
    text: str
    citations: list[str]


class Answer(BaseModel):
    claims: list[Claim]


async def main() -> None:
    llm = gemini_provider()
    started = time.perf_counter()
    try:
        result = await llm.generate_json(
            system="Answer in one claim. Cite the evidence id given.",
            user='<evidence id="e1">A CTR is filed for cash over $10,000.</evidence> '
            "When is a CTR filed?",
            schema=Answer,
        )
    finally:
        await llm.client.aclose()
    print(f"model={llm.model} latency_ms={(time.perf_counter() - started) * 1000:.0f}")
    print(result.model_dump_json(indent=2))


if __name__ == "__main__":
    asyncio.run(main())
