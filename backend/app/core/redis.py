"""异步 Redis 客户端生命周期管理"""
from redis.asyncio import Redis          # Redis 官方库的异步版本
from app.core.config import settings     # 复用配置单例

_redis_client: Redis | None = None       # 全局客户端,初始为 None  _ 是 Python 约定,表示"私有,别从外部直接访问"

async def get_redis() -> Redis:
    """Return the shared asynchronous Redis client."""

    global _redis_client

    if _redis_client is None:
        _redis_client = Redis.from_url(
            settings.REDIS_URL,
            encoding="utf-8",
            decode_responses=True,
            socket_connect_timeout=5.0,
            socket_timeout=5.0,
            health_check_interval=30,
        )

    return _redis_client


async def close_redis() -> None:
    """Close the Redis client and its connection pool."""

    global _redis_client

    if _redis_client is not None:
        await _redis_client.aclose()
        _redis_client = None
