from types import SimpleNamespace

import pytest
from fastapi.security import HTTPAuthorizationCredentials

from app.api.v1 import auth
from app.core.security import create_access_token, get_token_jti, hash_password
from app.models.user import User
from app.schemas.auth import RefreshRequest, UserLogin


def _request(ip: str = "127.0.0.1"):
    return SimpleNamespace(headers={}, client=SimpleNamespace(host=ip))


async def _create_user(db_session, username: str, email: str) -> User:
    user = User(
        username=username,
        email=email,
        password_hash=hash_password("correct-password"),
    )
    db_session.add(user)
    await db_session.flush()
    return user


@pytest.mark.asyncio
async def test_login_indexes_refresh_token_by_user(db_session, fake_redis):
    user = await _create_user(db_session, "alice", "alice@example.com")

    response = await auth.login(
        UserLogin(email=user.email, password="correct-password"),
        request=_request(),
        db=db_session,
        redis=fake_redis,
    )

    refresh_token = response["data"]["tokens"]["refresh_token"]
    jti = get_token_jti(refresh_token)

    assert fake_redis.values[auth._refresh_token_key(jti)] == user.id
    assert jti in fake_redis.sets[auth._user_refresh_tokens_key(user.id)]


@pytest.mark.asyncio
async def test_refresh_rotates_token_without_leaving_stale_user_index(db_session, fake_redis):
    user = await _create_user(db_session, "bob", "bob@example.com")
    login_response = await auth.login(
        UserLogin(email=user.email, password="correct-password"),
        request=_request(),
        db=db_session,
        redis=fake_redis,
    )
    old_refresh = login_response["data"]["tokens"]["refresh_token"]
    old_jti = get_token_jti(old_refresh)

    refresh_response = await auth.refresh_token(
        RefreshRequest(refresh_token=old_refresh),
        db=db_session,
        redis=fake_redis,
    )
    new_refresh = refresh_response["data"]["refresh_token"]
    new_jti = get_token_jti(new_refresh)
    user_index_key = auth._user_refresh_tokens_key(user.id)

    assert auth._refresh_token_key(old_jti) not in fake_redis.values
    assert old_jti not in fake_redis.sets[user_index_key]
    assert fake_redis.values[auth._refresh_token_key(new_jti)] == user.id
    assert new_jti in fake_redis.sets[user_index_key]


@pytest.mark.asyncio
async def test_logout_revokes_only_current_users_indexed_refresh_tokens(db_session, fake_redis):
    current_user = await _create_user(db_session, "carol", "carol@example.com")
    other_user = await _create_user(db_session, "dave", "dave@example.com")

    current_login = await auth.login(
        UserLogin(email=current_user.email, password="correct-password"),
        request=_request(),
        db=db_session,
        redis=fake_redis,
    )
    other_login = await auth.login(
        UserLogin(email=other_user.email, password="correct-password"),
        request=_request("127.0.0.2"),
        db=db_session,
        redis=fake_redis,
    )

    current_jti = get_token_jti(current_login["data"]["tokens"]["refresh_token"])
    other_jti = get_token_jti(other_login["data"]["tokens"]["refresh_token"])
    access_token = create_access_token(current_user.id)

    response = await auth.logout(
        current_user=current_user,
        credentials=HTTPAuthorizationCredentials(scheme="Bearer", credentials=access_token),
        redis=fake_redis,
    )

    assert response["code"] == 200
    assert auth._refresh_token_key(current_jti) not in fake_redis.values
    assert auth._user_refresh_tokens_key(current_user.id) not in fake_redis.sets
    assert fake_redis.values[auth._refresh_token_key(other_jti)] == other_user.id
    assert other_jti in fake_redis.sets[auth._user_refresh_tokens_key(other_user.id)]
