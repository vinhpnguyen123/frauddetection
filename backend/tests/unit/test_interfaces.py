import inspect

import pytest
from pydantic import BaseModel, ValidationError

from app.generation.llm import FakeLLMProvider
from app.retrieval.fts import FtsRetriever
from app.retrieval.protocols import Retriever


class Answer(BaseModel):
    text: str


@pytest.mark.parametrize("retriever", [Retriever, FtsRetriever])
def test_context_is_required_and_keyword_only(retriever: type) -> None:
    parameter = inspect.signature(retriever.search).parameters["context"]
    assert parameter.kind is inspect.Parameter.KEYWORD_ONLY
    assert parameter.default is inspect.Parameter.empty


async def test_fake_llm_returns_recorded_responses_in_order() -> None:
    llm = FakeLLMProvider([{"text": "first"}, {"text": "second"}])
    first = await llm.generate_json(system="s", user="u", schema=Answer)
    second = await llm.generate_json(system="s", user="u", schema=Answer)
    assert (first, second) == (Answer(text="first"), Answer(text="second"))


async def test_fake_llm_validates_against_the_schema() -> None:
    llm = FakeLLMProvider([{"wrong": "shape"}])
    with pytest.raises(ValidationError):
        await llm.generate_json(system="s", user="u", schema=Answer)
