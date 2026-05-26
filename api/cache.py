"""Redis async client + helper — singleton, used by both @cached decorator and WebSocket consumer."""
from __future__ import annotations

import os

import redis.asyncio as aioredis

_redis: aioredis.Redis | None = None


def get_redis() -> aioredis.Redis:
    global _redis
    if _redis is None:
        _redis = aioredis.from_url(
            os.getenv("REDIS_URL", "redis://redis:6379/0"),
            decode_responses=False,
        )
    return _redis
