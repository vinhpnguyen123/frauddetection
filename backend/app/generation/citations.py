"""Citation validity, checked in code: is each cited label one of the evidence we sent?

Every evidence label maps to a chunk read through the ACL, so a valid label is also a chunk the
user may read. Validity is not support: whether the chunk backs the claim is the judge's job.
"""

from collections.abc import Collection

from app.schemas.answer import LLMAnswer, LLMClaim


def claim_is_valid(claim: LLMClaim, labels: Collection[str]) -> bool:
    return bool(claim.citations) and all(label in labels for label in claim.citations)


def answer_problems(answer: LLMAnswer, labels: Collection[str]) -> list[str]:
    """Describe what is wrong, in words the model can act on during the retry. Empty = valid."""
    if answer.type == "refusal":
        return [] if answer.refusal is not None else ['type is "refusal" but "refusal" is null']
    if not answer.claims:
        return ['type is "answer" but "claims" is empty']
    problems = []
    for number, claim in enumerate(answer.claims, start=1):
        if not claim.citations:
            problems.append(f"claim {number} has no citations")
        unknown = sorted(set(claim.citations) - set(labels))
        if unknown:
            problems.append(f"claim {number} cites labels that do not exist: {unknown}")
    return problems
