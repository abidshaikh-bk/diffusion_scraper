import asyncio
import random
import time
from dataclasses import dataclass
from typing import Optional

@dataclass
class HumanSleepProfile:
    # micro pauses like typing / thinking
    micro_min: float = 0.25
    micro_max: float = 1.4

    # normal between actions
    short_min: float = 1.5
    short_max: float = 6.0

    # reading/scanning pages / metadata
    medium_min: float = 6.0
    medium_max: float = 18.0

    # occasional “walk away” breaks
    long_min: float = 45.0
    long_max: float = 180.0

    # chance of each pause type when called
    micro_p: float = 0.55
    short_p: float = 0.30
    medium_p: float = 0.13
    long_p: float = 0.02


def _choose_delay(p: HumanSleepProfile) -> float:
    r = random.random()
    if r < p.micro_p:
        return random.uniform(p.micro_min, p.micro_max)
    r -= p.micro_p
    if r < p.short_p:
        return random.uniform(p.short_min, p.short_max)
    r -= p.short_p
    if r < p.medium_p:
        return random.uniform(p.medium_min, p.medium_max)
    return random.uniform(p.long_min, p.long_max)


def sleep_sync(
    *,
    profile: Optional[HumanSleepProfile] = None,
    base: float = 1.0,
    jitter: float = 0.35,
    extra: float = 0.0,
) -> float:
    """
    Human-ish sleep:
    - chooses a bucket (micro/short/medium/long)
    - applies jitter so timing isn’t patterned
    Returns the actual sleep seconds used.
    """
    p = profile or HumanSleepProfile()
    delay = _choose_delay(p) * base + extra
    delay = delay * random.uniform(1.0 - jitter, 1.0 + jitter)
    delay = max(0.0, delay)
    time.sleep(delay)
    return delay


async def sleep_async(
    *,
    profile: Optional[HumanSleepProfile] = None,
    base: float = 1.0,
    jitter: float = 0.35,
    extra: float = 0.0,
) -> float:
    p = profile or HumanSleepProfile()
    delay = _choose_delay(p) * base + extra
    delay = delay * random.uniform(1.0 - jitter, 1.0 + jitter)
    delay = max(0.0, delay)
    await asyncio.sleep(delay)
    return delay