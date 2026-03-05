from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, List


@dataclass
class VideoMetadata:
    url: str

    # Basic metadata
    title: str = ""
    description: str = ""
    language: str = ""
    video_type: str = ""
    quality: str = ""
    duration: str = ""
    duration_seconds: Optional[int] = None
    platform: str = ""

    # Channel / uploader
    uploader: str = ""
    uploader_id: str = ""
    uploader_url: str = ""

    channel: str = ""
    channel_id: str = ""
    channel_url: str = ""

    # Engagement
    view_count: Optional[int] = None
    like_count: Optional[int] = None
    comment_count: Optional[int] = None

    # Content descriptors
    categories: List[str] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)

    # Upload info
    upload_date: str = ""        # YYYYMMDD
    timestamp: Optional[int] = None

    # Geography
    country: str = ""

    # Video technical metadata
    width: Optional[int] = None
    height: Optional[int] = None
    fps: Optional[float] = None
    resolution: str = ""

    # Canonical page
    webpage_url: str = ""