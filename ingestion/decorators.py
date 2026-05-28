from __future__ import annotations

import asyncio
import functools
import logging
from collections.abc import Awaitable, Callable
from typing import ParamSpec, TypeVar

P = ParamSpec("P")
T = TypeVar("T")


def retry(
    *,
    max_attempts: int = 3,
    backoff_base: float = 1.5,
    max_delay: float = 30.0,
    exceptions: tuple[type[BaseException], ...] = (Exception,),
) -> Callable[[Callable[P, Awaitable[T]]], Callable[P, Awaitable[T]]]:
    def decorate(fn: Callable[P, Awaitable[T]]) -> Callable[P, Awaitable[T]]:
        @functools.wraps(fn)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            delay = 1.0
            for attempt in range(1, max_attempts + 1):
                try:
                    return await fn(*args, **kwargs)
                except exceptions:
                    if attempt == max_attempts:
                        raise
                    logging.getLogger(fn.__module__).warning(
                        "%s failed on attempt %d/%d; retrying in %.1fs",
                        fn.__name__,
                        attempt,
                        max_attempts,
                        delay,
                    )
                    await asyncio.sleep(delay)
                    delay = min(delay * backoff_base, max_delay)
            raise RuntimeError("unreachable")

        return wrapper

    return decorate

