"""Application errors and the JSON error envelope: ``{"error": {"code", "message", "details"}}``."""

from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException


class AppError(Exception):
    status = 400
    code = "BAD_REQUEST"

    def __init__(self, message: str = "", *, code: str | None = None, status: int | None = None, **details: Any):
        super().__init__(message or self.code)
        self.message = message or self.code.replace("_", " ").capitalize()
        if code:
            self.code = code
        if status:
            self.status = status
        self.details = details


class Unauthorized(AppError):
    status, code = 401, "UNAUTHENTICATED"


class Forbidden(AppError):
    status, code = 403, "FORBIDDEN"


class PlanRequired(AppError):
    status, code = 403, "PLAN_REQUIRED"


class NotFound(AppError):
    status, code = 404, "NOT_FOUND"


class Conflict(AppError):
    status, code = 409, "CONFLICT"


class InsufficientFunds(AppError):
    status, code = 409, "INSUFFICIENT_FUNDS"


class QuotaExceeded(AppError):
    status, code = 429, "QUOTA_EXCEEDED"


class RateLimited(AppError):
    status, code = 429, "RATE_LIMITED"


def _envelope(status: int, code: str, message: str, details: dict[str, Any] | None = None) -> JSONResponse:
    return JSONResponse(
        status_code=status, content={"error": {"code": code, "message": message, "details": details or {}}}
    )


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(_: Request, exc: AppError) -> JSONResponse:
        return _envelope(exc.status, exc.code, exc.message, exc.details)

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError) -> JSONResponse:
        errors = [
            {"loc": [str(p) for p in e.get("loc", ())], "msg": e.get("msg", ""), "type": e.get("type", "")}
            for e in exc.errors()
        ]
        return _envelope(422, "VALIDATION_ERROR", "The request is not valid", {"errors": errors})

    @app.exception_handler(StarletteHTTPException)
    async def _http(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = {404: "NOT_FOUND", 405: "METHOD_NOT_ALLOWED"}.get(exc.status_code, "HTTP_ERROR")
        return _envelope(exc.status_code, code, str(exc.detail))
