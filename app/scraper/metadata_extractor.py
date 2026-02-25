from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from typing import Any, Dict, Optional

from app.core.utils import seconds_to_hhmmss


@dataclass
class ExtractedMetadata:
    title: str | None
    language: str | None
    ext: str | None
    quality: str | None
    duration_hhmmss: str | None
    platform: str | None


def _platform_from_info(info: Dict[str, Any]) -> str | None:
    # yt-dlp typically provides extractor / extractor_key (e.g., "youtube", "vimeo")
    extractor_key = (info.get("extractor_key") or info.get("extractor") or "").strip()
    if not extractor_key:
        return None
    # normalize to nice names
    key = extractor_key.lower()
    if "youtube" in key:
        return "YouTube"
    if "vimeo" in key:
        return "Vimeo"
    return extractor_key  # fallback


async def extract_metadata(url: str) -> ExtractedMetadata:
    """
    Async wrapper around yt-dlp JSON dump.
    Uses subprocess so it won't block the event loop.
    """
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
        raise RuntimeError(f"yt-dlp failed: {err.decode(errors='ignore')[:500]}")

    info = json.loads(out.decode("utf-8", errors="ignore"))

    title = info.get("title")
    ext = info.get("ext")
    duration_sec = info.get("duration")
    lang = info.get("language") or info.get("lang")  # depends on extractor
    platform = _platform_from_info(info)

    # Quality: pick best available fields; can refine later
    # (yt-dlp may include "resolution", "height", "width", "format", etc.)
    quality = info.get("resolution")
    if not quality:
        h = info.get("height")
        if isinstance(h, int):
            quality = f"{h}p"

    return ExtractedMetadata(
        title=title,
        language=lang,
        ext=ext,
        quality=quality,
        duration_hhmmss=seconds_to_hhmmss(duration_sec if isinstance(duration_sec, int) else None),
        platform=platform,
    )