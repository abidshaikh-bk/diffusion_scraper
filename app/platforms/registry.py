from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional
from urllib.parse import urlparse
import yaml


@dataclass(frozen=True)
class Platform:
    name: str
    domains: tuple[str, ...]

    def matches(self, url: str) -> bool:
        """
        Match host exactly OR as a subdomain:
          - youtube.com matches m.youtube.com, www.youtube.com, etc.
        """
        try:
            host = (urlparse(url).netloc or "").lower()
            if not host:
                return False
            for d in self.domains:
                dd = (d or "").lower().strip()
                if not dd:
                    continue
                if host == dd or host.endswith("." + dd):
                    return True
            return False
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

    def platform_for(self, url: str) -> Optional[str]:
        for p in self.platforms:
            if p.matches(url):
                return p.name
        return None

    def platform_key_for(self, url: str) -> str:
        """
        Returns a normalized key used for rotation/cooldowns.
        """
        name = (self.platform_for(url) or "").strip().lower()
        if "youtube" in name:
            return "youtube"
        if "vimeo" in name:
            return "vimeo"
        if "dailymotion" in name:
            return "dailymotion"
        if name:
            return name.replace(" ", "_")
        return "unknown"