import pytest
from fastapi import FastAPI, HTTPException
from httpx import ASGITransport, AsyncClient
from pydantic import BaseModel

from app.core.errors import install_exception_handlers
from app.core.observability import REQUEST_ID_HEADER, RequestIDMiddleware


class Item(BaseModel):
    count: int


def make_app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(RequestIDMiddleware)
    install_exception_handlers(app)

    @app.get("/plain-error")
    async def plain_error():
        raise HTTPException(status_code=404, detail="missing")

    @app.get("/structured-error")
    async def structured_error():
        raise HTTPException(
            status_code=400,
            detail={
                "code": "domain_error",
                "message": "Domain error",
                "field": "status",
            },
        )

    @app.post("/items")
    async def create_item(item: Item):
        return item

    @app.get("/boom")
    async def boom():
        raise RuntimeError("secret stack detail")

    return app


@pytest.mark.asyncio
async def test_http_exception_response_has_stable_shape():
    async with AsyncClient(
        transport=ASGITransport(app=make_app()),
        base_url="http://test",
    ) as client:
        response = await client.get("/plain-error", headers={REQUEST_ID_HEADER: "req-1"})

    assert response.status_code == 404
    assert response.json() == {
        "code": "not_found",
        "message": "missing",
        "request_id": "req-1",
    }


@pytest.mark.asyncio
async def test_structured_http_exception_preserves_details():
    async with AsyncClient(
        transport=ASGITransport(app=make_app()),
        base_url="http://test",
    ) as client:
        response = await client.get("/structured-error", headers={REQUEST_ID_HEADER: "req-2"})

    assert response.status_code == 400
    assert response.json() == {
        "code": "domain_error",
        "message": "Domain error",
        "request_id": "req-2",
        "details": {"field": "status"},
    }


@pytest.mark.asyncio
async def test_validation_error_response_has_details():
    async with AsyncClient(
        transport=ASGITransport(app=make_app()),
        base_url="http://test",
    ) as client:
        response = await client.post("/items", json={"count": "not-int"})

    payload = response.json()
    assert response.status_code == 422
    assert payload["code"] == "validation_error"
    assert payload["message"] == "请求参数校验失败"
    assert payload["request_id"]
    assert payload["details"]


@pytest.mark.asyncio
async def test_unhandled_error_response_does_not_leak_exception_detail():
    async with AsyncClient(
        transport=ASGITransport(app=make_app(), raise_app_exceptions=False),
        base_url="http://test",
    ) as client:
        response = await client.get("/boom", headers={REQUEST_ID_HEADER: "req-3"})

    assert response.status_code == 500
    assert response.json() == {
        "code": "internal_server_error",
        "message": "服务器内部错误",
        "request_id": "req-3",
    }
