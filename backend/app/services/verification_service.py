"""注册验证码的生成、存储、发送和一次性消费。"""

import hashlib
import hmac
import secrets

from fastapi import HTTPException
from redis.asyncio import Redis

from app.core.config import settings
from app.core.rate_limit import RateLimit, check_rate_limit
from app.services.email_service import (
    EmailDeliveryError,
    send_verification_code,
)


CODE_TTL_SECONDS = 300
COOLDOWN_SECONDS = 60
MAX_ATTEMPTS = 5

SEND_IP_LIMIT = RateLimit(10, 3600, "验证码请求过于频繁")
SEND_EMAIL_LIMIT = RateLimit(5, 3600, "该邮箱验证码请求过于频繁")


# 验证码匹配时同时删除验证码和错误计数，保证只能消费一次。
_CONSUME_SCRIPT = """
if redis.call('GET', KEYS[1]) == ARGV[1] then
    redis.call('DEL', KEYS[1], KEYS[2])
    return 1
end
return 0
"""

# 错误次数达到上限后立即让验证码失效。
_FAILURE_SCRIPT = """
if redis.call('EXISTS', KEYS[1]) == 0 then
    return -1
end

local count = redis.call('INCR', KEYS[2])

if count == 1 then
    local code_ttl = redis.call('TTL', KEYS[1])
    if code_ttl > 0 then
        redis.call('EXPIRE', KEYS[2], code_ttl)
    end
end

if count >= tonumber(ARGV[1]) then
    redis.call('DEL', KEYS[1], KEYS[2])
    return -2
end

return count
"""

# 邮件发送失败时，仅清理由本次请求写入的数据。
_CONDITIONAL_DELETE_SCRIPT = """
if redis.call('GET', KEYS[1]) == ARGV[1] then
    redis.call('DEL', KEYS[1], KEYS[2], KEYS[3])
    return 1
end
return 0
"""


def _normalize_email(email: str) -> str:
    """保证 Redis Key 和 HMAC 始终使用相同邮箱格式。"""

    return email.strip().lower()


def _code_key(email: str) -> str:
    return f"aiiv2:auth:verify:register:{email}"


def _attempt_key(email: str) -> str:
    return f"aiiv2:auth:verify_attempts:register:{email}"


def _cooldown_key(email: str) -> str:
    return f"aiiv2:auth:send_cooldown:{email}"


def _digest(email: str, code: str) -> str:
    """计算验证码摘要，Redis 中不保存验证码明文。"""

    payload = f"{email}:register:{code}".encode("utf-8")
    secret = settings.VERIFICATION_HMAC_SECRET.encode("utf-8")

    return hmac.new(
        secret,
        payload,
        hashlib.sha256,
    ).hexdigest()


def _invalid_code() -> HTTPException:
    """统一错误响应，避免暴露验证码是错误还是过期。"""

    return HTTPException(
        status_code=400,
        detail={
            "code": "invalid_verification_code",
            "message": "验证码错误或已过期",
        },
    )


async def issue_registration_code(
    redis: Redis,
    *,
    email: str,
    client_ip: str,
    email_registered: bool,
) -> None:
    """签发并发送注册验证码。"""

    email = _normalize_email(email)

    # IP 和邮箱两个维度都需要满足限流规则。
    await check_rate_limit(
        redis,
        f"aiiv2:auth:rl:send:ip:{client_ip}",
        SEND_IP_LIMIT,
    )
    await check_rate_limit(
        redis,
        f"aiiv2:auth:rl:send:email:{email}",
        SEND_EMAIL_LIMIT,
    )

    if email_registered:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "email_already_registered",
                "message": "该邮箱已注册",
            },
        )

    cooldown_key = _cooldown_key(email)

    # NX 保证并发请求中只有一个能取得60秒发送资格。
    acquired = await redis.set(
        cooldown_key,
        "1",
        ex=COOLDOWN_SECONDS,
        nx=True,
    )

    if not acquired:
        ttl = max(await redis.ttl(cooldown_key), 1)
        raise HTTPException(
            status_code=429,
            detail={
                "code": "send_cooldown",
                "message": "请稍后再发送验证码",
            },
            headers={"Retry-After": str(ttl)},
        )

    code = f"{secrets.randbelow(1_000_000):06d}"
    digest = _digest(email, code)
    code_key = _code_key(email)
    attempt_key = _attempt_key(email)

    # 使用事务同时写入新验证码并清除旧的错误计数。
    async with redis.pipeline(transaction=True) as pipeline:
        pipeline.set(code_key, digest, ex=CODE_TTL_SECONDS)
        pipeline.delete(attempt_key)
        await pipeline.execute()

    try:
        await send_verification_code(email, code)
    except EmailDeliveryError as exc:
        # 发送失败后撤销本次验证码和冷却，允许用户立即重试。
        await redis.eval(
            _CONDITIONAL_DELETE_SCRIPT,
            3,
            code_key,
            attempt_key,
            cooldown_key,
            digest,
        )
        raise HTTPException(
            status_code=503,
            detail={
                "code": "email_delivery_unavailable",
                "message": "验证码发送失败，请稍后重试",
            },
        ) from exc


async def consume_registration_code(
    redis: Redis,
    *,
    email: str,
    code: str,
) -> None:
    """验证并一次性消费注册验证码。"""

    email = _normalize_email(email)
    code_key = _code_key(email)
    attempt_key = _attempt_key(email)

    stored_digest = await redis.get(code_key)
    if not stored_digest:
        raise _invalid_code()

    supplied_digest = _digest(email, code)

    # compare_digest 降低通过比较耗时推测摘要内容的风险。
    if hmac.compare_digest(stored_digest, supplied_digest):
        consumed = await redis.eval(
            _CONSUME_SCRIPT,
            2,
            code_key,
            attempt_key,
            supplied_digest,
        )

        if int(consumed) == 1:
            return

        # 并发请求中只有第一个请求能够消费成功。
        raise _invalid_code()

    await redis.eval(
        _FAILURE_SCRIPT,
        2,
        code_key,
        attempt_key,
        MAX_ATTEMPTS,
    )
    raise _invalid_code()
