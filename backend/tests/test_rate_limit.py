import pytest
from fastapi import HTTPException

from app.core.rate_limit import RateLimit, check_rate_limit, is_locked


@pytest.mark.asyncio
async def test_check_rate_limit_blocks_after_threshold(fake_redis):
    rule = RateLimit(limit=2, window_seconds=60, message="too many")

    await check_rate_limit(fake_redis, "rl:test", rule)
    await check_rate_limit(fake_redis, "rl:test", rule)

    with pytest.raises(HTTPException) as exc:
        await check_rate_limit(fake_redis, "rl:test", rule)

    assert exc.value.status_code == 429
    assert exc.value.headers["Retry-After"] == "60"


@pytest.mark.asyncio
async def test_is_locked_raises_when_lock_has_ttl(fake_redis):
    await fake_redis.setex("lock:test", 30, "1")

    with pytest.raises(HTTPException) as exc:
        await is_locked(fake_redis, "lock:test", "locked")

    assert exc.value.status_code == 429
    assert exc.value.headers["Retry-After"] == "30"
