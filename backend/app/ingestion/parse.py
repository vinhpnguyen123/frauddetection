"""Parse a PDF into sections of text blocks with page and bbox. See docs/DATASET.md §5.

Reading order is the order stored in the PDF, not a sort by position: the corpus stores two-column
pages column by column, and sorting by position would mix columns and could scramble tables.
"""

import math
import re
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

import pymupdf

# No ligatures, so "ﬁnancial" is searchable as "financial". No images, which are never used.
TEXT_FLAGS = (
    pymupdf.TEXTFLAGS_DICT & ~pymupdf.TEXT_PRESERVE_LIGATURES & ~pymupdf.TEXT_PRESERVE_IMAGES
)

MARGIN_SHARE = 0.10  # top and bottom share of a page where headers and footers live
REPEAT_SHARE = 0.4  # a margin line on this share of the pages is a running header or footer
HEADING_MIN_GROWTH = 0.75  # points above the body size that make a line a heading
NOTE_MAX_SIZE_GAP = 0.4  # points below the body size that make a bottom line a footnote
HEADING_MAX_CHARS = 120
MIN_CHARS_PER_PAGE = 200
MAX_SINGLE_CHAR_RATIO = 0.2

PAGE_NUMBER = re.compile(r"\W*(page\s*)?\d+(\s*(of|/)\s*\d+)?\W*", re.IGNORECASE)
UNPRINTABLE = re.compile("[\x00-\x08\x0e-\x1f\u00ad\ue000-\uf8ff]")  # controls, icon glyphs
DOT_LEADER = re.compile(r"(\.\s?){5,}")
SENTENCE_END = '.!?:;”"'
WORD = re.compile(r"[A-Za-z]{3}")
CONTENTS_TITLES = {"contents", "table of contents"}
NOTE_NUMBER = re.compile(r"(\d{1,3})(?:[.)]|\s|$)")
NOTE_NUMBER_ONLY = re.compile(r"\d{1,3}[.)]?")
MARK = re.compile(r"[\d,\s]+")
LIST_ITEM = re.compile(r"[•▪○◦*–-]\s|\d{1,2}[.)]\s")

BBox = tuple[float, float, float, float]


@dataclass(frozen=True)
class Line:
    page: int  # 1-based, as the PDF viewer counts
    bbox: BBox  # PDF points, origin at the top left of the page
    text: str
    size: float
    bold: bool
    marks: tuple[str, ...] = ()  # footnote numbers this line refers to


@dataclass(frozen=True)
class Block:
    page: int
    bbox: BBox
    text: str
    kind: Literal["body", "footnote"]


@dataclass(frozen=True)
class Section:
    path: str  # 'Overview > Filing Timeframes'; empty before the first heading
    text: str  # body first, then footnotes, so a footnote never cuts a sentence
    page_start: int
    page_end: int
    ordinal: int
    blocks: tuple[Block, ...]


@dataclass(frozen=True)
class ParsedDocument:
    page_count: int
    sections: tuple[Section, ...]
    single_char_ratio: float


def clean(text: str) -> str:
    return " ".join(UNPRINTABLE.sub("", text).split())


def read_line(line: dict[str, Any], number: int) -> Line | None:
    """`line` is a line of pymupdf's "dict" output, which has no type information."""
    spans = [span for span in line["spans"] if span["text"].strip()]
    text = clean("".join(span["text"] for span in line["spans"]))
    if not text or not spans:
        return None
    sizes: Counter[float] = Counter()
    for span in spans:
        sizes[round(span["size"], 1)] += len(span["text"])
    # The dominant size, not the mean: a superscript must not shrink a body line.
    size = sizes.most_common(1)[0][0]
    marks = [
        digits
        for span in spans
        if span["size"] < size - 1 and MARK.fullmatch(span["text"])
        for digits in re.findall(r"\d+", span["text"])
    ]
    return Line(
        page=number,
        bbox=tuple(line["bbox"]),
        text=text,
        size=size,
        bold=all(
            span["flags"] & pymupdf.TEXT_FONT_BOLD or "bold" in span["font"].lower()
            for span in spans
        ),
        marks=tuple(marks),
    )


def read_page(page: pymupdf.Page, number: int) -> list[Line]:
    # pymupdf ships no type information for this call.
    content = page.get_text("dict", flags=TEXT_FLAGS)  # type: ignore[no-untyped-call]
    lines = (read_line(line, number) for b in content["blocks"] for line in b.get("lines", []))
    return [line for line in lines if line is not None]


def drop_contents(lines: list[Line]) -> list[Line]:
    """A contents page has no content of its own, and its entries look like headings."""
    if any(line.text.lower() in CONTENTS_TITLES for line in lines):
        return []
    return [line for line in lines if not DOT_LEADER.search(line.text)]


def in_margin(line: Line, height: float) -> bool:
    return line.bbox[1] < height * MARGIN_SHARE or line.bbox[3] > height * (1 - MARGIN_SHARE)


def margin_key(line: Line) -> str:
    return re.sub(r"\d+", "#", line.text.lower())


def drop_margins(pages: list[list[Line]], heights: list[float]) -> list[list[Line]]:
    """Remove page numbers and the lines that repeat in the margins of many pages."""
    seen: Counter[str] = Counter()
    for lines, height in zip(pages, heights, strict=True):
        seen.update({margin_key(line) for line in lines if in_margin(line, height)})
    needed = max(2, math.ceil(len(pages) * REPEAT_SHARE))

    def is_noise(line: Line, height: float) -> bool:
        if not in_margin(line, height):
            return False
        return seen[margin_key(line)] >= needed or bool(PAGE_NUMBER.fullmatch(line.text))

    return [
        [line for line in lines if not is_noise(line, height)]
        for lines, height in zip(pages, heights, strict=True)
    ]


def body_size(lines: Iterable[Line]) -> float:
    """The size that carries the most characters, which differs from document to document."""
    sizes: Counter[float] = Counter()
    for line in lines:
        sizes[round(line.size, 1)] += len(line.text)
    return sizes.most_common(1)[0][0] if sizes else 0.0


def split_footnotes(lines: list[Line], body: float, height: float) -> tuple[list[Line], list[Line]]:
    """Footnotes are the run of smaller lines at the very bottom of the page."""
    notes: set[int] = set()
    for index in sorted(range(len(lines)), key=lambda i: lines[i].bbox[3], reverse=True):
        line = lines[index]
        if line.size >= body - NOTE_MAX_SIZE_GAP or line.bbox[1] < height / 2:
            break
        notes.add(index)
    return (
        [line for index, line in enumerate(lines) if index not in notes],
        [line for index, line in enumerate(lines) if index in notes],
    )


def continues(previous: Line, line: Line) -> bool:
    """True when `line` is the next line of the same paragraph."""
    same_style = abs(previous.size - line.size) < 0.5 and previous.bold == line.bold
    gap = line.bbox[1] - previous.bbox[3]
    overlaps = line.bbox[0] < previous.bbox[2] and previous.bbox[0] < line.bbox[2]
    return (
        same_style
        and overlaps
        and -0.5 * line.size < gap < 0.5 * line.size
        and (not LIST_ITEM.match(line.text))
    )


def join_lines(left: str, right: str) -> str:
    return f"{left}{right}" if left.endswith("-") else f"{left} {right}"


def extend(head: Line, line: Line) -> Line:
    return Line(
        page=head.page,
        bbox=(
            min(head.bbox[0], line.bbox[0]),
            min(head.bbox[1], line.bbox[1]),
            max(head.bbox[2], line.bbox[2]),
            max(head.bbox[3], line.bbox[3]),
        ),
        text=join_lines(head.text, line.text),
        size=head.size,
        bold=head.bold,
        marks=head.marks + line.marks,
    )


def merge_paragraphs(lines: list[Line]) -> list[Line]:
    """Some PDFs store every line as its own block, so paragraphs are rebuilt from the spacing."""
    merged: list[Line] = []
    previous: Line | None = None
    for line in lines:
        if previous is not None and merged and continues(previous, line):
            merged[-1] = extend(merged[-1], line)
        else:
            merged.append(line)
        previous = line
    return merged


def group_notes(lines: list[Line], marks: set[str]) -> list[tuple[str | None, Line]]:
    """Split the bottom of a page into footnotes, each with its number if the page refers to it.

    Only a number the body refers to starts a note, so a wrapped line that begins with
    "31 CFR" stays in its note.
    """
    notes: list[tuple[str | None, Line]] = []
    previous: Line | None = None
    for line in lines:
        found = NOTE_NUMBER.match(line.text)
        number = found.group(1) if found and found.group(1) in marks else None
        if notes and previous is not None and number is None:
            head_number, head = notes[-1]
            if NOTE_NUMBER_ONLY.fullmatch(head.text) or continues(previous, line):
                notes[-1] = (head_number, extend(head, line))
                previous = line
                continue
        notes.append((number, line))
        previous = line
    return notes


def is_heading(paragraph: Line, body: float, row_mates: int) -> bool:
    """Larger text, or a bold line alone on its row: a bold cell has neighbours in a table."""
    text = paragraph.text
    if len(text) > HEADING_MAX_CHARS or not re.search(r"[A-Za-z]{2}", text):
        return False
    if text.endswith((".", ",", ";")) or LIST_ITEM.match(text):
        return False
    if paragraph.size >= body + HEADING_MIN_GROWTH:
        return True
    return paragraph.bold and paragraph.size >= body - NOTE_MAX_SIZE_GAP and row_mates == 0


def find_headings(paragraphs: list[Line], body: float) -> set[int]:
    found = set()
    for index, paragraph in enumerate(paragraphs):
        mates = sum(
            other is not paragraph
            and other.bbox[1] < paragraph.bbox[3]
            and paragraph.bbox[1] < other.bbox[3]
            for other in paragraphs
        )
        if is_heading(paragraph, body, mates):
            found.add(index)
    return found


def style_of(heading: Line) -> tuple[int, bool]:
    return round(heading.size), heading.bold


def join_body(blocks: list[Block]) -> str:
    """Rejoin a sentence that a page or column break cut in two."""
    text = ""
    for block in blocks:
        if not text:
            text = block.text
        elif text[-1] not in SENTENCE_END and block.text[0].islower():
            text = join_lines(text, block.text)
        else:
            text = f"{text}\n\n{block.text}"
    return text


@dataclass
class Draft:
    path: str
    body: list[Block] = field(default_factory=list)
    notes: list[Block] = field(default_factory=list)


class SectionBuilder:
    """Sections stay open until the end, because a footnote at the bottom of a page belongs to
    the section that refers to it, which may already be behind the current one."""

    def __init__(self, levels: dict[tuple[int, bool], int]) -> None:
        self.levels = levels
        self.stack: list[tuple[int, str]] = []
        self.current = Draft(path="")
        self.drafts = [self.current]
        self.owners: dict[tuple[int, str], Draft] = {}
        self.last_note_owner = self.current
        self.last_note: Block | None = None
        self.note_is_numbered = False  # captions such as "Source: Italy" never continue

    def claim(self, line: Line) -> None:
        for mark in line.marks:
            self.owners[(line.page, mark)] = self.current

    def add_heading(self, line: Line) -> None:
        level = self.levels[style_of(line)]
        while self.stack and self.stack[-1][0] >= level:
            self.stack.pop()
        self.stack.append((level, line.text))
        path = " > ".join(text for _, text in self.stack)
        if self.current.body:
            self.current = Draft(path=path)
            self.drafts.append(self.current)
        else:
            self.current.path = path
        self.claim(line)

    def add_body(self, line: Line) -> None:
        self.current.body.append(Block(line.page, line.bbox, line.text, "body"))
        self.claim(line)

    def continues_note(self, number: str | None, line: Line) -> bool:
        """True for an unnumbered note that opens a page right after an unfinished footnote."""
        last = self.last_note
        if number is not None or last is None or last.page != line.page - 1:
            return False
        if not self.note_is_numbered:
            return False
        return line.text[0].islower() or last.text[-1] not in SENTENCE_END

    def add_note(self, number: str | None, line: Line, opens_page: bool) -> None:
        owner = self.owners.get((line.page, number or ""), self.current)
        continued = opens_page and self.continues_note(number, line)
        if continued:
            owner = self.last_note_owner
        self.note_is_numbered = number is not None or continued
        self.last_note = Block(line.page, line.bbox, line.text, "footnote")
        owner.notes.append(self.last_note)
        self.last_note_owner = owner

    def sections(self) -> tuple[Section, ...]:
        kept: list[Draft] = []
        waiting: list[Block] = []  # notes of a heading with no text go to the next section
        for draft in self.drafts:
            draft.notes = waiting + draft.notes
            if WORD.search(join_body(draft.body)):  # else cells of a numbered list, not content
                kept.append(draft)
                waiting = []
            else:
                waiting = draft.notes
        if kept:
            kept[-1].notes += waiting
        return tuple(build_section(draft, index) for index, draft in enumerate(kept))


def build_section(draft: Draft, ordinal: int) -> Section:
    blocks = draft.body + draft.notes
    return Section(
        path=draft.path,
        text="\n\n".join([join_body(draft.body), *(note.text for note in draft.notes)]),
        page_start=min(block.page for block in blocks),
        page_end=max(block.page for block in blocks),
        ordinal=ordinal,
        blocks=tuple(blocks),
    )


def parse_pdf(path: Path) -> ParsedDocument:
    """Parse one PDF. Page numbers are 1-based; bboxes are PDF points from the top left."""
    with pymupdf.open(path) as document:  # type: ignore[no-untyped-call]
        raw = [read_page(page, number) for number, page in enumerate(document, start=1)]
        heights = [page.rect.height for page in document]

    total_lines = sum(len(lines) for lines in raw)
    single = sum(len(line.text) == 1 for lines in raw for line in lines)
    pages = [drop_contents(lines) for lines in drop_margins(raw, heights)]
    body = body_size(line for lines in pages for line in lines)

    split = [
        split_footnotes(lines, body, height) for lines, height in zip(pages, heights, strict=True)
    ]
    paragraphs = [merge_paragraphs(main) for main, _ in split]
    headings = [find_headings(page, body) for page in paragraphs]
    styles = {
        style_of(page[index])
        for page, found in zip(paragraphs, headings, strict=True)
        for index in found
    }
    levels = {
        style: level for level, style in enumerate(sorted(styles, key=lambda s: (-s[0], not s[1])))
    }

    builder = SectionBuilder(levels)
    for page, found, (_, notes) in zip(paragraphs, headings, split, strict=True):
        for index, paragraph in enumerate(page):
            if index in found:
                builder.add_heading(paragraph)
            else:
                builder.add_body(paragraph)
        marks = {mark for paragraph in page for mark in paragraph.marks}
        for index, (number, note) in enumerate(group_notes(notes, marks)):
            builder.add_note(number, note, opens_page=index == 0)
    return ParsedDocument(
        page_count=len(raw),
        sections=builder.sections(),
        single_char_ratio=single / total_lines if total_lines else 0.0,
    )


def quality_flags(document: ParsedDocument) -> list[str]:
    """Reasons a person should look at this document. Empty means it passed."""
    flags = []
    if document.page_count == 0:
        return ["no_pages"]
    chars = sum(len(section.text) for section in document.sections)
    if chars / document.page_count < MIN_CHARS_PER_PAGE:
        flags.append("low_text_density")
    if document.single_char_ratio > MAX_SINGLE_CHAR_RATIO:
        flags.append("many_single_char_lines")
    if not any(section.path for section in document.sections):
        flags.append("no_headings")
    return flags
