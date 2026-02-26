from __future__ import annotations
from dataclasses import dataclass

@dataclass
class VideoMetadata:
    url: str
    title: str = ""
    description: str = ""
    language: str = ""
    video_type: str = ""
    quality: str = ""
    duration: str = ""        # hh:mm:ss
    platform: str = ""

    # NEW (for relevancy)
    uploader: str = ""
    channel: str = ""
    categories: list[str] = None
    tags: list[str] = None