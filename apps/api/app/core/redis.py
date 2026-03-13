"""
Redis client setup.

Provides a single async Redis connection pool shared across the FastAPI
application lifetime.  Imported by app.main during startup.
"""
from __future__ import annotations

from typing import Optional

import redis.asyncio as aioredis

from shared.config.settings import settings
from shared.utils.logging import get_logger

logger = get_logger(__name__)

_redis_client: Optional[aioredis.Redis] = None


async def get_redis_client() -> aioredis.Redis:
    """
    Return (and lazily create) the application-wide Redis connection pool.

    Called once during FastAPI lifespan startup; the returned client is stored
    on ``app.state.redis`` and reused for the entire server lifetime.
    """
    global _redis_client
    if _redis_client is None:
        _redis_client = aioredis.from_url(
            settings.redis_url,
            encoding="utf-8",
            decode_responses=True,
            socket_connect_timeout=5,
            socket_timeout=5,
            retry_on_timeout=True,
            health_check_interval=30,
        )
        # Verify the connection is reachable at startup
        try:
            await _redis_client.ping()
            logger.info("Redis connection established", url=settings.redis_url)
        except Exception as exc:  # pragma: no cover
            logger.warning(
                "Redis not reachable at startup — caching disabled",
                url=settings.redis_url,
                error=str(exc),
            )
    return _redis_client


async def get_redis_dep() -> aioredis.Redis:
    """
    FastAPI dependency that yields the Redis client.

    Usage::

        @router.get("/cached")
        async def cached_endpoint(redis: Redis = Depends(get_redis_dep)):
            value = await redis.get("my-key")
    """
    return await get_redis_client()
