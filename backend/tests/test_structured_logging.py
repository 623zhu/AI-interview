import json
import logging

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.core.logging import JsonLogFormatter
from app.core.observability import REQUEST_ID_HEADER, RequestIDMiddleware


def test_json_log_formatter_outputs_stable_fields():
    formatter = JsonLogFormatter()
    record = logging.LogRecord(
        name="app.test",
        level=logging.INFO,
        pathname=__file__,
        lineno=10,
        msg="hello %s",
        args=("world",),
        exc_info=None,
    )

    payload = json.loads(formatter.format(record))

    assert payload["level"] == "INFO"
    assert payload["logger"] == "app.test"
    assert payload["message"] == "hello world"
    assert "timestamp" in payload
    assert "request_id" in payload


@pytest.mark.asyncio
async def test_http_request_log_includes_request_metadata(caplog):
    app = FastAPI()
    app.add_middleware(RequestIDMiddleware)

    @app.get("/ping")
    async def ping():
        return {"ok": True}

    caplog.set_level(logging.INFO, logger="app.http")
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get("/ping", headers={REQUEST_ID_HEADER: "req-log"})

    assert response.status_code == 200
    records = [record for record in caplog.records if record.name == "app.http"]
    assert records
    record = records[-1]
    assert record.getMessage() == "http_request"
    assert record.method == "GET"
    assert record.path == "/ping"
    assert record.status_code == 200
    assert record.duration_ms >= 0
