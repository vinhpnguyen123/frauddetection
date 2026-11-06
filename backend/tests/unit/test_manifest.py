"""data/manifest.csv is committed and is the source of truth, so its shape is checked."""

import re
from datetime import date
from urllib.parse import urlsplit

import pytest
from scripts.download import MANIFEST, read_manifest

COLUMNS = [
    "doc_id",
    "title",
    "source",
    "url",
    "landing_url",
    "published_date",
    "collections",
    "authority",
    "status",
    "license",
    "sha256",
    "stage",
    "notes",
]
SOURCES = {"fincen", "ffiec", "occ", "fdic", "fed", "treasury", "ofac", "fatf", "wolfsberg"}
AUTHORITIES = {"regulation", "supervisory_guidance", "advisory", "industry_standard"}
STATUSES = {"active", "rescinded", "superseded"}
LICENSES = {"us_gov_public", "link_only"}

ROWS = read_manifest(MANIFEST)


def test_columns_and_unique_ids() -> None:
    assert list(ROWS[0]) == COLUMNS
    ids = [row["doc_id"] for row in ROWS]
    assert len(ids) == len(set(ids))


@pytest.mark.parametrize("row", ROWS, ids=lambda row: row["doc_id"])
def test_row_is_valid(row: dict[str, str]) -> None:
    assert row["doc_id"].startswith(f"{row['source']}-")
    assert row["title"].strip()
    assert row["source"] in SOURCES
    assert row["authority"] in AUTHORITIES
    assert row["status"] in STATUSES
    assert row["license"] in LICENSES
    assert row["stage"] in {"1", "2", "3"}
    assert row["collections"]
    assert urlsplit(row["url"]).scheme == "https"
    assert urlsplit(row["landing_url"]).scheme == "https"
    if row["published_date"]:
        date.fromisoformat(row["published_date"])
    if row["sha256"]:
        assert re.fullmatch(r"[0-9a-f]{64}", row["sha256"])


@pytest.mark.parametrize("row", ROWS, ids=lambda row: row["doc_id"])
def test_fatf_and_wolfsberg_are_link_only(row: dict[str, str]) -> None:
    assert (row["license"] == "link_only") == (row["source"] in {"fatf", "wolfsberg"})
