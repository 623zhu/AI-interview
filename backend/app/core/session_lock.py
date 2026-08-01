"""Redis-backed locks for session-scoped operations."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress
from uuid import uuid4

from redis.asyncio import Redis


SESSION_LOCK_TTL_SECONDS = 120
logger = logging.getLogger(__name__)

_RENEW_SCRIPT = """
if redis.call('get', KEYS[1]) == ARGV[1] then
    return redis.call('expire', KEYS[1], ARGV[2])
end
return 0
"""

_RELEASE_SCRIPT = """
if redis.call('get', KEYS[1]) == ARGV[1] then
    return redis.call('del', KEYS[1])
end
return 0
"""


def session_lock_key(session_id: str) -> str:
    return f"lock:interview_session:{session_id}"


async def acquire_session_lock(
    redis: Redis,
    session_id: str,
    *,
    ttl_seconds: int = SESSION_LOCK_TTL_SECONDS,
) -> str | None:
    """用 Redis SET NX 获取会话锁；已有请求持锁时返回 None。"""
    token = str(uuid4())
    acquired = await redis.set(
        session_lock_key(session_id),
        token,
        ex=ttl_seconds,
        nx=True,
    )
    return token if acquired else None


async def release_session_lock(redis: Redis, session_id: str, token: str) -> bool:
    """仅锁的当前持有者可以释放；Lua 保证比较 token 和删除不可被插队。"""
    released = await redis.eval(
        _RELEASE_SCRIPT,
        1,
        session_lock_key(session_id),
        token,
    )
    return bool(released)


async def renew_session_lock(
    redis: Redis,
    session_id: str,
    token: str,
    *,
    ttl_seconds: int = SESSION_LOCK_TTL_SECONDS,
) -> bool:
    """仅在 token 仍匹配时延长 TTL，锁已经易主则返回 False。"""
    renewed = await redis.eval(
        _RENEW_SCRIPT,
        1,
        session_lock_key(session_id),
        token,
        ttl_seconds,
    )
    return bool(renewed)


@asynccontextmanager
async def session_lock_lease(
    redis: Redis,
    session_id: str,
    token: str,
    *,
    ttl_seconds: int = SESSION_LOCK_TTL_SECONDS,
    renew_interval_seconds: float | None = None,
) -> AsyncIterator[None]:
    """在耗时操作期间定时续租，并在退出代码块时原子释放锁。

    API 使用 ``async with session_lock_lease(...)`` 包住整轮图执行，避免
    LLM/RAG 超过固定 TTL 后另一个请求误以为锁已空闲。
    """
    interval = renew_interval_seconds or max(0.1, ttl_seconds / 3)

    async def heartbeat() -> None:
        while True:
            await asyncio.sleep(interval)
            try:
                if not await renew_session_lock(
                    redis,
                    session_id,
                    token,
                    ttl_seconds=ttl_seconds,
                ):
                    logger.warning("Session lock lease lost session=%s", session_id)
                    return
            except Exception:
                logger.exception("Session lock renewal failed session=%s", session_id)
                return

    task = asyncio.create_task(heartbeat())
    try:
        yield
    finally:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task
        await release_session_lock(redis, session_id, token)
