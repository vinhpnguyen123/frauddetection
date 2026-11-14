"""Inspect token visibility without returning input text or reversible token IDs."""

import hashlib
import json
from typing import Any


# Any: the optional sentence-transformers model and HF tokenizer are absent from CI.
def inspect_pairs(model: Any, pairs: list[tuple[str, str]]) -> list[dict[str, object]]:
    """Verify diagnostic tokenization against the model's actual preprocessing.

    Only text-pair models whose offsets reproduce their real inputs are supported. A mismatch
    fails closed; it must never silently report guessed truncation or change inference inputs.
    """
    tokenizer = model.tokenizer
    limit = int(model.max_seq_length)
    queries, documents = zip(*pairs, strict=True)
    actual = model.preprocess(pairs)
    encoded = tokenizer(
        list(queries),
        list(documents),
        padding=True,
        truncation="longest_first",
        max_length=limit,
        return_offsets_mapping=True,
    )
    full_queries = tokenizer(list(queries), add_special_tokens=False)["input_ids"]
    full_documents = tokenizer(list(documents), add_special_tokens=False)["input_ids"]
    actual_ids = actual["input_ids"].tolist()
    actual_mask = actual["attention_mask"].tolist()
    found = []
    for i in range(len(pairs)):
        ids = [v for v, mask in zip(actual_ids[i], actual_mask[i], strict=True) if mask]
        expected = [
            v
            for v, mask in zip(encoded["input_ids"][i], encoded["attention_mask"][i], strict=True)
            if mask
        ]
        if ids != expected:
            raise ValueError("diagnostic tokenizer does not reproduce model preprocessing")
        sequence = encoded.sequence_ids(i)
        query_count = sum(s == 0 for s in sequence)
        doc_count = sum(s == 1 for s in sequence)
        offsets = [
            offset
            for s, offset in zip(sequence, encoded["offset_mapping"][i], strict=True)
            if s == 1
        ]
        special = len(ids) - query_count - doc_count
        total = len(full_queries[i]) + len(full_documents[i]) + special
        found.append(
            {
                "query_tokens": len(full_queries[i]),
                "document_tokens": len(full_documents[i]),
                "special_tokens": special,
                "input_tokens": total,
                "effective_tokens": len(ids),
                "retained_query_tokens": query_count,
                "retained_document_tokens": doc_count,
                "effective_limit": limit,
                "truncated": total > len(ids),
                "document_visible_ranges": [(offsets[0][0], offsets[-1][1])] if offsets else [],
                "input_ids_sha256": hashlib.sha256(json.dumps(ids).encode()).hexdigest(),
            }
        )
    return found
