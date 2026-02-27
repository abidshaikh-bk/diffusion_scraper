from __future__ import annotations
import asyncio
import random
from typing import Callable, TypeVar, Awaitable

T = TypeVar("T")

async def retry_with_backoff(
    fn: Callable[[], Awaitable[T]],
    *,
    attempts: int = 6,
    base_delay_sec: float = 2.0,
    max_delay_sec: float = 30.0,
) -> T:
    """
    Retries async fn with exponential backoff + jitter.
    """
    last_exc: Exception | None = None
    for i in range(attempts):
        try:
            return await fn()
        except Exception as e:
            last_exc = e
            delay = min(max_delay_sec, base_delay_sec * (2 ** i))
            delay = delay + random.random() * 0.5 * delay  # jitter
            await asyncio.sleep(delay)
    raise last_exc  # type: ignore