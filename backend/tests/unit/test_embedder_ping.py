from collections.abc import Callable
from types import SimpleNamespace

import httpx
import pytest

from app import embedder

Handler = Callable[[httpx.Request], httpx.Response]


@pytest.fixture
def use_handler(monkeypatch: pytest.MonkeyPatch) -> Callable[[Handler], None]:
    """Route the probe through a fake transport, so nothing touches the network."""
    real_client = httpx.AsyncClient
    settings = SimpleNamespace(embedder_url="http://embedder.test")
    monkeypatch.setattr(embedder, "get_settings", lambda: settings)

    def use(handler: Handler) -> None:
        transport = httpx.MockTransport(handler)
        monkeypatch.setattr(httpx, "AsyncClient", lambda: real_client(transport=transport))

    return use


async def test_ping_calls_the_healthz_endpoint(use_handler: Callable[[Handler], None]) -> None:
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        return httpx.Response(200, json={"status": "ok"})

    use_handler(handler)
    await embedder.ping()
    assert seen == ["http://embedder.test/healthz"]


async def test_ping_raises_on_an_unhealthy_response(use_handler: Callable[[Handler], None]) -> None:
    use_handler(lambda _: httpx.Response(500))
    with pytest.raises(httpx.HTTPStatusError):
        await embedder.ping()


async def test_ping_raises_on_timeout(use_handler: Callable[[Handler], None]) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("timed out", request=request)

    use_handler(handler)
    with pytest.raises(httpx.ConnectTimeout):
        await embedder.ping()
