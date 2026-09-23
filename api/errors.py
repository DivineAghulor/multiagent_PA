"""A single error envelope for the whole API.

Every failure reaches the client as `{"error": {"type", "message"}}` with a
machine-readable `type`, because the frontend has to tell these apart: a
validation error is the user's to fix, a provider error is worth retrying, and
a missing draft session means "this draft was lost, start again" rather than a
generic failure (requirements §5 S-3, API-1).
"""
from __future__ import annotations

import logging
import re
from collections.abc import Iterator
from contextlib import contextmanager

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import ValidationError as PydanticValidationError
from sqlalchemy.exc import SQLAlchemyError

logger = logging.getLogger(__name__)

NOT_FOUND = "not_found"
INVALID_REQUEST = "invalid_request"
VALIDATION = "validation"
SESSION_EXPIRED = "session_expired"  # a draft session that no longer exists
CONFLICT = "conflict"  # e.g. a turn is already running on this draft session
PROVIDER = "provider"  # the LLM provider failed or is misconfigured
INTERNAL = "internal"

# Longest provider error text passed on to the client.
_MAX_PROVIDER_MESSAGE = 400


class ApiError(Exception):
    """Raised by handlers; rendered into the envelope by the handler below."""

    def __init__(self, type_: str, message: str, status_code: int) -> None:
        super().__init__(message)
        self.type = type_
        self.message = message
        self.status_code = status_code


class NotFoundError(ApiError):
    def __init__(self, what: str, id_: object) -> None:
        super().__init__(NOT_FOUND, f"{what} {id_} not found", status.HTTP_404_NOT_FOUND)


class InvalidRequestError(ApiError):
    def __init__(self, message: str) -> None:
        super().__init__(INVALID_REQUEST, message, status.HTTP_400_BAD_REQUEST)


class SessionExpiredError(ApiError):
    """The draft session is gone: never existed, expired, already confirmed,
    or lost in a backend restart. The UI says "this draft was lost, start
    again" rather than showing a generic error (S-3)."""

    def __init__(self, session_id: str) -> None:
        super().__init__(
            SESSION_EXPIRED,
            f"Draft session {session_id} no longer exists — it expired, was already "
            "confirmed, or was lost when the server restarted. Start again.",
            status.HTTP_404_NOT_FOUND,
        )


class ConflictError(ApiError):
    def __init__(self, message: str) -> None:
        super().__init__(CONFLICT, message, status.HTTP_409_CONFLICT)


class ProviderError(ApiError):
    """The model call failed. 503 when it never started (no key configured),
    502 when the provider was reached and failed or returned something
    unusable — both are worth retrying once fixed, unlike a validation error."""

    def __init__(self, message: str, status_code: int = status.HTTP_502_BAD_GATEWAY) -> None:
        super().__init__(PROVIDER, message, status_code)


# Anything shaped like a credential: provider key prefixes, bearer tokens, and
# long unbroken runs of key-ish characters. Some providers echo a masked slice
# of the key back in auth errors ("Incorrect API key provided: sk-ab***yz"),
# and even a slice must never reach a response (SEC-3).
_SECRETISH = re.compile(
    r"(?i)(?:bearer\s+\S+|\b(?:(?:sk|pk|rk|gsk|xai)[-_]|AIza)[-_A-Za-z0-9*.]{6,}|[A-Za-z0-9*_\-]{32,})"
)


def redact(text: str) -> str:
    return _SECRETISH.sub("[redacted]", text)


def provider_message(exc: BaseException) -> str:
    """A client-safe one-line description of a failed model call."""
    detail = redact(" ".join(str(exc).split()))
    message = f"The model call failed ({type(exc).__name__})" + (f": {detail}" if detail else "")
    if len(message) > _MAX_PROVIDER_MESSAGE:
        message = message[: _MAX_PROVIDER_MESSAGE - 1] + "\u2026"
    return message


def require_provider() -> None:
    """Refuse a model-backed request up front when no provider key is
    configured, so the failure is a clear 503 rather than an SDK auth error."""
    from config import settings
    from llm import factory

    if not factory.provider_key_configured():
        raise ProviderError(
            f"No API key is configured for the '{settings.llm_provider}' provider, so "
            "model-backed actions are unavailable. Everything else still works.",
            status.HTTP_503_SERVICE_UNAVAILABLE,
        )


@contextmanager
def model_call() -> Iterator[None]:
    """Wrap the one agent call in a handler that reaches the model.

    Checks require_provider() first. Anything the call raises that isn't
    already an ApiError becomes a ProviderError: provider outages, quota
    errors and malformed structured output (a pydantic ValidationError) all
    mean the same thing to the user — nothing was saved, try again (API-1).
    """
    require_provider()
    try:
        yield
    except (ApiError, SQLAlchemyError):
        # A database failure around the call is not the provider's fault; it
        # falls through to the generic 500 below.
        raise
    except Exception as exc:  # noqa: BLE001 — surfaced to the client as a typed error
        logger.exception("model call failed")
        raise ProviderError(provider_message(exc)) from exc


def _envelope(type_: str, message: str, status_code: int) -> JSONResponse:
    return JSONResponse(status_code=status_code, content={"error": {"type": type_, "message": message}})


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def _api_error(_: Request, exc: ApiError) -> JSONResponse:
        return _envelope(exc.type, exc.message, exc.status_code)

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        # Flatten FastAPI's per-field list into one readable sentence; the
        # frontend shows it verbatim.
        parts = [f"{'.'.join(str(p) for p in e['loc'][1:])}: {e['msg']}" for e in exc.errors()]
        return _envelope(
            VALIDATION, "; ".join(parts) or "invalid request", status.HTTP_422_UNPROCESSABLE_CONTENT
        )

    @app.exception_handler(PydanticValidationError)
    async def _response_model_error(_: Request, exc: PydanticValidationError) -> JSONResponse:
        # Handled before ValueError, which it subclasses. This is a response
        # model failing to build — our bug, not the caller's, so it must not be
        # reported as a bad request. Most likely cause: serialising an unloaded
        # relationship off a detached ORM instance.
        logger.exception("response model failed to serialise")
        return _envelope(
            INTERNAL, "the server could not serialise its response", status.HTTP_500_INTERNAL_SERVER_ERROR
        )

    @app.exception_handler(ValueError)
    async def _value_error(_: Request, exc: ValueError) -> JSONResponse:
        # tools/* raise ValueError for rejected input (bad rating, non-Monday
        # week start). Handlers check existence themselves and raise
        # NotFoundError, so a ValueError reaching here is a bad request.
        return _envelope(INVALID_REQUEST, str(exc), status.HTTP_400_BAD_REQUEST)

    @app.exception_handler(Exception)
    async def _unhandled(_: Request, exc: Exception) -> JSONResponse:
        # Anything else keeps the envelope, so the client never has to parse a
        # bare "Internal Server Error" page. The detail goes to the log only.
        logger.exception("unhandled error")
        return _envelope(INTERNAL, "the server hit an unexpected error", status.HTTP_500_INTERNAL_SERVER_ERROR)
