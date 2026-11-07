"""Download the corpus listed in data/manifest.csv, politely. See docs/DATASET.md §4.

Hosts that refuse automated access are never worked around: their documents are reported as
blocked, to be saved by hand into data/raw/. The next run records the hash of such a file.
"""

import argparse
import csv
import hashlib
import os
import sys
import tempfile
import time
from collections.abc import Callable
from pathlib import Path
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser

import httpx

from app.config import get_settings

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "data" / "manifest.csv"
RAW_DIR = ROOT / "data" / "raw"

MIN_DELAY_SECONDS = 2.0
MAX_ATTEMPTS = 3
MAX_REDIRECTS = 5
RETRYABLE_STATUS = {429, 500, 502, 503, 504}

Row = dict[str, str]


class Blocked(Exception):
    """The host or its robots.txt refuses automated access."""


class NotPdf(Exception):
    """The response is not a PDF."""


def read_manifest(path: Path) -> list[Row]:
    with path.open(newline="", encoding="utf-8") as file:
        return list(csv.DictReader(file))


def write_manifest(path: Path, rows: list[Row]) -> None:
    """Replace the manifest atomically: a failed write leaves the previous one untouched.

    The temp file is unique per write. Overlapping runs cannot corrupt the file, but the last one
    wins, so hashes from the other run can be lost: run one download at a time.
    """
    with tempfile.NamedTemporaryFile(
        "w", dir=path.parent, suffix=".tmp", delete=False, newline="", encoding="utf-8"
    ) as file:
        temp = Path(file.name)
        try:
            writer = csv.DictWriter(file, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
            file.flush()
            os.fsync(file.fileno())
            temp.chmod(0o644)  # mkstemp creates 0600
            os.replace(temp, path)
        finally:
            temp.unlink(missing_ok=True)


def target_path(row: Row, raw_dir: Path) -> Path:
    return raw_dir / row["source"] / f"{row['doc_id']}.pdf"


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def redirect_target(response: httpx.Response) -> str:
    return str(response.url.join(response.headers["location"]))


class Fetcher:
    """One request at a time, at least MIN_DELAY_SECONDS apart per host, honouring robots.txt."""

    def __init__(
        self,
        client: httpx.Client,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.client = client
        self.sleep = sleep
        self.clock = clock
        self.last_request: dict[str, float] = {}
        self.robots: dict[str, RobotFileParser | None] = {}
        self.refused: dict[str, str] = {}  # host -> reason, so a refusing host is asked once

    def _get(self, url: str) -> httpx.Response:
        host = urlsplit(url).netloc
        if host in self.last_request:
            wait = self.last_request[host] + MIN_DELAY_SECONDS - self.clock()
            if wait > 0:
                self.sleep(wait)
        try:
            return self.client.get(url)
        finally:
            self.last_request[host] = self.clock()

    def _get_robots_txt(self, url: str) -> httpx.Response:
        for _ in range(MAX_REDIRECTS + 1):
            response = self._get(url)
            if not response.has_redirect_location:
                return response
            url = redirect_target(response)
        raise httpx.TooManyRedirects(f"too many redirects for {url}")

    def _robots_for(self, url: str) -> RobotFileParser | None:
        """Return the parsed rules, or None when the site has no robots.txt."""
        parts = urlsplit(url)
        if parts.netloc in self.refused:
            raise Blocked(self.refused[parts.netloc])
        if parts.netloc not in self.robots:
            response = self._get_robots_txt(f"{parts.scheme}://{parts.netloc}/robots.txt")
            if response.status_code == 404:
                self.robots[parts.netloc] = None
            elif response.status_code != 200:
                self.refused[parts.netloc] = f"robots.txt returned {response.status_code}"
                raise Blocked(self.refused[parts.netloc])
            else:
                parser = RobotFileParser()
                parser.parse(response.text.splitlines())
                self.robots[parts.netloc] = parser
        return self.robots[parts.netloc]

    def _get_allowed(self, url: str) -> httpx.Response:
        """One hop: robots.txt of this URL is checked first, and a redirect is returned as is."""
        rules = self._robots_for(url)
        agent = str(self.client.headers["user-agent"])
        if rules is not None and not rules.can_fetch(agent, url):
            raise Blocked("disallowed by robots.txt")

        for attempt in range(1, MAX_ATTEMPTS + 1):
            try:
                response = self._get(url)
            except httpx.TransportError:
                if attempt == MAX_ATTEMPTS:
                    raise
                self.sleep(2.0**attempt)
                continue
            if response.status_code in RETRYABLE_STATUS and attempt < MAX_ATTEMPTS:
                self.sleep(2.0**attempt)
                continue
            if response.status_code in {401, 403}:
                raise Blocked(f"HTTP {response.status_code}")
            if not response.has_redirect_location:
                response.raise_for_status()
            return response
        raise AssertionError("unreachable: the last attempt returns or raises")

    def fetch_pdf(self, url: str) -> bytes:
        """Return the PDF bytes. Raises Blocked, NotPdf or httpx.HTTPError.

        Redirects are followed here, not by the client, so that every hop gets its own robots
        check and per-host delay.
        """
        for _ in range(MAX_REDIRECTS + 1):
            response = self._get_allowed(url)
            if response.has_redirect_location:
                url = redirect_target(response)
                continue
            content_type = response.headers.get("content-type", "")
            if "pdf" not in content_type.lower() or not response.content.startswith(b"%PDF-"):
                raise NotPdf(content_type or "no content type")
            return response.content
        raise httpx.TooManyRedirects(f"too many redirects for {url}")


def download_row(row: Row, fetcher: Fetcher, raw_dir: Path, recheck: bool) -> str:
    """Bring one document up to date and return a status. Never overwrites a known file."""
    path = target_path(row, raw_dir)
    if path.exists() and not recheck:
        current = file_hash(path)
        if not row["sha256"]:
            row["sha256"] = current
            return "recorded"
        return "ok" if current == row["sha256"] else "CHANGED"

    content = fetcher.fetch_pdf(row["url"])
    new_hash = hashlib.sha256(content).hexdigest()
    if row["sha256"] and new_hash != row["sha256"]:
        return "CHANGED"  # a new version upstream: keep the old file and flag it
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    row["sha256"] = new_hash
    return "downloaded"


def verify_row(row: Row, raw_dir: Path) -> str:
    path = target_path(row, raw_dir)
    if not path.exists():
        return "MISSING"
    if not row["sha256"]:
        return "UNRECORDED"
    return "ok" if file_hash(path) == row["sha256"] else "CHANGED"


def select(rows: list[Row], stage: int | None, only: str | None) -> list[Row]:
    return [
        row
        for row in rows
        if (stage is None or int(row["stage"]) <= stage) and (only is None or row["doc_id"] == only)
    ]


def run_verify(rows: list[Row], raw_dir: Path) -> int:
    results = [(row["doc_id"], verify_row(row, raw_dir)) for row in rows]
    for doc_id, status in results:
        if status != "ok":
            print(f"{status:<11} {doc_id}")
    good = sum(status == "ok" for _, status in results)
    print(f"verified {good}/{len(results)}")
    return 0 if good == len(results) else 1


def run_download(
    rows: list[Row], fetcher: Fetcher, raw_dir: Path, recheck: bool, save: Callable[[], None]
) -> int:
    failed = 0
    for row in rows:
        try:
            status = download_row(row, fetcher, raw_dir, recheck)
        except Blocked as exc:
            status = f"BLOCKED ({exc})"
        except (NotPdf, httpx.HTTPError) as exc:
            status = f"FAILED ({type(exc).__name__}: {exc})"
        failed += status not in {"ok", "recorded", "downloaded"}
        print(f"{status:<11} {row['doc_id']}", flush=True)
        save()  # after each document, so an interrupted run keeps its hashes
    print(f"{len(rows) - failed}/{len(rows)} documents ready")
    return 1 if failed else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", type=int, help="include documents up to this corpus stage")
    parser.add_argument("--only", help="a single doc_id")
    parser.add_argument("--verify", action="store_true", help="check hashes only, no network")
    parser.add_argument("--recheck", action="store_true", help="re-fetch to detect new versions")
    args = parser.parse_args()

    rows = read_manifest(MANIFEST)
    chosen = select(rows, args.stage, args.only)
    if args.verify:
        return run_verify(chosen, RAW_DIR)

    email = get_settings().download_contact_email
    if not email:
        sys.exit("Set DOWNLOAD_CONTACT_EMAIL in .env first.")
    agent = (
        f"FraudDetection-corpus/0.1 (+https://github.com/vinhpnguyen123/frauddetection; {email})"
    )
    with httpx.Client(headers={"user-agent": agent}, timeout=60.0) as client:
        return run_download(
            chosen, Fetcher(client), RAW_DIR, args.recheck, lambda: write_manifest(MANIFEST, rows)
        )


if __name__ == "__main__":
    sys.exit(main())
