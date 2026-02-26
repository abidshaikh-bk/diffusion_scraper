from __future__ import annotations

import asyncio
import json

from app.core.utils import seconds_to_hhmmss
from app.models.video_metadata import VideoMetadata


def _platform_from_info(info: dict) -> str:
    key = (info.get("extractor_key") or info.get("extractor") or "").lower()
    if "youtube" in key:
        return "YouTube"
    if "vimeo" in key:
        return "Vimeo"
    if "dailymotion" in key:
        return "Dailymotion"
    return (info.get("extractor_key") or info.get("extractor") or "Unknown")


def _quality_from_info(info: dict) -> str:
    if info.get("resolution"):
        return str(info["resolution"])
    h = info.get("height")
    if isinstance(h, int):
        return f"{h}p"
    return ""


async def fetch_metadata(url: str) -> VideoMetadata:
    cmd = [
        "yt-dlp",
        "--dump-single-json",
        "--no-warnings",
        "--skip-download",
        url,
    ]


    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    out, err = await proc.communicate()

    if proc.returncode != 0:
        raise RuntimeError(f"yt-dlp failed: {err.decode(errors='ignore')[:400]}")

    info = json.loads(out.decode("utf-8", errors="ignore"))
    duration_sec = info.get("duration") if isinstance(info.get("duration"), int) else None

    categories = info.get("categories") or []
    tags = info.get("tags") or []
    
    return VideoMetadata(
        url=url,
        title=info.get("title") or "",
        description=info.get("description") or "",
        language=info.get("language") or "",
        video_type=info.get("ext") or "",
        quality=_quality_from_info(info),
        duration=seconds_to_hhmmss(duration_sec),
        platform=_platform_from_info(info),

        uploader=info.get("uploader") or "",
        channel=info.get("channel") or info.get("uploader") or "",
        categories=[str(x) for x in categories if x],
        tags=[str(x) for x in tags if x],
    )