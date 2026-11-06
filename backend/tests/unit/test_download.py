"""The download script, on a fake transport: nothing here touches the network."""

import hashlib
from collections.abc import Callable
from pathlib import Path

import httpx
import pytest
from scripts import download
from scripts.download import Blocked, Fetcher, NotPdf

PDF = b"%PDF-1.7 content"
URL = "https://host.test/doc.pdf"
Handler = Callable[[httpx.Request], httpx.Response]


def pdf_response() -> httpx.Response:
    return httpx.Response(200, content=PDF, headers={"content-type": "application/pdf"})


def site(robots: httpx.Response | None = None, *, doc: Handler | None = None) -> Handler:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return robots or httpx.Response(404)
        return doc(request) if doc else pdf_response()

    return handler


class Clock:
    def __init__(self) -> None:
        self.now = 0.0
        self.sleeps: list[float] = []

    def time(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


def fetcher(handler: Handler, clock: Clock | None = None) -> Fetcher:
    clock = clock or Clock()
    client = httpx.Client(
        transport=httpx.MockTransport(handler), headers={"user-agent": "test-agent"}
    )
    return Fetcher(client, sleep=clock.sleep, clock=clock.time)


def row(sha256: str = "") -> dict[str, str]:
    return {"doc_id": "fincen-x", "source": "fincen", "url": URL, "sha256": sha256, "stage": "1"}


def test_fetch_returns_the_pdf() -> None:
    assert fetcher(site()).fetch_pdf(URL) == PDF


def test_robots_disallow_is_respected() -> None:
    robots = httpx.Response(200, text="User-agent: *\nDisallow: /doc.pdf\n")
    with pytest.raises(Blocked, match="robots"):
        fetcher(site(robots)).fetch_pdf(URL)


def test_robots_refused_means_blocked_without_touching_the_document() -> None:
    seen: list[str] = []

    def doc(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.path)
        return pdf_response()

    with pytest.raises(Blocked, match="403"):
        fetcher(site(httpx.Response(403), doc=doc)).fetch_pdf(URL)
    assert seen == []


def test_a_refusing_host_is_asked_only_once() -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        return httpx.Response(403)

    fetch = fetcher(handler)
    for _ in range(3):
        with pytest.raises(Blocked):
            fetch.fetch_pdf(URL)
    assert calls == ["/robots.txt"]


def test_forbidden_document_is_blocked_and_not_retried() -> None:
    calls: list[int] = []

    def doc(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(403)

    with pytest.raises(Blocked):
        fetcher(site(doc=doc)).fetch_pdf(URL)
    assert len(calls) == 1


def test_html_is_rejected_even_with_a_pdf_content_type() -> None:
    def doc(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"<html>", headers={"content-type": "application/pdf"})

    with pytest.raises(NotPdf):
        fetcher(site(doc=doc)).fetch_pdf(URL)


def test_wrong_content_type_is_rejected() -> None:
    def doc(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=PDF, headers={"content-type": "text/html"})

    with pytest.raises(NotPdf):
        fetcher(site(doc=doc)).fetch_pdf(URL)


def test_server_errors_are_retried_with_backoff() -> None:
    responses = [httpx.Response(503), httpx.Response(429), pdf_response()]
    clock = Clock()
    assert fetcher(site(doc=lambda _: responses.pop(0)), clock).fetch_pdf(URL) == PDF
    assert 2.0 in clock.sleeps and 4.0 in clock.sleeps


def test_retries_give_up() -> None:
    with pytest.raises(httpx.HTTPStatusError):
        fetcher(site(doc=lambda _: httpx.Response(503))).fetch_pdf(URL)


def test_requests_to_one_host_are_spaced_out() -> None:
    clock = Clock()
    fetch = fetcher(site(), clock)
    fetch.fetch_pdf(URL)
    fetch.fetch_pdf(URL)
    assert clock.sleeps == [2.0, 2.0]  # robots -> first document -> second document


def test_download_saves_and_records_the_hash(tmp_path: Path) -> None:
    entry = row()
    assert download.download_row(entry, fetcher(site()), tmp_path, recheck=False) == "downloaded"
    assert (tmp_path / "fincen" / "fincen-x.pdf").read_bytes() == PDF
    assert entry["sha256"] == hashlib.sha256(PDF).hexdigest()


def test_changed_upstream_keeps_the_old_file(tmp_path: Path) -> None:
    path = tmp_path / "fincen" / "fincen-x.pdf"
    path.parent.mkdir()
    path.write_bytes(b"%PDF-old")
    entry = row(hashlib.sha256(b"%PDF-old").hexdigest())

    status = download.download_row(entry, fetcher(site()), tmp_path, recheck=True)

    assert status == "CHANGED"
    assert path.read_bytes() == b"%PDF-old"
    assert entry["sha256"] == hashlib.sha256(b"%PDF-old").hexdigest()


def test_hand_saved_file_is_recorded_without_any_request(tmp_path: Path) -> None:
    path = tmp_path / "fincen" / "fincen-x.pdf"
    path.parent.mkdir()
    path.write_bytes(PDF)

    def no_network(request: httpx.Request) -> httpx.Response:
        raise AssertionError("must not fetch")

    entry = row()
    assert download.download_row(entry, fetcher(no_network), tmp_path, recheck=False) == "recorded"
    assert entry["sha256"] == hashlib.sha256(PDF).hexdigest()


@pytest.mark.parametrize(
    ("content", "recorded", "expected"),
    [
        (PDF, hashlib.sha256(PDF).hexdigest(), "ok"),
        (b"tampered", hashlib.sha256(PDF).hexdigest(), "CHANGED"),
        (PDF, "", "UNRECORDED"),
        (None, "abc", "MISSING"),
    ],
)
def test_verify(tmp_path: Path, content: bytes | None, recorded: str, expected: str) -> None:
    if content is not None:
        path = tmp_path / "fincen" / "fincen-x.pdf"
        path.parent.mkdir()
        path.write_bytes(content)
    assert download.verify_row(row(recorded), tmp_path) == expected


def test_select_filters_by_stage_and_id() -> None:
    rows = [{"doc_id": "a", "stage": "1"}, {"doc_id": "b", "stage": "2"}]
    assert [r["doc_id"] for r in download.select(rows, 1, None)] == ["a"]
    assert [r["doc_id"] for r in download.select(rows, None, "b")] == ["b"]
