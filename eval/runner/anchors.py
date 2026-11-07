"""Decide whether a chunk holds a labeled passage. Labels are text anchors, not chunk ids."""

import math
import re
import unicodedata
from difflib import SequenceMatcher

STRADDLE_SHARE = 0.6  # a quote cut by a chunk boundary counts with this share of its tokens
SAME_PASSAGE_CHARS = 45  # shared letters and digits; below this, a stock phrase can match


def squash(text: str) -> str:
    """Keep only lowercase letters and digits.

    Ignores whitespace, case, punctuation and line-break hyphens ("laun- dering") at once.
    A false match would need a whole 8 to 20 word quote to collide, so word boundaries can go.
    """
    folded = unicodedata.normalize("NFKC", text).lower()
    return re.sub(r"[^a-z0-9]", "", folded)


def holds_quote(chunk_text: str, quote: str) -> bool:
    """True if the chunk holds the whole quote, or the part a chunk boundary left in it.

    A cut quote must touch the boundary: its start closes the chunk, or its end opens it. The
    same words elsewhere in a chunk are not a cut, since the text may go on to say otherwise.
    """
    chunk = squash(chunk_text)
    if squash(quote) in chunk:
        return True
    tokens = quote.split()
    needed = math.ceil(STRADDLE_SHARE * len(tokens))
    return any(
        chunk.endswith(squash(" ".join(tokens[:kept])))
        or chunk.startswith(squash(" ".join(tokens[-kept:])))
        for kept in range(needed, len(tokens))
    )


def same_passage(first: str, second: str) -> bool:
    """True if two quotes overlap, so two anchors would count one passage twice in Recall."""
    a, b = squash(first), squash(second)
    shared = SequenceMatcher(None, a, b, autojunk=False).find_longest_match()
    return shared.size >= min(SAME_PASSAGE_CHARS, len(a), len(b))
