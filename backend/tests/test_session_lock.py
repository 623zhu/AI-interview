import pytest

from app.core.session_lock import (
    acquire_session_lock,
    release_session_lock,
    session_lock_key,
)


@pytest.mark.asyncio
async def test_session_lock_allows_single_owner(fake_redis):
    first_token = await acquire_session_lock(fake_redis, "session-1")
    second_token = await acquire_session_lock(fake_redis, "session-1")

    assert first_token
    assert second_token is None
    assert fake_redis.values[session_lock_key("session-1")] == first_token


@pytest.mark.asyncio
async def test_session_lock_release_requires_matching_token(fake_redis):
    token = await acquire_session_lock(fake_redis, "session-1")

    assert await release_session_lock(fake_redis, "session-1", "wrong-token") is False
    assert fake_redis.values[session_lock_key("session-1")] == token

    assert await release_session_lock(fake_redis, "session-1", token) is True
    assert session_lock_key("session-1") not in fake_redis.values
