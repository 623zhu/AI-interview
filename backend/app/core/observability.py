"""Request tracing helpers."""

from __future__ import annotations

import logging
import time
from contextvars import ContextVar
from uuid import uuid4

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


REQUEST_ID_HEADER = "X-Request-ID"
request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)
logger = logging.getLogger("app.http")


def get_request_id() -> str | None:
    return request_id_var.get()


class RequestIDMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        request_id = request.headers.get(REQUEST_ID_HEADER) or str(uuid4())
        started = time.perf_counter()
        token = request_id_var.set(request_id)
        request.state.request_id = request_id
        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
        finally:
            duration_ms = round((time.perf_counter() - started) * 1000, 2)
            client_ip = request.client.host if request.client else None
            logger.info(
                "http_request",
                extra={
                    "method": request.method,
                    "path": request.url.path,
                    "status_code": status_code,
                    "duration_ms": duration_ms,
                    "client_ip": client_ip,
                },
            )
            request_id_var.reset(token)

        response.headers[REQUEST_ID_HEADER] = request_id
        return response
