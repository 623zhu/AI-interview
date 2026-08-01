"""密码哈希、密码验证和 JWT Token 工具。"""

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

import bcrypt
from jose import JWTError, jwt

from app.core.config import settings


_BCRYPT_ROUNDS = 12
_TOKEN_TYPES = {"access", "refresh"}
_REQUIRED_TOKEN_CLAIMS = {"sub", "type", "jti", "iat", "exp"}


def _password_bytes(password: str) -> bytes:
    """将密码转换为 bcrypt 可处理的字节，并执行最终安全检查。"""

    encoded = password.encode("utf-8")

    # bcrypt 最多安全处理 72 字节，不能只按照 Python 字符数判断。
    if len(encoded) > 72:
        raise ValueError("密码的 UTF-8 长度不能超过 72 字节")

    return encoded


def _hash_password(password: str) -> str:
    """在线程中执行的同步密码哈希函数。"""

    password_bytes = _password_bytes(password)
    salt = bcrypt.gensalt(rounds=_BCRYPT_ROUNDS)

    return bcrypt.hashpw(password_bytes, salt).decode("utf-8")


def _verify_password(password: str, password_hash: str) -> bool:
    """在线程中执行的同步密码校验函数。"""

    try:
        return bcrypt.checkpw(
            _password_bytes(password),
            password_hash.encode("utf-8"),
        )
    except (TypeError, ValueError):
        # 无效哈希或超长密码统一视为验证失败，不能向外泄漏内部异常。
        return False


# 用户不存在时仍执行一次 bcrypt，降低通过响应时间枚举邮箱的风险。
_DUMMY_HASH = bcrypt.hashpw(
    b"not-a-real-password",
    bcrypt.gensalt(rounds=_BCRYPT_ROUNDS),
).decode("utf-8")


async def hash_password(password: str) -> str:
    """异步生成密码哈希，避免 CPU 密集计算阻塞事件循环。"""

    return await asyncio.to_thread(_hash_password, password)


async def verify_password(
    password: str,
    password_hash: str | None,
) -> bool:
    """验证密码；用户不存在时也保持接近真实验证的耗时。"""

    target_hash = password_hash or _DUMMY_HASH

    valid = await asyncio.to_thread(
        _verify_password,
        password,
        target_hash,
    )

    # 即使密码碰巧通过占位哈希，也不能让不存在的用户登录成功。
    return bool(password_hash) and valid


def _create_token(
    subject: str,
    token_type: str,
    expires_delta: timedelta,
) -> str:
    """创建包含完整标准声明的 JWT。"""

    if token_type not in _TOKEN_TYPES:
        raise ValueError(f"不支持的 Token 类型: {token_type}")

    now = datetime.now(timezone.utc)

    payload = {
        # sub 保存用户 ID，不能放密码、邮箱等敏感信息。
        "sub": str(subject),
        "type": token_type,
        # 每个 Token 都有独立 JTI，用于 Redis 撤销和轮换。
        "jti": str(uuid4()),
        "iat": now,
        "exp": now + expires_delta,
    }

    return jwt.encode(
        payload,
        settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
    )


def create_access_token(subject: str) -> str:
    """创建短期 Access Token。"""

    return _create_token(
        subject=subject,
        token_type="access",
        expires_delta=timedelta(
            minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES,
        ),
    )


def create_refresh_token(subject: str) -> str:
    """创建长期 Refresh Token。"""

    return _create_token(
        subject=subject,
        token_type="refresh",
        expires_delta=timedelta(
            days=settings.REFRESH_TOKEN_EXPIRE_DAYS,
        ),
    )


def decode_token(token: str) -> dict[str, Any]:
    """验证 JWT 签名和过期时间，并返回载荷。"""

    payload = jwt.decode(
        token,
        settings.JWT_SECRET_KEY,
        algorithms=[settings.JWT_ALGORITHM],
    )

    # 防止签名有效但缺少业务必需声明的 Token 进入后续流程。
    missing_claims = _REQUIRED_TOKEN_CLAIMS.difference(payload)
    if missing_claims:
        raise JWTError("Token 缺少必要声明")

    if payload.get("type") not in _TOKEN_TYPES:
        raise JWTError("Token 类型无效")

    return payload


def remaining_ttl(payload: dict[str, Any]) -> int:
    """计算 Token 距离过期还剩多少秒，供 Redis 黑名单使用。"""

    expires_at = payload.get("exp")
    if not isinstance(expires_at, (int, float)):
        raise JWTError("Token 过期时间无效")

    now = int(datetime.now(timezone.utc).timestamp())
    return max(int(expires_at) - now, 1)
