from __future__ import annotations
import asyncio
from dataclasses import dataclass
from typing import Callable, Awaitable

@dataclass
class WorkerConfig:
    concurrency: int = 10
    batch_size: int = 25
    poll_interval_sec: int = 5

class WorkerPool:
    def __init__(self, config: WorkerConfig):
        self.config = config
        self._sem = asyncio.Semaphore(config.concurrency)

    async def run_forever(self, tick: Callable[[], Awaitable[None]]):
        while True:
            await tick()
            await asyncio.sleep(self.config.poll_interval_sec)