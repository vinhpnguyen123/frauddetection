"""Render synthetic/<tenant>/<policy>.md to PDF, so policies go through the same parser as the
public corpus. See docs/DATASET.md §6.

The output is byte-stable: the same text always gives the same PDF, because ingestion is
idempotent on the content hash. Nothing here may add a timestamp.
"""

import io
from pathlib import Path

import markdown
import pymupdf

ROOT = Path(__file__).resolve().parents[1]
SOURCE_DIR = ROOT / "synthetic"
OUTPUT_DIR = ROOT / "data" / "raw" / "synthetic"

PAGE = pymupdf.paper_rect("letter")
BODY = PAGE + (54, 54, -54, -54)
CSS = "body { font-family: sans-serif; font-size: 11pt; } th, td { padding: 3pt; }"


def render_pdf(text: str) -> bytes:
    story = pymupdf.Story(html=markdown.markdown(text, extensions=["tables"]), user_css=CSS)
    buffer = io.BytesIO()
    writer = pymupdf.DocumentWriter(buffer)
    more = True
    while more:
        device = writer.begin_page(PAGE)
        more, _ = story.place(BODY)
        story.draw(device)
        writer.end_page()
    writer.close()
    return buffer.getvalue()


def main() -> None:
    sources = sorted(SOURCE_DIR.glob("*/*.md"))
    for source in sources:
        target = OUTPUT_DIR / source.parent.name / f"{source.stem}.pdf"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(render_pdf(source.read_text(encoding="utf-8")))
    print(f"rendered {len(sources)} policies into {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
