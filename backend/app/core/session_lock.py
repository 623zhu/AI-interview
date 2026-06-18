"""Redis-backed locks for session-scoped operations."""

from __future__ import annotations

from uuid import uuid4

from redis.asyncio import Redis


SESSION_LOCK_TTL_SECONDS = 120


def session_lock_key(session_id: str) -> str:
    return f"lock:interview_session:{session_id}"


async def acquire_session_lock(
    redis: Redis,
    session_id: str,
    *,
    ttl_seconds: int = SESSION_LOCK_TTL_SECONDS,
) -> str | None:
    token = str(uuid4())
    acquired = await redis.set(
        session_lock_key(session_id),
        token,
        ex=ttl_seconds,
        nx=True,
    )
    return token if acquired else None


async def release_session_lock(redis: Redis, session_id: str, token: str) -> bool:
    key = session_lock_key(session_id)
    stored = await redis.get(key)
    if stored != token:
        return False

    await redis.delete(key)
    return True
