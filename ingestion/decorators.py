"""
Curated async decorators for the ingestion service.
Each covers exactly one cross-cutting concern; none leak into business logic.
"""
from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from functools import wraps
from typing import Any, ParamSpec, TypeVar, overload

P = ParamSpec("P")
R = TypeVar("R")


# ---------------------------------------------------------------------------
# retry
# ---------------------------------------------------------------------------

def retry(
    *,
    max_attempts: int = 5,
    backoff_base: float = 2.0,
    max_delay: float = 60.0,
    exceptions: tuple[type[BaseException], ...] = (Exception,),
) -> Callable[[Callable[P, Awaitable[R]]], Callable[P, Awaitable[R]]]:
    """Wrap an async function with exponential-backoff retry.

    Args:
        max_attempts: Total call attempts before re-raising the last exception.
        backoff_base: Delay multiplier: delay = min(base**(attempt-1), max_delay).
        max_delay: Upper bound on sleep duration in seconds.
        exceptions: Only retry on these exception types.

    Example::

        @retry(max_attempts=8, backoff_base=2.0, max_delay=60.0)
        async def fetch_data(url: str) -> dict[str, Any]: ...
    """
    def decorator(func: Callable[P, Awaitable[R]]) -> Callable[P, Awaitable[R]]:
        _logger = logging.getLogger(func.__module__)

        @wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            for attempt in range(1, max_attempts + 1):
                try:
                    return await func(*args, **kwargs)
                except exceptions as exc:
                    if attempt == max_attempts:
                        _logger.error(
                            "giving up after %d/%d attempts in %s: %s",
                            attempt, max_attempts, func.__qualname__, exc,
                        )
                        raise
                    delay = min(backoff_base ** (attempt - 1), max_delay)
                    _logger.warning(
                        "%s attempt %d/%d failed (%s), retrying in %.1fs",
                        func.__qualname__, attempt, max_attempts, exc, delay,
                    )
                    await asyncio.sleep(delay)
            # Unreachable — loop always raises or returns, but satisfies type checker.
            raise RuntimeError("retry loop exited without result")

        return wrapper

    return decorator


# ---------------------------------------------------------------------------
# rate_limit
# ---------------------------------------------------------------------------

def rate_limit(*, min_interval: float) -> Callable[[Callable[P, Awaitable[R]]], Callable[P, Awaitable[R]]]:
    """Enforce a minimum wall-clock gap (seconds) between successive invocations.

    State is per-decorated-function (closure), not per-caller.

    SCALE: In a multi-process deployment move the last-called timestamp to a
    Redis INCR+TTL to coordinate across workers rather than per-process.

    Args:
        min_interval: Minimum seconds between consecutive calls.

    Example::

        @rate_limit(min_interval=10.0)
        async def call_opensky_api() -> list[dict[str, Any]]: ...
    """
    def decorator(func: Callable[P, Awaitable[R]]) -> Callable[P, Awaitable[R]]:
        _last_called: list[float] = [0.0]  # mutable cell avoids nonlocal

        @wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            elapsed = time.monotonic() - _last_called[0]
            if elapsed < min_interval:
                await asyncio.sleep(min_interval - elapsed)
            _last_called[0] = time.monotonic()
            return await func(*args, **kwargs)

        return wrapper

    return decorator


# ---------------------------------------------------------------------------
# timed
# ---------------------------------------------------------------------------

def timed(
    *,
    logger: logging.Logger | None = None,
    threshold_ms: float = 500.0,
) -> Callable[[Callable[P, Awaitable[R]]], Callable[P, Awaitable[R]]]:
    """Log execution wall-time; emit WARNING when threshold is exceeded.

    Args:
        logger: Logger instance to use. Defaults to the function's module logger.
        threshold_ms: Emit WARNING (vs DEBUG) when duration exceeds this.

    Example::

        @timed(logger=logger, threshold_ms=2_000)
        async def write_flights(client: ..., states: list[FlightState]) -> None: ...
    """
    def decorator(func: Callable[P, Awaitable[R]]) -> Callable[P, Awaitable[R]]:
        _logger = logger or logging.getLogger(func.__module__)

        @wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            t0 = time.perf_counter()
            try:
                return await func(*args, **kwargs)
            finally:
                ms = (time.perf_counter() - t0) * 1_000
                level = logging.WARNING if ms > threshold_ms else logging.DEBUG
                _logger.log(level, "%s completed in %.1fms", func.__qualname__, ms)

        return wrapper

    return decorator


# ---------------------------------------------------------------------------
# stream_publish
# ---------------------------------------------------------------------------

def stream_publish(
    *,
    stream: str,
    maxlen: int = 50_000,
) -> Callable[[Callable[P, Awaitable[list[Any]]]], Callable[P, Awaitable[list[Any]]]]:
    """Publish each Pydantic model in the returned list to a Redis Stream.

    The decorated function must return ``list[BaseModel]``.
    A ``redis`` keyword argument (``redis.asyncio.Redis``) must be passed at
    call-time; if absent the publish step is silently skipped.

    Args:
        stream: Redis Stream key name.
        maxlen: Approximate MAXLEN for the stream (``~`` trimming).

    SCALE: MAXLEN with ``~`` (approximate) trimming trades exactness for
    throughput — ClickHouse is the durable store; the stream is transit only.

    Example::

        @stream_publish(stream="pulse:flights", maxlen=50_000)
        async def fetch_states(..., redis: Redis) -> list[FlightState]: ...
    """
    def decorator(
        func: Callable[P, Awaitable[list[Any]]],
    ) -> Callable[P, Awaitable[list[Any]]]:
        @wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> list[Any]:
            result: list[Any] = await func(*args, **kwargs)
            redis = kwargs.get("redis")  # type: ignore[call-overload]
            if redis is not None and result:
                pipe = redis.pipeline()
                for item in result:
                    payload: str = (
                        item.model_dump_json()
                        if hasattr(item, "model_dump_json")
                        else str(item)
                    )
                    pipe.xadd(stream, {"data": payload}, maxlen=maxlen, approximate=True)
                await pipe.execute()
            return result

        return wrapper

    return decorator
