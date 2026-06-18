from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.api.v1 import auth
from app.core.security import hash_password
from app.models.user import User
from app.schemas.auth import UserLogin


def _request(ip: str = "127.0.0.1"):
    return SimpleNamespace(headers={}, client=SimpleNamespace(host=ip))


@pytest.mark.asyncio
async def test_login_failures_lock_email(db_session, fake_redis):
    user = User(
        username="alice",
        email="alice@example.com",
        password_hash=hash_password("correct-password"),
    )
    db_session.add(user)
    await db_session.flush()

    for _ in range(auth.LOGIN_FAILURE_LIMIT):
        with pytest.raises(HTTPException) as exc:
            await auth.login(
                UserLogin(email=user.email, password="wrong-password"),
                request=_request(),
                db=db_session,
                redis=fake_redis,
            )
        assert exc.value.status_code == 401

    with pytest.raises(HTTPException) as locked:
        await auth.login(
            UserLogin(email=user.email, password="correct-password"),
            request=_request(),
            db=db_session,
            redis=fake_redis,
        )

    assert locked.value.status_code == 429
    assert fake_redis.values[f"lock:login:{user.email}"] == "1"


@pytest.mark.asyncio
async def test_successful_login_clears_failure_counter(db_session, fake_redis):
    user = User(
        username="bob",
        email="bob@example.com",
        password_hash=hash_password("correct-password"),
    )
    db_session.add(user)
    await db_session.flush()
    await fake_redis.incr(f"fail:login:{user.email}")
    await fake_redis.expire(f"fail:login:{user.email}", 900)

    response = await auth.login(
        UserLogin(email=user.email, password="correct-password"),
        request=_request(),
        db=db_session,
        redis=fake_redis,
    )

    assert response["code"] == 200
    assert f"fail:login:{user.email}" not in fake_redis.values
