"""Refresh Token 状态、轮换和 Access Token 黑名单管理。"""

from typing import Any

from jose import JWTError
from redis.asyncio import Redis

from app.core.security import decode_token, remaining_ttl


_REFRESH_PREFIX = "aiiv2:auth:refresh:"
_USER_REFRESH_PREFIX = "aiiv2:auth:user_refresh:"
_ACCESS_BLOCKLIST_PREFIX = "aiiv2:auth:access_blocklist:"


# 原子校验旧 Refresh JTI、删除旧状态并写入新状态。
# Redis 单线程执行 Lua，因此并发刷新只有一个请求能成功。
_ROTATE_SCRIPT = """
if redis.call('GET', KEYS[1]) ~= ARGV[1] then
    return 0
end

redis.call('DEL', KEYS[1])
redis.call('SREM', KEYS[2], ARGV[2])

redis.call('SETEX', KEYS[3], ARGV[4], ARGV[1])
redis.call('SADD', KEYS[2], ARGV[3])
redis.call('EXPIRE', KEYS[2], ARGV[4])

return 1
"""


# 原子读取用户的全部 Refresh JTI，并删除对应状态。
_REVOKE_ALL_SCRIPT = """
local jtis = redis.call('SMEMBERS', KEYS[1])

for _, jti in ipairs(jtis) do
    redis.call('DEL', ARGV[1] .. jti)
end

redis.call('DEL', KEYS[1])
return #jtis
"""


def _refresh_key(jti: str) -> str:
    return f"{_REFRESH_PREFIX}{jti}"


def _user_refresh_key(user_id: str) -> str:
    return f"{_USER_REFRESH_PREFIX}{user_id}"


def _access_blocklist_key(jti: str) -> str:
    return f"{_ACCESS_BLOCKLIST_PREFIX}{jti}"


def _validate_token(
    token: str,
    *,
    expected_type: str,
    expected_user_id: str | None = None,
) -> tuple[dict[str, Any], str, str]:
    """验证 Token 类型、用户 ID 和 JTI，并返回解析结果。"""

    payload = decode_token(token)
    token_type = str(payload.get("type") or "")
    user_id = str(payload.get("sub") or "")
    jti = str(payload.get("jti") or "")

    if token_type != expected_type:
        raise JWTError(f"需要 {expected_type} Token")

    if not user_id or not jti:
        raise JWTError("Token 缺少用户 ID 或 JTI")

    if expected_user_id is not None and user_id != str(expected_user_id):
        # 防止调用方把甲用户的 Token 存入乙用户的 Redis 集合。
        raise JWTError("Token 用户 ID 不匹配")

    return payload, user_id, jti


async def store_refresh_token(
    redis: Redis,
    user_id: str,
    token: str,
) -> None:
    """保存登录成功后签发的 Refresh Token JTI。"""

    payload, _, jti = _validate_token(
        token,
        expected_type="refresh",
        expected_user_id=user_id,
    )
    ttl = remaining_ttl(payload)
    user_key = _user_refresh_key(user_id)

    # Redis 只保存 JTI 和用户 ID，不保存完整 JWT。
    async with redis.pipeline(transaction=True) as pipeline:
        pipeline.setex(
            _refresh_key(jti),
            ttl,
            str(user_id),
        )
        pipeline.sadd(user_key, jti)
        pipeline.expire(user_key, ttl)
        await pipeline.execute()


async def rotate_refresh_token(
    redis: Redis,
    *,
    user_id: str,
    old_jti: str,
    new_token: str,
) -> bool:
    """原子撤销旧 Refresh JTI，并登记新 Refresh JTI。"""

    new_payload, _, new_jti = _validate_token(
        new_token,
        expected_type="refresh",
        expected_user_id=user_id,
    )

    if new_jti == old_jti:
        raise JWTError("新旧 Refresh Token 的 JTI 不能相同")

    ttl = remaining_ttl(new_payload)

    result = await redis.eval(
        _ROTATE_SCRIPT,
        3,
        _refresh_key(old_jti),
        _user_refresh_key(user_id),
        _refresh_key(new_jti),
        str(user_id),
        old_jti,
        new_jti,
        ttl,
    )

    return int(result) == 1


async def revoke_user_refresh_tokens(
    redis: Redis,
    user_id: str,
) -> int:
    """撤销一个用户当前登记的全部 Refresh Token。"""

    result = await redis.eval(
        _REVOKE_ALL_SCRIPT,
        1,
        _user_refresh_key(user_id),
        _REFRESH_PREFIX,
    )

    return int(result)


async def block_access_token(
    redis: Redis,
    token: str,
) -> None:
    """将登出的 Access Token 加入黑名单直到它自然过期。"""

    payload, _, jti = _validate_token(
        token,
        expected_type="access",
    )

    await redis.setex(
        _access_blocklist_key(jti),
        remaining_ttl(payload),
        "1",
    )


async def is_access_token_blocked(
    redis: Redis,
    jti: str,
) -> bool:
    """检查 Access JTI 是否已因登出而进入黑名单。"""

    if not jti:
        return True

    return bool(
        await redis.exists(
            _access_blocklist_key(jti),
        )
    )
