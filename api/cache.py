from __future__ import annotations

import os

import redis.asyncio as aioredis

_redis: aioredis.Redis | None = None


def get_redis() -> aioredis.Redis:
    """Return the process-wide Redis client, creating it on first use."""
    global _redis
    if _redis is None:
        _redis = aioredis.from_url(os.getenv("REDIS_URL", "redis://redis:6379/0"), decode_responses=True)
    return _redis


async def close_redis() -> None:
    """Close the shared Redis client and reset the singleton (used on shutdown)."""
    global _redis
    if _redis is not None:
        await _redis.aclose()
        _redis = None

