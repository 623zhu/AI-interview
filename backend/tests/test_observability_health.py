import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.core.health import check_directory, check_redis, health_payload, readiness_payload
from app.core.observability import REQUEST_ID_HEADER, RequestIDMiddleware


class FakeEngine:
    def __init__(self, fail: bool = False):
        self.fail = fail

    def connect(self):
        return self

    async def __aenter__(self):
        if self.fail:
            raise RuntimeError("db down")
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None

    async def execute(self, statement):
        return None


class PingRedis:
    def __init__(self, response=True):
        self.response = response

    async def ping(self):
        return self.response


async def redis_factory(response=True):
    return PingRedis(response)


def test_health_payload_is_process_only():
    payload = health_payload()

    assert payload["status"] == "ok"
    assert payload["app"]
    assert payload["version"]


def test_check_directory_creates_and_writes(tmp_path):
    target = tmp_path / "uploads"

    result = check_directory(str(target))

    assert result == {"ok": True, "status": "ok"}
    assert target.is_dir()


@pytest.mark.asyncio
async def test_check_redis_accepts_pong_response():
    result = await check_redis(lambda: redis_factory("PONG"))

    assert result == {"ok": True, "status": "ok"}


@pytest.mark.asyncio
async def test_readiness_payload_reports_failed_dependency(monkeypatch, tmp_path):
    monkeypatch.setattr("app.core.health.settings.UPLOAD_DIR", str(tmp_path / "uploads"))
    monkeypatch.setattr("app.core.health.settings.CHROMA_PERSIST_DIR", str(tmp_path / "chroma"))

    status_code, payload = await readiness_payload(
        engine=FakeEngine(fail=True),
        redis_factory=lambda: redis_factory(True),
    )

    assert status_code == 503
    assert payload["status"] == "not_ready"
    assert payload["checks"]["database"]["ok"] is False
    assert payload["checks"]["redis"]["ok"] is True


@pytest.mark.asyncio
async def test_request_id_middleware_uses_incoming_id():
    app = FastAPI()
    app.add_middleware(RequestIDMiddleware)

    @app.get("/ping")
    async def ping():
        return {"ok": True}

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get("/ping", headers={REQUEST_ID_HEADER: "req-123"})

    assert response.status_code == 200
    assert response.headers[REQUEST_ID_HEADER] == "req-123"


@pytest.mark.asyncio
async def test_request_id_middleware_generates_id_when_missing():
    app = FastAPI()
    app.add_middleware(RequestIDMiddleware)

    @app.get("/ping")
    async def ping():
        return {"ok": True}

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get("/ping")

    assert response.status_code == 200
    assert response.headers[REQUEST_ID_HEADER]
