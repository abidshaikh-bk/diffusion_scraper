from __future__ import annotations

from dataclasses import dataclass
from typing import List
from urllib.parse import urlparse
import yaml


@dataclass(frozen=True)
class Platform:
    name: str
    domains: tuple[str, ...]

    def matches(self, url: str) -> bool:
        try:
            host = (urlparse(url).netloc or "").lower()
            return host in {d.lower() for d in self.domains}
        except Exception:
            return False


class PlatformRegistry:
    def __init__(self, platforms: List[Platform]):
        self.platforms = platforms

    @staticmethod
    def from_yaml(path: str = "configs/platforms.yaml") -> "PlatformRegistry":
        data = yaml.safe_load(open(path, "r", encoding="utf-8")) or {}
        plats = [
            Platform(name=p["name"], domains=tuple(p.get("domains", [])))
            for p in data.get("platforms", [])
        ]
        return PlatformRegistry(plats)

    def is_allowed(self, url: str) -> bool:
        return any(p.matches(url) for p in self.platforms)

    def platform_for(self, url: str) -> str | None:
        for p in self.platforms:
            if p.matches(url):
                return p.name
        return None