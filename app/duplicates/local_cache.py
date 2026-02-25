from __future__ import annotations

import time
from dataclasses import dataclass, field


@dataclass
class DedupeCache:
    ttl_sec: int = 60
    _last_refresh: float = 0.0
    _urls: set[str] = field(default_factory=set)

    def should_refresh(self) -> bool:
        return (time.time() - self._last_refresh) > self.ttl_sec

    def update(self, urls: set[str]) -> None:
        self._urls = urls
        self._last_refresh = time.time()

    def contains(self, url: str) -> bool:
        return url in self._urls