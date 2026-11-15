"""Domain errors and the one handler that maps them to HTTP (CONVENTIONS §4)."""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse


class FraudDetectionError(Exception):
    """Base of every domain error. `status` and `public_message` are what a client sees."""

    status = 500
    public_message = "internal error"


class NotFound(FraudDetectionError):
    """Also raised when access is denied to a private resource, so its existence never leaks."""

    status = 404
    public_message = "not found"


class Forbidden(FraudDetectionError):
    """A role check failed on a resource the user already knows exists (e.g. admin-only)."""

    status = 403
    public_message = "forbidden"


class RateLimited(FraudDetectionError):
    """An upstream (Gemini) answered 429. Surfaced to the caller, never retried forever."""

    status = 429
    public_message = "rate limited, try again later"


class LLMOutputInvalid(FraudDetectionError):
    """The LLM answered, but not with JSON that matches the expected schema."""

    status = 502
    public_message = "the language model returned an invalid response"


class IngestionFailed(FraudDetectionError):
    """A failure that a retry cannot fix, such as a corrupt file or a broken document."""

    status = 422
    public_message = "the document could not be ingested"


async def _handle(_: Request, error: Exception) -> JSONResponse:
    # The message passed to the exception is for logs only: it may name a document or
    # quote model output, so the client only ever gets the fixed public message.
    assert isinstance(error, FraudDetectionError)
    return JSONResponse(status_code=error.status, content={"detail": error.public_message})


def install_handler(app: FastAPI) -> None:
    """Register the single handler for every FraudDetectionError subclass."""
    app.add_exception_handler(FraudDetectionError, _handle)
