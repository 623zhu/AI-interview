"""Health and readiness checks."""

from __future__ import annotations

from pathlib import Path
from typing import Awaitable, Callable

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine
from redis.asyncio import Redis

from app.core.config import settings

CheckResult = dict[str, str | bool]


def health_payload() -> dict:
    return {
        "status": "ok",
        "app": settings.APP_NAME,
        "version": settings.APP_VERSION,
    }


async def check_database(engine: AsyncEngine) -> CheckResult:
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return {"ok": True, "status": "ok"}
    except Exception as exc:
        return {"ok": False, "status": "failed", "error": exc.__class__.__name__}


async def check_redis(redis_factory: Callable[[], Awaitable[Redis]]) -> CheckResult:
    try:
        redis = await redis_factory()
        pong = await redis.ping()
        if pong is True or str(pong).upper() == "PONG":
            return {"ok": True, "status": "ok"}
        return {"ok": False, "status": "failed", "error": "UnexpectedPingResponse"}
    except Exception as exc:
        return {"ok": False, "status": "failed", "error": exc.__class__.__name__}


def check_directory(path: str) -> CheckResult:
    try:
        directory = Path(path)
        directory.mkdir(parents=True, exist_ok=True)
        if not directory.is_dir():
            return {"ok": False, "status": "failed", "error": "NotDirectory"}
        probe = directory / ".write_check"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
        return {"ok": True, "status": "ok"}
    except Exception as exc:
        return {"ok": False, "status": "failed", "error": exc.__class__.__name__}


async def readiness_payload(
    *,
    engine: AsyncEngine,
    redis_factory: Callable[[], Awaitable[Redis]],
) -> tuple[int, dict]:
    checks = {
        "database": await check_database(engine),
        "redis": await check_redis(redis_factory),
        "uploads": check_directory(settings.UPLOAD_DIR),
        "chroma": check_directory(settings.CHROMA_PERSIST_DIR),
    }
    ok = all(bool(result["ok"]) for result in checks.values())
    return (
        200 if ok else 503,
        {
            "status": "ready" if ok else "not_ready",
            "checks": checks,
            "app": settings.APP_NAME,
            "version": settings.APP_VERSION,
        },
    )
