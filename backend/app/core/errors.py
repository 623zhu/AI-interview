"""Unified API error responses."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette import status

from app.core.observability import get_request_id


DEFAULT_ERROR_CODES = {
    400: "bad_request",
    401: "unauthorized",
    403: "forbidden",
    404: "not_found",
    409: "conflict",
    422: "validation_error",
    429: "rate_limited",
    500: "internal_server_error",
    503: "service_unavailable",
}


def _request_id(request: Request) -> str | None:
    return getattr(request.state, "request_id", None) or get_request_id()


def error_payload(
    *,
    status_code: int,
    message: str,
    request_id: str | None,
    code: str | None = None,
    details: Any | None = None,
) -> dict[str, Any]:
    payload = {
        "code": code or DEFAULT_ERROR_CODES.get(status_code, "error"),
        "message": message,
        "request_id": request_id,
    }
    if details is not None:
        payload["details"] = details
    return payload


def _detail_to_error(status_code: int, detail: Any) -> tuple[str, str, Any | None]:
    if isinstance(detail, dict):
        code = str(detail.get("code") or DEFAULT_ERROR_CODES.get(status_code, "error"))
        message = str(detail.get("message") or DEFAULT_ERROR_CODES.get(status_code, "error"))
        details = {k: v for k, v in detail.items() if k not in {"code", "message"}}
        return code, message, details or None

    return DEFAULT_ERROR_CODES.get(status_code, "error"), str(detail), None


async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    code, message, details = _detail_to_error(exc.status_code, exc.detail)
    return JSONResponse(
        status_code=exc.status_code,
        content=error_payload(
            status_code=exc.status_code,
            code=code,
            message=message,
            details=details,
            request_id=_request_id(request),
        ),
        headers=exc.headers,
    )


async def validation_exception_handler(
    request: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content=error_payload(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            code="validation_error",
            message="请求参数校验失败",
            details=exc.errors(),
            request_id=_request_id(request),
        ),
    )


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=error_payload(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            code="internal_server_error",
            message="服务器内部错误",
            request_id=_request_id(request),
        ),
    )


def install_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(HTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)
