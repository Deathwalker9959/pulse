from __future__ import annotations

import functools
import hashlib
import json
from collections.abc import Awaitable, Callable
from datetime import date, datetime
from typing import Any, ParamSpec, TypeVar

P = ParamSpec("P")
T = TypeVar("T")


def _json_default(value: Any) -> str:
    """JSON fallback serializer: render datetimes/dates as ISO strings, everything else via str()."""
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return str(value)


def cached(ttl: int, key_prefix: str) -> Callable[[Callable[P, Awaitable[T]]], Callable[P, Awaitable[T]]]:
    """Decorator factory: cache an async function's JSON result in Redis under a hashed key for `ttl` seconds.

    The wrapped function must receive `redis` as a keyword arg; without it the call runs uncached.
    """
    def decorate(fn: Callable[P, Awaitable[T]]) -> Callable[P, Awaitable[T]]:
        """Wrap a single async function with the Redis read-through cache."""
        @functools.wraps(fn)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            """Return the cached value if present, otherwise call `fn` and store its result."""
            redis = kwargs.get("redis")
            if redis is None:
                return await fn(*args, **kwargs)
            payload = json.dumps({"args": args, "kwargs": {k: v for k, v in kwargs.items() if k != "redis"}}, default=_json_default, sort_keys=True)
            digest = hashlib.sha256(payload.encode()).hexdigest()[:20]
            key = f"pulse:v1:{key_prefix}:{digest}"
            value = await redis.get(key)
            if value:
                return json.loads(value)
            result = await fn(*args, **kwargs)
            await redis.setex(key, ttl, json.dumps(result, default=_json_default))
            return result

        return wrapper

    return decorate

