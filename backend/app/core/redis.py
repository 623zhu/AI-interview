"""Redis connection pool and client."""
import redis.asyncio as aioredis
from redis.asyncio import Redis
from app.core.config import settings

# Global Redis connection pool
_redis_pool: Redis | None = None


async def get_redis() -> Redis:
    """Get or create the Redis connection pool."""
    global _redis_pool
    if _redis_pool is None:
        _redis_pool = aioredis.from_url(
            settings.REDIS_URL,
            encoding="utf-8",
            decode_responses=True,
        )
    return _redis_pool


async def close_redis():
    """Close the Redis connection pool."""
    global _redis_pool
    if _redis_pool:
        await _redis_pool.close()
        _redis_pool = None
