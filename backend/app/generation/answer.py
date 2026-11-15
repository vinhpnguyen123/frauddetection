"""The answer path: retrieve → read evidence through the ACL → generate → check citations.

Refusal from multiple signals (scores, conflicts, scope) is M5-S3; here only the model's own
refusal and the no-evidence case produce one.
"""

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.errors import LLMOutputInvalid
from app.generation.citations import answer_problems, claim_is_valid
from app.generation.llm import LLMProvider
from app.generation.prompts import ANSWER_PROMPT_V1, answer_user_message, retry_message
from app.retrieval.config import RetrievalConfig
from app.retrieval.evidence import Evidence, load_evidence
from app.retrieval.protocols import RetrievalContext, Retriever
from app.schemas.answer import Answer, Citation, Claim, LLMAnswer, Refusal, RefusalCode

EXCERPT_CHARS = 300
PROMPT = ANSWER_PROMPT_V1


async def answer_question(
    question: str,
    *,
    context: RetrievalContext,
    retriever: Retriever,
    llm: LLMProvider,
    sessions: async_sessionmaker[AsyncSession],
    config: RetrievalConfig,
) -> Answer:
    """Answer from evidence the context may read. Claims with invalid citations get one retry,
    then are dropped and counted; a valid label always maps to a chunk read through the ACL."""
    if config.final_k is None:
        raise ValueError("the answer path needs final_k in its RetrievalConfig")
    hits = await retriever.search(question, context=context, limit=config.final_k)
    evidence = await load_evidence(
        sessions,
        [hit.chunk_id for hit in hits],
        context=context,
        parent_expansion=config.parent_expansion,
    )
    if not evidence:
        return refusal("insufficient_evidence", "No readable evidence answers this question.")

    labelled = {f"E{number}": item for number, item in enumerate(evidence, start=1)}
    user = answer_user_message(question, labelled)
    raw = await generate(llm, user)
    problems = answer_problems(raw, labelled)
    retried = bool(problems)
    if retried:
        raw = await generate(llm, retry_message(user, problems))
    return build_answer(raw, labelled, retried=retried)


async def generate(llm: LLMProvider, user: str) -> LLMAnswer:
    result = await llm.generate_json(system=PROMPT.system, user=user, schema=LLMAnswer)
    if not isinstance(result, LLMAnswer):  # a provider must return the schema it was given
        raise LLMOutputInvalid(f"expected LLMAnswer, got {type(result).__name__}")
    return result


def build_answer(raw: LLMAnswer, labelled: dict[str, Evidence], *, retried: bool) -> Answer:
    if raw.type == "refusal":
        if raw.refusal is None:  # still inconsistent after the retry
            raise LLMOutputInvalid("refusal without a refusal object")
        return refusal(raw.refusal.code, raw.refusal.message, retried=retried)
    kept = [claim for claim in raw.claims if claim_is_valid(claim, labelled)]
    claims = [
        Claim(text=claim.text, citations=[citation(labelled[label]) for label in claim.citations])
        for claim in kept
    ]
    return Answer(
        type="answer",
        claims=claims,
        refusal=None,
        dropped_claims=len(raw.claims) - len(kept),
        retried=retried,
        prompt_version=PROMPT.version,
    )


def citation(evidence: Evidence) -> Citation:
    return Citation(
        chunk_id=evidence.chunk_id,
        version_id=evidence.version_id,
        title=evidence.title,
        spans=evidence.spans,
        excerpt=evidence.text[:EXCERPT_CHARS],
    )


def refusal(code: RefusalCode, message: str, *, retried: bool = False) -> Answer:
    return Answer(
        type="refusal",
        claims=[],
        refusal=Refusal(code=code, message=message),
        dropped_claims=0,
        retried=retried,
        prompt_version=PROMPT.version,
    )
