from __future__ import annotations

import asyncio
import inspect
import random
from typing import Awaitable, Callable, Optional, TypeVar

from app.core.human_sleep import sleep_async  # ✅ you created this

T = TypeVar("T")

NON_RETRY_PATTERNS = (
    "sign in to confirm youre not a bot",
    "sign in to confirm you're not a bot",
    "--cookies-from-browser",
    "--cookies for the authentication",
    "this video is unavailable",
    "private video",
    # NOTE: keep EJS as non-retryable at *outer* retry level
    # because fetch_metadata will do internal fallbacks first.
    "yt_n_challenge_needs_ejs",
    "n challenge solving failed",
    "only images are available",
)

# These are usually *transient* -> retryable (often resolves with delay).
RETRYABLE_PATTERNS = (
    "http error 429",
    "too many requests",
    "rate-limited by youtube",
    "this content isn't available, try again later",
)

NETWORKISH_PATTERNS = (
    "name or service not known",
    "temporary failure in name resolution",
    "network is unreachable",
    "connection reset",
    "connection aborted",
    "timed out",
    "timeout",
    "dns",
    "connection refused",
    "tls",
    "ssl",
    "remote end closed connection",
)


def _msg(exc: Exception) -> str:
    return str(exc).lower()


def is_non_retryable(exc: Exception) -> bool:
    msg = _msg(exc)
    return any(s in msg for s in NON_RETRY_PATTERNS)


def is_retryable_transient(exc: Exception) -> bool:
    msg = _msg(exc)
    return any(s in msg for s in RETRYABLE_PATTERNS)


def is_networkish(exc: Exception) -> bool:
    msg = _msg(exc)
    return any(s in msg for s in NETWORKISH_PATTERNS)


async def retry_with_backoff(
    operation: Callable[[], Awaitable[T] | T],
    *,
    logger,
    operation_name: str = "operation",
    retries: Optional[int] = 5,          # None = infinite
    base_delay: float = 1.0,
    max_delay: float = 120.0,
) -> T:
    """
    Retries:
      - infinite ONLY if retries=None OR network-ish errors happen (keeps trying)
      - non-retryable errors raise immediately
      - includes human-ish waiting so cadence isn't bot-like
    """
    attempt = 0
    while True:
        try:
            result = operation()
            if inspect.isawaitable(result):
                result = await result
            return result

        except Exception as e:
            attempt += 1

            if is_non_retryable(e):
                logger.exception(f"{operation_name} failed (non-retryable)")
                raise

            # Decide whether we should stop (finite mode)
            if retries is not None and attempt >= retries and not is_networkish(e):
                logger.exception(f"{operation_name} failed (attempt {attempt}/{retries})")
                raise

            # Backoff: longer for rate-limit, infinite for network-ish
            delay = base_delay * (2 ** min(attempt - 1, 6))
            delay = min(delay, max_delay)

            # If 429/rate-limit, stretch delays more
            if is_retryable_transient(e):
                delay = min(max_delay, delay * 2.5)

            # Jitter
            delay = delay * random.uniform(0.85, 1.25)

            if is_networkish(e):
                logger.warning(
                    f"{operation_name} hit network issue — waiting for internet... "
                    f"(attempt {attempt}{'' if retries is None else f'/{retries}'})"
                )
            else:
                logger.warning(
                    f"{operation_name} failed — retrying in {delay:.1f}s "
                    f"(attempt {attempt}{'' if retries is None else f'/{retries}'}) — {type(e).__name__}"
                )

            # ✅ human-ish sleep (instead of robotic fixed sleep)
            # We still respect computed delay, but make it feel natural.
            # extra=delay ensures we actually wait at least that long.
            await sleep_async(base=0.6, extra=delay)