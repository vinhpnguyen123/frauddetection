"""chunk_v1 with a fake tokenizer: one token per word, so sizes are easy to read."""

from app.ingestion.chunk import (
    MAX_TOKENS,
    OVERLAP_TOKENS,
    TARGET_TOKENS,
    Chunk,
    ChunkConfig,
    Span,
    chunk_document,
    halve,
)
from app.ingestion.parse import Block, ParsedDocument, Section

BOX = (72.0, 100.0, 500.0, 120.0)


async def count_words(texts: list[str]) -> list[int]:
    return [len(text.split()) for text in texts]


def sentence(words: int, tag: str = "w") -> str:
    return " ".join([tag] * (words - 1) + [f"{tag}."])


def body(text: str, page: int = 1, marks: tuple[str, ...] = ()) -> Block:
    return Block(page, BOX, text, "body", marks=marks)


def note(text: str, number: str | None = None, page: int = 1, origin: int = 1) -> Block:
    return Block(page, BOX, text, "footnote", note_key=(origin, number) if number else None)


def section(*blocks: Block, path: str = "A", ordinal: int = 0) -> Section:
    pages = [block.page for block in blocks]
    return Section(path, "", min(pages), max(pages), ordinal, blocks)


async def chunks_of(*sections: Section) -> list[Chunk]:
    return await chunk_document(ParsedDocument(1, sections, 0.0), count_words)


async def test_a_short_section_is_one_chunk() -> None:
    (chunk,) = await chunks_of(section(body("A short rule.")))
    assert chunk.text == "A short rule."
    assert (chunk.token_count, chunk.section_path, chunk.ordinal) == (3, "A", 0)


async def test_chunks_never_cross_a_section() -> None:
    first = section(body("First section text."), path="A", ordinal=0)
    second = section(body("Second section text."), path="B", ordinal=1)
    chunks = await chunks_of(first, second)
    assert [(c.ordinal, c.section_ordinal, c.section_path) for c in chunks] == [
        (0, 0, "A"),
        (1, 1, "B"),
    ]


async def test_a_long_section_splits_near_the_target() -> None:
    blocks = [body(sentence(100, f"s{index}")) for index in range(12)]
    chunks = await chunks_of(section(*blocks))
    assert len(chunks) > 1
    assert all(chunk.token_count <= MAX_TOKENS for chunk in chunks)
    assert all(chunk.token_count >= TARGET_TOKENS for chunk in chunks[:-1])


async def test_overlap_repeats_the_last_whole_sentences() -> None:
    sentences = [sentence(20, f"S{index}") for index in range(60)]
    chunks = await chunks_of(section(body(" ".join(sentences))))
    assert len(chunks) > 1
    for left, right in zip(chunks, chunks[1:], strict=False):
        last_seen = max(index for index, s in enumerate(sentences) if s in left.text)
        first_new = sentences[last_seen + 1]
        repeated = right.text[: right.text.index(first_new)].split()
        assert 0 < len(repeated) <= OVERLAP_TOKENS
        assert left.text.endswith(" ".join(repeated))


async def test_no_text_is_lost() -> None:
    sentences = [sentence(30, f"S{index}") for index in range(50)]
    chunks = await chunks_of(section(body(" ".join(sentences))))
    assert all(any(s in chunk.text for chunk in chunks) for s in sentences)


async def test_a_sentence_over_the_limit_is_split_and_kept() -> None:
    words = [f"w{index}" for index in range(1500)]
    chunks = await chunks_of(section(body(" ".join(words))))
    assert all(chunk.token_count <= MAX_TOKENS for chunk in chunks)
    joined = " ".join(chunk.text for chunk in chunks).split()
    assert set(joined) == set(words)


def test_halve_splits_text_without_spaces() -> None:
    assert halve("abcdef") == ("abc", "def")


async def test_spans_list_each_contributing_block_once() -> None:
    left = Block(3, BOX, "One sentence here. Another sentence here.", "body")
    right = Block(4, (72.0, 200.0, 500.0, 220.0), "Next page text.", "body")
    (chunk,) = await chunks_of(section(left, right))
    assert chunk.spans == (Span(3, left.bbox), Span(4, right.bbox))


async def test_a_sentence_cut_by_a_page_is_rejoined() -> None:
    (chunk,) = await chunks_of(section(body("This rule applies to", 1), body("every bank.", 2)))
    assert chunk.text == "This rule applies to every bank."


async def test_a_footnote_follows_the_paragraph_that_refers_to_it() -> None:
    (chunk,) = await chunks_of(
        section(
            body("File in thirty days1", marks=("1",)),
            body("Keep records."),
            note("1 Except when no suspect is known.", "1"),
        )
    )
    assert chunk.text.index("Except") < chunk.text.index("Keep")


async def test_a_footnote_stays_in_the_chunk_of_its_rule() -> None:
    """Regression guard: the footnote must not fall into the last chunk of a long section."""
    filler = [body(sentence(100, f"f{index}")) for index in range(3)]
    rule = body(sentence(205, "rule") + "1", marks=("1",))  # the rule ends past the target
    tail = [body(sentence(100, f"t{index}")) for index in range(8)]
    chunks = await chunks_of(section(*filler, rule, *tail, note(sentence(60, "exception"), "1")))
    assert len(chunks) > 2
    holder = next(chunk for chunk in chunks if "exception" in chunk.text)
    assert "rule" in holder.text


async def test_a_rule_moves_to_the_next_chunk_to_keep_its_footnote() -> None:
    """Regression: 300 + 400 filled a chunk, and the 60-token exception was left on its own."""
    chunks = await chunks_of(
        section(
            body(sentence(300, "Filler")),
            body(sentence(400, "Rule") + "1", marks=("1",)),
            note(sentence(60, "Exception"), "1"),
        )
    )
    holder = next(chunk for chunk in chunks if "Exception" in chunk.text)
    assert "Rule" in holder.text
    assert all(chunk.token_count <= MAX_TOKENS for chunk in chunks)


async def test_a_rule_and_footnote_too_big_for_one_chunk_are_split_safely() -> None:
    sentences = " ".join(sentence(100, f"Rule{index}") for index in range(7))
    chunks = await chunks_of(
        section(body(sentences + "1", marks=("1",)), note(sentence(100, "Exception"), "1"))
    )
    assert len(chunks) > 1
    assert all(chunk.token_count <= MAX_TOKENS for chunk in chunks)
    assert any("Exception" in chunk.text for chunk in chunks)


async def test_a_footnote_waits_for_the_end_of_its_sentence() -> None:
    """Regression: the note landed inside 'the provision of ML services'."""
    (chunk,) = await chunks_of(
        section(
            body("Networks focus on the provision1", marks=("1",)),
            body("of ML services."),
            note("1 See the report.", "1"),
        )
    )
    assert chunk.text == "Networks focus on the provision1 of ML services.\n\n1 See the report."


async def test_a_paragraph_across_pages_keeps_its_footnote_and_spans() -> None:
    first = body("This rule applies to1", 1, marks=("1",))
    second = Block(2, (72.0, 300.0, 500.0, 320.0), "every bank.", "body")
    (chunk,) = await chunks_of(section(first, second, note("1 Except credit unions.", "1")))
    assert chunk.text == "This rule applies to1 every bank.\n\n1 Except credit unions."
    assert Span(2, second.bbox) in chunk.spans


async def test_a_cut_paragraph_moves_whole_to_keep_its_footnote() -> None:
    chunks = await chunks_of(
        section(
            body(sentence(300, "Filler")),
            body(" ".join(["Rule"] * 300) + "1", marks=("1",)),
            body(" ".join(["rest"] * 100) + "."),
            note(sentence(60, "Exception"), "1"),
        )
    )
    holder = next(chunk for chunk in chunks if "Exception" in chunk.text)
    assert "Rule Rule" in holder.text
    assert "rest rest" in holder.text


async def test_note_numbers_that_restart_on_a_page_are_not_confused() -> None:
    """Regression: the first reference to "1" took the footnotes of both pages."""
    (chunk,) = await chunks_of(
        section(
            body("Rule A1", 1, marks=("1",)),
            body("Rule B1", 2, marks=("1",)),
            note("1 Exception A.", "1", page=1, origin=1),
            note("1 Exception B.", "1", page=2, origin=2),
        )
    )
    assert chunk.text.split("\n\n") == ["Rule A1", "1 Exception A.", "Rule B1", "1 Exception B."]


async def test_restarted_note_numbers_stay_with_their_rule_across_chunks() -> None:
    first = body(sentence(520, "Alpha") + "1", 1, marks=("1",))
    second = body(sentence(520, "Beta") + "1", 2, marks=("1",))
    chunks = await chunks_of(
        section(
            first,
            second,
            note("1 Exception alpha.", "1", page=1, origin=1),
            note("1 Exception beta.", "1", page=2, origin=2),
        )
    )
    alpha = next(chunk for chunk in chunks if "Exception alpha" in chunk.text)
    beta = next(chunk for chunk in chunks if "Exception beta" in chunk.text)
    assert alpha is not beta
    assert "Alpha Alpha" in alpha.text
    assert "Beta Beta" in beta.text


async def test_an_unreferenced_footnote_goes_last() -> None:
    (chunk,) = await chunks_of(section(body("Body text."), note("Source: agency data.")))
    assert chunk.text == "Body text.\n\nSource: agency data."


async def test_a_footnote_with_its_continuation_stays_together() -> None:
    (chunk,) = await chunks_of(
        section(
            body("Rule one1", marks=("1",)),
            body("Later text."),
            note("1 Applies to", "1"),
            note("SAR filings.", "1", page=2, origin=1),
        )
    )
    assert chunk.text.index("SAR filings") < chunk.text.index("Later text")


async def test_same_text_gives_the_same_hash() -> None:
    first = await chunks_of(section(body("A  rule.")))
    second = await chunks_of(section(body("A rule.")))
    assert first[0].content_hash == second[0].content_hash


async def test_empty_document_has_no_chunks() -> None:
    assert await chunks_of() == []


async def chunks_with(config: ChunkConfig, *blocks: Block) -> list[Chunk]:
    document = ParsedDocument(1, (section(*blocks),), 0.0)
    return await chunk_document(document, count_words, config)


async def test_a_smaller_config_keeps_its_own_limits() -> None:
    config = ChunkConfig(target=30, max=45, overlap=5)
    chunks = await chunks_with(config, *[body(sentence(10, f"s{i}")) for i in range(12)])
    assert len(chunks) > 1
    assert all(chunk.token_count <= config.max for chunk in chunks)
    assert all(chunk.token_count >= config.target for chunk in chunks[:-1])


async def test_per_paragraph_gives_each_paragraph_its_own_chunk() -> None:
    config = ChunkConfig(overlap=0, per_paragraph=True)
    chunks = await chunks_with(config, body(sentence(5, "a")), body(sentence(6, "b")))
    assert [chunk.token_count for chunk in chunks] == [5, 6]


async def test_per_paragraph_keeps_a_footnote_with_its_paragraph() -> None:
    config = ChunkConfig(overlap=0, per_paragraph=True)
    chunks = await chunks_with(
        config, body(sentence(5, "a"), marks=("1",)), body(sentence(6, "b")), note("Note.", "1")
    )
    assert "Note." in chunks[0].text
    assert "Note." not in chunks[1].text


async def test_per_paragraph_still_splits_a_paragraph_over_the_limit() -> None:
    config = ChunkConfig(target=10, max=15, overlap=0, per_paragraph=True)
    text = " ".join(sentence(6, f"s{i}") for i in range(6))
    chunks = await chunks_with(config, body(text))
    assert len(chunks) > 1
    assert all(chunk.token_count <= config.max for chunk in chunks)
