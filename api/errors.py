"""A single error envelope for the whole API.

Every failure reaches the client as `{"error": {"type", "message"}}` with a
machine-readable `type`, because the frontend has to tell these apart: a
validation error is the user's to fix, a provider error is worth retrying, and
a missing draft session means "this draft was lost, start again" rather than a
generic failure (requirements §5 S-3, API-1).
"""
from __future__ import annotations

import logging

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import ValidationError as PydanticValidationError

logger = logging.getLogger(__name__)

NOT_FOUND = "not_found"
INVALID_REQUEST = "invalid_request"
VALIDATION = "validation"
SESSION_EXPIRED = "session_expired"  # a draft session that no longer exists (W3)
PROVIDER = "provider"  # the LLM provider failed or is misconfigured (W2)
INTERNAL = "internal"


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
