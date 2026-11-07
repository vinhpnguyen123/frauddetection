"""Write data/parse_report.csv: parse quality per document (docs/DATASET.md §5).

The expected documents come from the manifest and synthetic/, not from what is on disk, so a
deleted PDF shows up as missing instead of silently leaving the report.
"""

import csv
import sys
from pathlib import Path

import pymupdf
from scripts.download import MANIFEST, RAW_DIR, read_manifest, target_path
from scripts.render_synthetic import OUTPUT_DIR, SOURCE_DIR

from app.ingestion.parse import parse_pdf, quality_flags

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "data" / "parse_report.csv"
STAGE = 1
COLUMNS = ["doc", "pages", "chars_per_page", "sections", "footnote_share", "single_char", "flags"]


def expected_pdfs(raw_dir: Path) -> list[Path]:
    public = [
        target_path(row, raw_dir) for row in read_manifest(MANIFEST) if int(row["stage"]) <= STAGE
    ]
    synthetic = raw_dir / OUTPUT_DIR.relative_to(RAW_DIR)
    policies = [
        synthetic / source.parent.name / f"{source.stem}.pdf"
        for source in SOURCE_DIR.glob("*/*.md")
    ]
    return sorted(public + policies)


def report_row(path: Path, raw_dir: Path) -> dict[str, object]:
    doc = path.relative_to(raw_dir).with_suffix("").as_posix()
    if not path.exists():
        return {"doc": doc, "flags": "missing"}
    try:
        parsed = parse_pdf(path)
    except (pymupdf.FileDataError, pymupdf.EmptyFileError):
        return {"doc": doc, "flags": "unreadable"}
    blocks = [block for section in parsed.sections for block in section.blocks]
    chars = sum(len(block.text) for block in blocks)
    notes = sum(len(block.text) for block in blocks if block.kind == "footnote")
    return {
        "doc": doc,
        "pages": parsed.page_count,
        "chars_per_page": round(chars / parsed.page_count) if parsed.page_count else 0,
        "sections": len(parsed.sections),
        "footnote_share": round(notes / chars, 2) if chars else 0,
        "single_char": round(parsed.single_char_ratio, 3),
        "flags": ";".join(quality_flags(parsed)),
    }


def main() -> int:
    rows = [report_row(path, RAW_DIR) for path in expected_pdfs(RAW_DIR)]
    with REPORT.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    flagged = [row for row in rows if row["flags"]]
    for row in flagged:
        print(f"FLAGGED {row['doc']}: {row['flags']}")
    print(f"{len(rows)} documents, {len(flagged)} flagged, report in {REPORT}")
    absent = any(row["flags"] in {"missing", "unreadable"} for row in rows)
    return 1 if absent else 0


if __name__ == "__main__":
    sys.exit(main())
