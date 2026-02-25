from __future__ import annotations
from dataclasses import dataclass
from typing import Protocol, Optional

@dataclass
class VideoMetadata:
    url: str
    title: str | None = None
    description: str | None = None
    duration_seconds: int | None = None
    language: str | None = None
    resolution: str | None = None
    ext: str | None = None
    platform: str | None = None

class BaseVideoScraper(Protocol):
    async def fetch_metadata(self, url: str) -> VideoMetadata:
        ...