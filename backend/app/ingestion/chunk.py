"""chunk_v1: section-aware chunks of about 500 tokens. See docs/DATASET.md §5.

Packing works on sentences, so overlap never starts in the middle of one. A chunk belongs to
exactly one section. A footnote follows the paragraph that refers to it, and the two are packed
as one, so a rule and its exception share a chunk whenever they fit in one.
"""

import hashlib
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from itertools import groupby

from app.ingestion.parse import (
    BBox,
    Block,
    ParsedDocument,
    Section,
    continues_sentence,
    join_blocks,
)

TARGET_TOKENS = 500
MAX_TOKENS = 700
OVERLAP_TOKENS = 50

SENTENCE_BREAK = re.compile(r"(?<=[.!?])\s+(?=[A-Z“\"(])")

CountTokens = Callable[[list[str]], Awaitable[list[int]]]


@dataclass(frozen=True)
class ChunkConfig:
    """Sizes in tokens. `per_paragraph` starts a new chunk at every paragraph."""

    target: int = TARGET_TOKENS
    max: int = MAX_TOKENS
    overlap: int = OVERLAP_TOKENS
    per_paragraph: bool = False


CHUNK_V1 = ChunkConfig()


@dataclass(frozen=True)
class Span:
    page: int
    bbox: BBox


@dataclass(frozen=True)
class Chunk:
    ordinal: int  # position within the document version
    section_ordinal: int
    section_path: str
    text: str
    token_count: int
    spans: tuple[Span, ...]
    content_hash: str


@dataclass(frozen=True)
class Unit:
    """A sentence, or a piece of one that was too long."""

    text: str
    tokens: int
    block: int  # index of its block, because units of one block join with a space
    paragraph: int  # blocks of one paragraph and its footnotes share this
    span: Span
    attached: bool  # a footnote: stays with what comes before it when the size allows


def reading_order(section: Section) -> list[tuple[Block, int]]:
    """Blocks with their paragraph number. A paragraph may span several blocks and pages, so its
    footnotes wait for its end instead of cutting a sentence. Unreferenced footnotes go last."""
    bodies = [block for block in section.blocks if block.kind == "body"]
    notes = [block for block in section.blocks if block.kind == "footnote"]
    ordered: list[tuple[Block, int]] = []
    waiting: list[Block] = []
    paragraph = 0
    for block, following in zip(bodies, [*bodies[1:], None], strict=True):
        ordered.append((block, paragraph))
        keys = {(block.page, mark) for mark in block.marks}
        waiting += [note for note in notes if note.note_key in keys]
        notes = [note for note in notes if note.note_key not in keys]
        if following is None or not continues_sentence(block.text, following.text):
            ordered += [(note, paragraph) for note in waiting]
            waiting = []
            paragraph += 1
    return ordered + [(note, paragraph + index) for index, note in enumerate(notes)]


def halve(text: str) -> tuple[str, str]:
    """Split near the middle, on a space if there is one: a URL can outgrow any limit alone."""
    middle = len(text) // 2
    left, right = text.rfind(" ", 0, middle), text.find(" ", middle)
    candidates = [cut for cut in (left, right) if cut > 0]
    cut = min(candidates, key=lambda c: abs(c - middle)) if candidates else middle
    return text[:cut].strip(), text[cut:].strip()


async def fit(texts: list[str], count_tokens: CountTokens, target: int) -> list[tuple[str, int]]:
    """Measure texts, halving any that exceed the target until all of them fit."""
    fitted: list[tuple[str, int]] = []
    for text, tokens in zip(texts, await count_tokens(texts), strict=True):
        if tokens > target:
            fitted += await fit(list(halve(text)), count_tokens, target)
        else:
            fitted.append((text, tokens))
    return fitted


async def section_units(section: Section, count_tokens: CountTokens, target: int) -> list[Unit]:
    blocks = reading_order(section)
    sentences = [
        (index, sentence)
        for index, (block, _) in enumerate(blocks)
        for sentence in SENTENCE_BREAK.split(block.text)
        if sentence.strip()
    ]
    counts = await count_tokens([sentence for _, sentence in sentences]) if sentences else []
    units: list[Unit] = []
    for (index, sentence), tokens in zip(sentences, counts, strict=True):
        block, paragraph = blocks[index]
        pieces = [(sentence, tokens)]
        if tokens > target:
            pieces = await fit([sentence], count_tokens, target)
        units += [
            Unit(
                text=text,
                tokens=size,
                block=index,
                paragraph=paragraph,
                span=Span(block.page, block.bbox),
                attached=block.kind == "footnote",
            )
            for text, size in pieces
        ]
    return units


def overlap_tail(units: list[Unit], overlap: int) -> list[Unit]:
    """The last whole sentences of a chunk, up to the overlap size."""
    tail: list[Unit] = []
    size = 0
    for unit in reversed(units):
        size += unit.tokens
        if size > overlap:
            break
        tail.insert(0, unit)
    return tail


def size_of(units: list[Unit]) -> int:
    return sum(unit.tokens for unit in units)


def bundles(units: list[Unit], config: ChunkConfig) -> list[list[Unit]]:
    """What packing must not split: a paragraph with footnotes, if it fits in one chunk next to
    the overlap. Everything else can break between sentences."""
    result: list[list[Unit]] = []
    for _, members in groupby(units, key=lambda unit: unit.paragraph):
        group = list(members)
        keep = group[-1].attached and size_of(group) <= config.max - config.overlap
        result += [group] if keep else [[unit] for unit in group]
    return result


def pack(units: list[Unit], config: ChunkConfig) -> list[list[Unit]]:
    """Fill chunks up to the target. Only a footnote may push a chunk past it, up to the max."""
    groups: list[list[Unit]] = []
    current: list[Unit] = []
    fresh = 0  # bundles that are new to this chunk, so overlap alone never makes a chunk
    for bundle in bundles(units, config):
        size = size_of(current)
        full = size >= config.target and not bundle[0].attached
        new_paragraph = (
            config.per_paragraph and bool(current) and bundle[0].paragraph != current[-1].paragraph
        )
        if fresh and (full or new_paragraph or size + size_of(bundle) > config.max):
            groups.append(current)
            current = overlap_tail(current, config.overlap)
            fresh = 0
        current += bundle
        fresh += 1
    if fresh:
        groups.append(current)
    return groups


def join_units(units: list[Unit]) -> str:
    text = ""
    previous: Unit | None = None
    for unit in units:
        if previous is not None and previous.block == unit.block:
            text = f"{text} {unit.text}"
        else:
            text = join_blocks(text, unit.text)
        previous = unit
    return text


def normalized_hash(text: str) -> str:
    return hashlib.sha256(" ".join(text.split()).encode()).hexdigest()


async def chunk_document(
    document: ParsedDocument, count_tokens: CountTokens, config: ChunkConfig = CHUNK_V1
) -> list[Chunk]:
    """Chunk every section. Guarantees: never crosses a section, never exceeds `config.max`."""
    drafts: list[tuple[Section, list[Unit]]] = []
    for section in document.sections:
        units = await section_units(section, count_tokens, config.target)
        drafts += [(section, group) for group in pack(units, config)]
    texts = [join_units(group) for _, group in drafts]
    counts = await count_tokens(texts) if texts else []
    chunks = []
    for ordinal, ((section, group), text, tokens) in enumerate(
        zip(drafts, texts, counts, strict=True)
    ):
        if tokens > config.max:
            raise ValueError(f"chunk {ordinal} of {section.path!r} has {tokens} tokens")
        chunks.append(
            Chunk(
                ordinal=ordinal,
                section_ordinal=section.ordinal,
                section_path=section.path,
                text=text,
                token_count=tokens,
                spans=tuple(dict.fromkeys(unit.span for unit in group)),
                content_hash=normalized_hash(text),
            )
        )
    return chunks
