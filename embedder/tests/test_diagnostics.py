"""Token diagnostics must match the actual model input, including query and special tokens."""

import pytest

from diagnostics import inspect_pairs


class Tensor(list):
    def tolist(self) -> list:
        return list(self)


class Encoding(dict):
    def sequence_ids(self, index: int) -> list:
        return [None, 0, 0, None, 1, 1, 1, None]


class Tokenizer:
    def __call__(self, queries: list, documents: list | None = None, **kwargs: object) -> dict:
        if documents is None:
            return {"input_ids": [[10, 11] if queries[0] == "query" else list(range(6))]}
        return Encoding(
            {
                "input_ids": [[101, 10, 11, 102, 20, 21, 22, 102]],
                "attention_mask": [[1] * 8],
                "offset_mapping": [
                    [(0, 0), (0, 2), (3, 5), (0, 0), (0, 3), (4, 7), (8, 13), (0, 0)]
                ],
            }
        )


class Model:
    max_seq_length = 8
    tokenizer = Tokenizer()

    def preprocess(self, pairs: list) -> dict:
        return {
            "input_ids": Tensor([[101, 10, 11, 102, 20, 21, 22, 102]]),
            "attention_mask": Tensor([[1] * 8]),
        }


def test_actual_input_budget_and_visible_offsets_are_content_free() -> None:
    result = inspect_pairs(Model(), [("query", "document")])[0]
    assert result["input_tokens"] == 11
    assert result["effective_tokens"] == 8
    assert result["retained_query_tokens"] == 2
    assert result["retained_document_tokens"] == 3
    assert result["special_tokens"] == 3
    assert result["truncated"] is True
    assert result["document_visible_ranges"] == [(0, 13)]
    assert "document" not in str(result.values()) and "query" not in str(result.values())


def test_a_diagnostic_model_input_mismatch_fails_closed() -> None:
    model = Model()
    model.preprocess = lambda _: {
        "input_ids": Tensor([[999] * 8]),
        "attention_mask": Tensor([[1] * 8]),
    }
    with pytest.raises(ValueError, match="does not reproduce"):
        inspect_pairs(model, [("query", "document")])
