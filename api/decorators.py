"""
Curated async decorators for the API service.
"""
from __future__ import annotations

import hashlib
import json
import logging
import time
from collections.abc import Awaitable, Callable
from functools import wraps
from typing import Any, ParamSpec, TypeVar

P = ParamSpec("P")
R = TypeVar("R")

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# cached
# ---------------------------------------------------------------------------

def cached(
    *,
    ttl: int,
    key_prefix: str,
) -> Callable[[Callable[P, Awaitable[R]]], Callable[P, Awaitable[R]]]:
    """Cache the return value of an async controller method in Redis.

    Cache key: ``pulse:v1:{key_prefix}:{sha256(canonical_json(kwargs))}``.
    A ``redis`` keyword argument (``redis.asyncio.Redis``) must be supplied
    at call-time; if absent the cache is bypassed (no error).

    Return value must be JSON-serialisable (Pydantic models use
    ``model_dump()``).

    SCALE: TTL chosen per endpoint volatility. For 10x query volume add
    a local in-process LRU (e.g. cachetools) as L1 before Redis L2.

    Args:
        ttl: Cache lifetime in seconds.
        key_prefix: Human-readable namespace included in the key.

    Example::

        @cached(ttl=30, key_prefix="flights:live")
        async def get_live(redis: Redis, ch: AsyncClient) -> list[FlightLive]: ...
    """
    def decorator(func: Callable[P, Awaitable[R]]) -> Callable[P, Awaitable[R]]:
        @wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            redis = kwargs.get("redis")  # type: ignore[call-overload]
            if redis is None:
                return await func(*args, **kwargs)

            # Stable key from sorted kwargs (exclude redis itself).
            cache_kwargs = {k: v for k, v in kwargs.items() if k != "redis"}  # type: ignore[union-attr]
            raw = json.dumps(cache_kwargs, sort_keys=True, default=str)
            digest = hashlib.sha256(raw.encode()).hexdigest()[:16]
            key = f"pulse:v1:{key_prefix}:{digest}"

            cached_val = await redis.get(key)
            if cached_val is not None:
                return json.loads(cached_val)  # type: ignore[return-value]

            result = await func(*args, **kwargs)

            try:
                serialised = json.dumps(result, default=_json_default)
                await redis.setex(key, ttl, serialised)
            except (TypeError, ValueError) as exc:
                logger.warning("cache serialisation failed for %s: %s", key, exc)

            return result

        return wrapper

    return decorator


def _json_default(obj: Any) -> Any:
    if hasattr(obj, "model_dump"):
        return obj.model_dump()
    if hasattr(obj, "isoformat"):
        return obj.isoformat()
    raise TypeError(f"not serialisable: {type(obj)}")


# ---------------------------------------------------------------------------
# validate_bbox
# ---------------------------------------------------------------------------

def validate_bbox(func: Callable[P, Awaitable[R]]) -> Callable[P, Awaitable[R]]:
    """Validate a ``bbox`` keyword argument before calling the controller.

    Raises ``ValueError`` when the bbox string is malformed or out of range.
    Views translate this to HTTP 422.

    Example::

        @validate_bbox
        async def get_density(bbox: str, ...) -> list[DensityCell]: ...
    """
    @wraps(func)
    async def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        bbox: str | None = kwargs.get("bbox")  # type: ignore[assignment]
        if bbox is not None:
            parts = bbox.split(",")
            if len(parts) != 4:
                raise ValueError("bbox must have 4 comma-separated floats")
            try:
                lon_min, lat_min, lon_max, lat_max = map(float, parts)
            except ValueError:
                raise ValueError("bbox values must be numeric")
            if not (-180 <= lon_min < lon_max <= 180):
                raise ValueError(f"invalid longitude range: {lon_min} {lon_max}")
            if not (-90 <= lat_min < lat_max <= 90):
                raise ValueError(f"invalid latitude range: {lat_min} {lat_max}")
        return await func(*args, **kwargs)

    return wrapper


# ---------------------------------------------------------------------------
# timed  (same contract as ingestion version, duplicated to keep services independent)
# ---------------------------------------------------------------------------

def timed(
    *,
    threshold_ms: float = 500.0,
) -> Callable[[Callable[P, Awaitable[R]]], Callable[P, Awaitable[R]]]:
    """Log execution time of an async API controller method.

    Args:
        threshold_ms: Emit WARNING (vs DEBUG) when duration exceeds this.
    """
    def decorator(func: Callable[P, Awaitable[R]]) -> Callable[P, Awaitable[R]]:
        _logger = logging.getLogger(func.__module__)

        @wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            t0 = time.perf_counter()
            try:
                return await func(*args, **kwargs)
            finally:
                ms = (time.perf_counter() - t0) * 1_000
                level = logging.WARNING if ms > threshold_ms else logging.DEBUG
                _logger.log(level, "%s took %.1fms", func.__qualname__, ms)

        return wrapper

    return decorator
