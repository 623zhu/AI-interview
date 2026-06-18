from datetime import timedelta

from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    get_token_jti,
    hash_password,
    verify_password,
)


def test_password_hash_round_trip():
    password_hash = hash_password("correct horse battery staple")

    assert password_hash != "correct horse battery staple"
    assert verify_password("correct horse battery staple", password_hash)
    assert not verify_password("wrong password", password_hash)


def test_access_token_contains_required_claims():
    token = create_access_token("user-123", expires_delta=timedelta(minutes=5))
    payload = decode_token(token)

    assert payload["sub"] == "user-123"
    assert payload["type"] == "access"
    assert payload["jti"]
    assert get_token_jti(token) == payload["jti"]


def test_refresh_token_contains_required_claims():
    token = create_refresh_token("user-456")
    payload = decode_token(token)

    assert payload["sub"] == "user-456"
    assert payload["type"] == "refresh"
    assert payload["jti"]
