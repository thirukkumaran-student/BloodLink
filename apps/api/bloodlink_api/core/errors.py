"""Domain exception types + FastAPI exception handlers (owner: D1, spec §14).

Feature developers raise ``DomainError`` subclasses (or the small helpers at the
bottom of this module). The handlers translate them into the canonical envelope,
so no router ever hand-rolls an error response.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import ValidationError as PydanticValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from bloodlink_contracts.envelope import error_envelope
from bloodlink_contracts.errors import ErrorCode, http_status

logger = logging.getLogger("bloodlink.api.errors")


class DomainError(Exception):
    """Base class for business-rule failures inside feature modules."""

    code: ErrorCode = ErrorCode.INTERNAL_ERROR
    message: str = "Something went wrong"
    details: list[dict[str, Any]] | None = None

    def __init__(
        self,
        message: str | None = None,
        *,
        code: ErrorCode | None = None,
        details: list[dict[str, Any]] | None = None,
        status_code: int | None = None,
    ) -> None:
        self.message = message or self.message
        self.code = code or self.code
        self.details = details if details is not None else self.details
        self.status_code = status_code or http_status(self.code)
        super().__init__(self.message)


# --------------------------------------------------------------------------- #
# Reusable error types — feature modules may subclass or use directly.
# --------------------------------------------------------------------------- #
class NotFoundError(DomainError):
    code = ErrorCode.NOT_FOUND
    message = "Resource not found"


class ConflictError(DomainError):
    code = ErrorCode.CONFLICT
    message = "Conflicting state"


class ForbiddenError(DomainError):
    code = ErrorCode.FORBIDDEN
    message = "You are not allowed to perform this action"


class UnauthenticatedError(DomainError):
    code = ErrorCode.UNAUTHENTICATED
    message = "Authentication required"


class UnprocessableError(DomainError):
    code = ErrorCode.UNPROCESSABLE
    message = "Request cannot be processed"


class PrivacyViolationError(DomainError):
    code = ErrorCode.PRIVACY_VIOLATION
    message = "Request would expose protected information"


def request_id_of(request: Request) -> str:
    return getattr(request.state, "request_id", None) or str(uuid.uuid4())


def _json(payload: dict[str, Any], status_code: int, request: Request) -> JSONResponse:
    return JSONResponse(payload, status_code=status_code, headers={"X-Request-Id": request_id_of(request)})


def register_exception_handlers(app: FastAPI) -> None:
    """Wire every error class into the canonical envelope."""

    @app.exception_handler(DomainError)
    async def _domain_error(request: Request, exc: DomainError) -> JSONResponse:
        request_id = request_id_of(request)
        logger.info(
            "domain_error code=%s path=%s request_id=%s", exc.code.value, request.url.path, request_id
        )
        return _json(
            error_envelope(exc.code.value, exc.message, details=exc.details, request_id=request_id),
            exc.status_code,
            request,
        )

    @app.exception_handler(RequestValidationError)
    async def _request_validation(request: Request, exc: RequestValidationError) -> JSONResponse:
        details = [
            {
                "field": ".".join(str(part) for part in error.get("loc", ()) if part not in ("body", "query")),
                "message": error.get("msg", "Invalid value"),
            }
            for error in exc.errors()
        ]
        return _json(
            error_envelope(
                ErrorCode.VALIDATION_ERROR.value,
                "The submitted data is invalid",
                details=details,
                request_id=request_id_of(request),
            ),
            422,
            request,
        )

    @app.exception_handler(PydanticValidationError)
    async def _pydantic_validation(request: Request, exc: PydanticValidationError) -> JSONResponse:
        details = [
            {
                "field": ".".join(str(part) for part in error.get("loc", ())),
                "message": error.get("msg", "Invalid value"),
            }
            for error in exc.errors()
        ]
        return _json(
            error_envelope(
                ErrorCode.VALIDATION_ERROR.value,
                "The submitted data is invalid",
                details=details,
                request_id=request_id_of(request),
            ),
            422,
            request,
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = {
            400: ErrorCode.VALIDATION_ERROR,
            401: ErrorCode.UNAUTHENTICATED,
            403: ErrorCode.FORBIDDEN,
            404: ErrorCode.NOT_FOUND,
            409: ErrorCode.CONFLICT,
            422: ErrorCode.UNPROCESSABLE,
        }.get(exc.status_code, ErrorCode.INTERNAL_ERROR)
        message = exc.detail if isinstance(exc.detail, str) else "Request failed"
        return _json(
            error_envelope(code.value, message, request_id=request_id_of(request)),
            exc.status_code,
            request,
        )

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        request_id = request_id_of(request)
        logger.exception("unhandled_error path=%s request_id=%s", request.url.path, request_id)
        # Never leak stack traces or internal messages (spec §14).
        return _json(
            error_envelope(
                ErrorCode.INTERNAL_ERROR.value,
                "An unexpected error occurred. Please try again.",
                request_id=request_id,
            ),
            500,
            request,
        )
