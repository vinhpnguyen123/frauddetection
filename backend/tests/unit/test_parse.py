"""The parser, on small PDFs built here: data/raw does not exist in CI."""

from collections.abc import Iterable
from pathlib import Path

import pymupdf
import pytest
from scripts.download import MANIFEST, read_manifest
from scripts.parse_report import expected_pdfs, report_row
from scripts.render_synthetic import SOURCE_DIR, render_pdf

from app.ingestion.parse import (
    ParsedDocument,
    Section,
    clean,
    parse_pdf,
    quality_flags,
    read_page,
)

Text = tuple[float, float, str, float, str]  # x, y, text, size, font
BODY = "This is an ordinary sentence of body text that runs across the line."


def body(y: float, x: float = 72, text: str = BODY) -> Text:
    return (x, y, text, 11, "helv")


def heading(y: float, text: str, size: float = 16) -> Text:
    return (72, y, text, size, "hebo")


def build(path: Path, pages: Iterable[Iterable[Text]]) -> Path:
    with pymupdf.open() as document:
        for items in pages:
            page = document.new_page(width=612, height=792)
            for x, y, text, size, font in items:
                page.insert_text((x, y), text, fontsize=size, fontname=font)
        document.save(path)
    return path


def parse(tmp_path: Path, *pages: Iterable[Text]) -> ParsedDocument:
    return parse_pdf(build(tmp_path / "doc.pdf", pages))


def all_text(document: ParsedDocument) -> str:
    return "\n".join(section.text for section in document.sections)


def by_path(document: ParsedDocument, path: str) -> Section:
    return next(section for section in document.sections if section.path == path)


def test_running_headers_and_page_numbers_are_removed(tmp_path: Path) -> None:
    pages = [
        [
            (72, 40, f"FinCEN Alert {2020 + number}", 10, "helv"),
            body(200),
            body(240, text=f"Unique text on page {number}."),
            (300, 760, str(number), 10, "helv"),
        ]
        for number in range(1, 5)
    ]
    text = all_text(parse(tmp_path, *pages))
    assert "FinCEN Alert" not in text
    assert "Unique text on page 3." in text
    assert "\n3\n" not in f"\n{text}\n"


def test_a_line_outside_the_margins_is_kept_even_if_repeated(tmp_path: Path) -> None:
    pages = [[body(200, text="Same sentence on each page."), body(240)] for _ in range(4)]
    assert all_text(parse(tmp_path, *pages)).count("Same sentence") == 4


def test_headings_build_a_nested_path(tmp_path: Path) -> None:
    parsed = parse(
        tmp_path,
        [
            heading(100, "Overview", 18),
            body(130),
            heading(170, "Filing", 14),
            body(200),
            heading(240, "Deadlines", 11),
            body(270),
            heading(310, "Records", 14),
            body(340),
        ],
    )
    assert [section.path for section in parsed.sections] == [
        "Overview",
        "Overview > Filing",
        "Overview > Filing > Deadlines",
        "Overview > Records",
    ]
    assert [section.ordinal for section in parsed.sections] == [0, 1, 2, 3]


def test_a_bold_table_row_is_not_a_heading(tmp_path: Path) -> None:
    parsed = parse(
        tmp_path,
        [
            heading(100, "Limits"),
            (72, 150, "Rating", 11, "hebo"),
            (300, 150, "Review cycle", 11, "hebo"),
            body(200),
            body(216),
        ],
    )
    assert [section.path for section in parsed.sections] == ["Limits"]
    assert "Review cycle" in all_text(parsed)


def test_a_sentence_is_not_a_heading(tmp_path: Path) -> None:
    parsed = parse(
        tmp_path, [heading(100, "Scope"), body(150), (72, 190, "Bold text.", 11, "hebo")]
    )
    assert [section.path for section in parsed.sections] == ["Scope"]


def test_two_columns_are_read_in_stored_order(tmp_path: Path) -> None:
    left = [body(120 + 16 * i, text=f"Left column line {i} of the text") for i in range(4)]
    right = [body(120 + 16 * i, 320, f"Right column line {i} of the text") for i in range(4)]
    text = all_text(parse(tmp_path, left + right))
    assert text.index("Left column line 3") < text.index("Right column line 0")


def test_lines_are_merged_into_paragraphs(tmp_path: Path) -> None:
    parsed = parse(tmp_path, [body(100, text="first half of"), body(113, text="the paragraph.")])
    assert parsed.sections[0].text == "first half of the paragraph."
    (block,) = parsed.sections[0].blocks
    assert block.bbox[1] < 100 < block.bbox[3] or block.bbox[3] > 113


def test_list_items_stay_separate(tmp_path: Path) -> None:
    parsed = parse(tmp_path, [body(100, text="- First item"), body(113, text="- Second item")])
    assert parsed.sections[0].text == "- First item\n\n- Second item"


def test_footnotes_go_after_the_body_and_do_not_cut_a_sentence(tmp_path: Path) -> None:
    filler = [body(100 + 16 * i) for i in range(6)]
    parsed = parse(
        tmp_path,
        [
            *filler,
            body(650, text="This sentence is cut by the"),
            (72, 690, "1 See 31 CFR 1020.320", 9, "helv"),
        ],
        [body(100, text="end of the page."), *filler[1:]],
    )
    (section,) = parsed.sections
    assert "cut by the end of the page." in section.text
    assert section.text.endswith("1 See 31 CFR 1020.320")
    assert section.blocks[-1].kind == "footnote"
    assert (section.page_start, section.page_end) == (1, 2)


def test_a_superscript_does_not_change_the_size_of_its_line(tmp_path: Path) -> None:
    """Regression: a mean size split the body into many sizes, and footnotes won as the body."""
    text = "A body line that ends with a note mark"
    with pymupdf.open() as document:
        page = document.new_page(width=612, height=792)
        page.insert_text((72, 100), text, fontsize=12)
        page.insert_text((72 + pymupdf.get_text_length(text, fontsize=12), 97), "1", fontsize=7)
        (line,) = read_page(page, 1)
    assert line.text == f"{text}1"
    assert line.size == 12


def write_marked(page: pymupdf.Page, y: float, text: str, mark: str) -> None:
    page.insert_text((72, y), text, fontsize=11)
    x = 72 + pymupdf.get_text_length(text, fontsize=11)
    page.insert_text((x, y - 3), mark, fontsize=7)


def write_section(page: pymupdf.Page, y: float, title: str, text: str, mark: str = "") -> None:
    page.insert_text((72, y), title, fontsize=16, fontname="hebo")
    write_marked(page, y + 30, text, mark)
    for index in range(3):
        page.insert_text((72, y + 46 + 16 * index), BODY, fontsize=11)


def notes_of(parsed: ParsedDocument, path: str) -> list[str]:
    return [b.text for b in by_path(parsed, path).blocks if b.kind == "footnote"]


def test_footnote_stays_with_the_section_that_refers_to_it(tmp_path: Path) -> None:
    """Regression: an exception in a footnote landed in the last section of the page."""
    path = tmp_path / "doc.pdf"
    with pymupdf.open() as document:
        page = document.new_page(width=612, height=792)
        write_section(page, 100, "Deadlines", "File the report in thirty days", "1")
        write_section(page, 300, "Retention", "Keep the records for five years", "2")
        page.insert_text((72, 660), "1 Except when no suspect is known.", fontsize=9)
        page.insert_text((72, 672), "2 Counted from the filing date.", fontsize=9)
        document.save(path)
    parsed = parse_pdf(path)
    assert notes_of(parsed, "Deadlines") == ["1 Except when no suspect is known."]
    assert notes_of(parsed, "Retention") == ["2 Counted from the filing date."]


def test_blocks_keep_note_references_and_numbers(tmp_path: Path) -> None:
    path = tmp_path / "doc.pdf"
    with pymupdf.open() as document:
        page = document.new_page(width=612, height=792)
        write_section(page, 100, "Deadlines", "File the report in thirty days", "1")
        page.insert_text((72, 660), "1 Except when no suspect is known.", fontsize=9)
        document.save(path)
    blocks = by_path(parse_pdf(path), "Deadlines").blocks
    assert blocks[0].marks == ("1",)
    assert blocks[-1].note_key == (1, "1")


def test_a_wrapped_footnote_line_starting_with_a_number_is_not_a_new_note(tmp_path: Path) -> None:
    path = tmp_path / "doc.pdf"
    with pymupdf.open() as document:
        page = document.new_page(width=612, height=792)
        write_section(page, 100, "Deadlines", "File the report in thirty days", "1")
        page.insert_text((72, 660), "1 See the rule at", fontsize=9)
        page.insert_text((72, 671), "31 CFR 1020.320.", fontsize=9)
        document.save(path)
    assert notes_of(parse_pdf(path), "Deadlines") == ["1 See the rule at 31 CFR 1020.320."]


def test_a_footnote_number_on_its_own_line_joins_its_text(tmp_path: Path) -> None:
    path = tmp_path / "doc.pdf"
    with pymupdf.open() as document:
        page = document.new_page(width=612, height=792)
        write_section(page, 100, "Deadlines", "File the report in thirty days", "4")
        write_section(page, 300, "Retention", "Keep the records for five years")
        page.insert_text((54, 660), "4.", fontsize=9)
        page.insert_text((72, 660), "See the rule.", fontsize=9)
        document.save(path)
    assert notes_of(parse_pdf(path), "Deadlines") == ["4. See the rule."]


def test_a_footnote_continued_on_the_next_page_keeps_its_section(tmp_path: Path) -> None:
    path = tmp_path / "doc.pdf"
    with pymupdf.open() as document:
        first = document.new_page(width=612, height=792)
        write_section(first, 100, "Deadlines", "File the report in thirty days", "1")
        first.insert_text((72, 672), "1 This note starts here", fontsize=9)
        second = document.new_page(width=612, height=792)
        write_section(second, 100, "Retention", "Keep the records for five years")
        second.insert_text((72, 672), "and ends on the next page.", fontsize=9)
        document.save(path)
    parsed = parse_pdf(path)
    assert len(notes_of(parsed, "Deadlines")) == 2
    assert notes_of(parsed, "Retention") == []
    notes = [b for b in by_path(parsed, "Deadlines").blocks if b.kind == "footnote"]
    assert [note.note_key for note in notes] == [(1, "1"), (1, "1")]


def two_pages_of_notes(path: Path, first_note: str, second_note: str) -> ParsedDocument:
    with pymupdf.open() as document:
        first = document.new_page(width=612, height=792)
        write_section(first, 100, "Deadlines", "File the report in thirty days", "1")
        first.insert_text((72, 672), first_note, fontsize=9)
        second = document.new_page(width=612, height=792)
        write_section(second, 100, "Retention", "Keep the records for five years")
        second.insert_text((72, 672), second_note, fontsize=9)
        document.save(path)
    return parse_pdf(path)


def test_an_unfinished_footnote_continues_even_with_an_uppercase_word(tmp_path: Path) -> None:
    """Regression: the rest of an exception landed in the next section."""
    parsed = two_pages_of_notes(
        tmp_path / "doc.pdf",
        "1 This exception applies to",
        "SAR filings with no known suspect.",
    )
    assert notes_of(parsed, "Deadlines") == [
        "1 This exception applies to",
        "SAR filings with no known suspect.",
    ]
    assert notes_of(parsed, "Retention") == []


def test_a_finished_footnote_does_not_capture_the_next_page(tmp_path: Path) -> None:
    parsed = two_pages_of_notes(
        tmp_path / "doc.pdf", "1 This note is complete.", "Source: agency data."
    )
    assert notes_of(parsed, "Deadlines") == ["1 This note is complete."]
    assert notes_of(parsed, "Retention") == ["Source: agency data."]


def test_an_unnumbered_caption_does_not_capture_the_next_page(tmp_path: Path) -> None:
    """Regression: "Source: Luxembourg" has no full stop, but it is not an unfinished footnote."""
    parsed = two_pages_of_notes(tmp_path / "doc.pdf", "Source: Luxembourg", "Source: Belgium")
    assert notes_of(parsed, "Deadlines") == ["Source: Luxembourg"]
    assert notes_of(parsed, "Retention") == ["Source: Belgium"]


def test_a_note_without_a_reference_stays_in_the_section_at_the_page_end(tmp_path: Path) -> None:
    path = tmp_path / "doc.pdf"
    with pymupdf.open() as document:
        page = document.new_page(width=612, height=792)
        write_section(page, 100, "Deadlines", "File the report in thirty days")
        page.insert_text((72, 672), "Source: agency data.", fontsize=9)
        document.save(path)
    assert notes_of(parse_pdf(path), "Deadlines") == ["Source: agency data."]


def test_contents_pages_are_dropped(tmp_path: Path) -> None:
    parsed = parse(
        tmp_path,
        [heading(100, "Contents"), body(150, text="Overview"), body(170, text="Filing")],
        [heading(100, "Overview"), body(150)],
    )
    assert [section.path for section in parsed.sections] == ["Overview"]
    assert [section.page_start for section in parsed.sections] == [2]


def test_dot_leaders_are_dropped(tmp_path: Path) -> None:
    text = all_text(parse(tmp_path, [body(100, text="Filing ........... 12"), body(150)]))
    assert "....." not in text


def test_sections_without_words_are_dropped(tmp_path: Path) -> None:
    parsed = parse(
        tmp_path,
        [heading(100, "Numbers"), body(150, text="12"), heading(200, "Words"), body(250)],
    )
    assert [section.path for section in parsed.sections] == ["Words"]


def test_clean_removes_control_and_icon_characters() -> None:
    assert clean("\x07Policy\xad  renewals") == "Policy renewals"


def test_blocks_carry_page_and_bbox(tmp_path: Path) -> None:
    parsed = parse(tmp_path, [body(100)], [body(100)])
    blocks = [block for section in parsed.sections for block in section.blocks]
    assert {block.page for block in blocks} == {1, 2}
    for block in blocks:
        x0, y0, x1, y1 = block.bbox
        assert 0 <= x0 < x1 <= 612 and 0 <= y0 < y1 <= 792


@pytest.mark.parametrize("path", sorted(SOURCE_DIR.glob("*/*.md")), ids=lambda path: path.stem)
def test_synthetic_policies_keep_their_canary(path: Path, tmp_path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    canary = next(word for word in text.split() if "-CANARY-" in word)
    target = tmp_path / "policy.pdf"
    target.write_bytes(render_pdf(text))
    parsed = parse_pdf(target)
    assert canary in all_text(parsed)
    assert quality_flags(parsed) == []


def test_clean_document_has_no_flags(tmp_path: Path) -> None:
    lines = [body(100 + 16 * i) for i in range(12)]
    assert quality_flags(parse(tmp_path, [heading(70, "Scope"), *lines])) == []


def test_sparse_document_is_flagged(tmp_path: Path) -> None:
    flags = quality_flags(parse(tmp_path, [(72, 100, "Hi there.", 11, "helv")]))
    assert flags == ["low_text_density", "no_headings"]


def test_single_character_lines_are_flagged(tmp_path: Path) -> None:
    letters = [(72, 100 + 14 * i, "x", 11, "helv") for i in range(30)]
    assert "many_single_char_lines" in quality_flags(parse(tmp_path, letters))


def test_empty_document_is_flagged() -> None:
    assert quality_flags(ParsedDocument(0, (), 0.0)) == ["no_pages"]


def test_report_flags_an_unreadable_file(tmp_path: Path) -> None:
    broken = tmp_path / "broken.pdf"
    broken.write_bytes(b"not a pdf")
    assert report_row(broken, tmp_path) == {"doc": "broken", "flags": "unreadable"}


def test_report_flags_a_missing_file(tmp_path: Path) -> None:
    assert report_row(tmp_path / "fincen" / "gone.pdf", tmp_path) == {
        "doc": "fincen/gone",
        "flags": "missing",
    }


def test_report_covers_every_manifest_document_and_policy(tmp_path: Path) -> None:
    expected = expected_pdfs(tmp_path)
    manifest = [row for row in read_manifest(MANIFEST) if int(row["stage"]) == 1]
    policies = list(SOURCE_DIR.glob("*/*.md"))
    assert len(expected) == len(set(expected)) == len(manifest) + len(policies)
    assert tmp_path / "fincen" / "fincen-FIN-2022-A002.pdf" in expected
    assert tmp_path / "synthetic" / "bluefin" / "cdd-edd-procedure.pdf" in expected
