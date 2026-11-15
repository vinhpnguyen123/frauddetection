"""The single exception handler: each domain error maps to its status and a fixed message."""

import pytest
from fastapi.testclient import TestClient

from app.errors import (
    Forbidden,
    FraudDetectionError,
    IngestionFailed,
    LLMOutputInvalid,
    NotFound,
    RateLimited,
)
from app.main import create_app


@pytest.mark.parametrize(
    ("error", "status"),
    [
        (NotFound, 404),
        (Forbidden, 403),
        (RateLimited, 429),
        (LLMOutputInvalid, 502),
        (IngestionFailed, 422),
        (FraudDetectionError, 500),
    ],
)
def test_handler_maps_status_and_hides_internal_message(
    error: type[FraudDetectionError], status: int
) -> None:
    app = create_app()

    @app.get("/boom")
    async def boom() -> None:
        raise error("tenant-b secret-policy.pdf")  # internal detail that must not leak

    response = TestClient(app).get("/boom")
    assert response.status_code == status
    assert response.json() == {"detail": error.public_message}
    assert "secret-policy" not in response.text
