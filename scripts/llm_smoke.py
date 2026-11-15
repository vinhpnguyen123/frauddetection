"""One live Gemini call with the real answer prompt and schema. Needs GEMINI_API_KEY/MODEL.

Proves Gemini accepts the `LLMAnswer` schema (nested `$defs`, a nullable refusal) and that
ANSWER_PROMPT_V1 yields labelled citations. Sends only a made-up public-style snippet.
"""

import asyncio
import time
from uuid import uuid4

from app.generation.citations import answer_problems
from app.generation.llm import gemini_provider
from app.generation.prompts import ANSWER_PROMPT_V1, answer_user_message
from app.retrieval.evidence import Evidence
from app.schemas.answer import LLMAnswer

EVIDENCE = Evidence(
    chunk_id=uuid4(),
    version_id=uuid4(),
    text="A bank must file a CTR for each cash transaction of more than $10,000.",
    section_path="CTR > Filing",
    spans=[],
    title="Smoke snippet",
    source="fincen",
    authority="regulation",
    status="active",
    published_date=None,
)


async def main() -> None:
    llm = gemini_provider()
    labelled = {"E1": EVIDENCE}
    questions = ["When must a bank file a CTR?", "What is the capital of France?"]
    try:
        for question in questions:
            started = time.perf_counter()
            result = await llm.generate_json(
                system=ANSWER_PROMPT_V1.system,
                user=answer_user_message(question, labelled),
                schema=LLMAnswer,
            )
            assert isinstance(result, LLMAnswer)
            elapsed = (time.perf_counter() - started) * 1000
            print(f"model={llm.model} latency_ms={elapsed:.0f} question={question!r}")
            print(f"problems={answer_problems(result, labelled)}")
            print(result.model_dump_json(indent=2))
    finally:
        await llm.client.aclose()


if __name__ == "__main__":
    asyncio.run(main())
