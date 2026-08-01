"""基于 Redis 的固定窗口限流和登录锁定工具。"""

from dataclasses import dataclass

from fastapi import HTTPException, Request
from redis.asyncio import Redis


# 通过 Lua 脚本保证 INCR、EXPIRE 和 TTL 在 Redis 内一次性执行。
# 如果拆成多个 Python 命令，并发或进程中断时可能产生永不过期的计数器。
_INCREMENT_WITH_TTL_SCRIPT = """
local current = redis.call('INCR', KEYS[1])

if current == 1 then
    redis.call('EXPIRE', KEYS[1], ARGV[1])
end

local ttl = redis.call('TTL', KEYS[1])

if ttl < 0 then
    redis.call('EXPIRE', KEYS[1], ARGV[1])
    ttl = tonumber(ARGV[1])
end

return {current, ttl}
"""


@dataclass(frozen=True)
class RateLimit:
    """一条固定窗口限流规则。"""

    limit: int
    window_seconds: int
    message: str = "请求过于频繁，请稍后再试"

    def __post_init__(self) -> None:
        # 配置错误应在开发阶段立即暴露，不能生成永久 Key。
        if self.limit <= 0:
            raise ValueError("限流次数必须大于 0")

        if self.window_seconds <= 0:
            raise ValueError("限流窗口必须大于 0 秒")


def client_ip(request: Request) -> str:
    """取得与应用建立连接的客户端地址。"""

    # 当前不直接信任 X-Forwarded-For，避免客户端伪造 Header 绕过限流。
    # 正式部署反向代理后，应在可信代理层统一处理真实客户端 IP。
    if request.client is None:
        return "unknown"

    return request.client.host


async def increment_with_ttl(
    redis: Redis,
    key: str,
    window_seconds: int,
) -> tuple[int, int]:
    """原子增加计数，并返回当前次数和剩余有效秒数。"""

    if window_seconds <= 0:
        raise ValueError("限流窗口必须大于 0 秒")

    result = await redis.eval(
        _INCREMENT_WITH_TTL_SCRIPT,
        1,
        key,
        window_seconds,
    )

    count = int(result[0])
    ttl = max(int(result[1]), 1)

    return count, ttl


async def check_rate_limit(
    redis: Redis,
    key: str,
    rule: RateLimit,
) -> None:
    """增加请求计数，超过限制时返回 HTTP 429。"""

    count, ttl = await increment_with_ttl(
        redis,
        key,
        rule.window_seconds,
    )

    if count <= rule.limit:
        return

    raise HTTPException(
        status_code=429,
        detail={
            "code": "rate_limited",
            "message": rule.message,
        },
        # 前端可以根据该 Header 禁用按钮并显示倒计时。
        headers={"Retry-After": str(ttl)},
    )


async def ensure_not_locked(
    redis: Redis,
    key: str,
) -> None:
    """检查登录锁定 Key，存在有效 TTL 时拒绝登录。"""

    ttl = await redis.ttl(key)

    if ttl <= 0:
        return

    raise HTTPException(
        status_code=429,
        detail={
            "code": "login_locked",
            "message": "登录失败次数过多，请稍后再试",
        },
        headers={"Retry-After": str(ttl)},
    )
