"""Small Redis-backed rate limiting helpers."""
from dataclasses import dataclass

from fastapi import HTTPException, Request
from redis.asyncio import Redis


@dataclass(frozen=True)
class RateLimit:
    limit: int
    window_seconds: int
    message: str = "请求过于频繁，请稍后再试"


def client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


async def check_rate_limit(redis: Redis, key: str, rule: RateLimit) -> None:
    count = await redis.incr(key)
    if count == 1:
        await redis.expire(key, rule.window_seconds)
    if count > rule.limit:
        ttl = await redis.ttl(key)
        retry_after = ttl if ttl and ttl > 0 else rule.window_seconds
        raise HTTPException(
            status_code=429,
            detail=rule.message,
            headers={"Retry-After": str(retry_after)},
        )


async def is_locked(redis: Redis, key: str, message: str) -> None:
    ttl = await redis.ttl(key)
    if ttl and ttl > 0:
        raise HTTPException(
            status_code=429,
            detail=message,
            headers={"Retry-After": str(ttl)},
        )
