from __future__ import annotations
from typing import List

from app.discovery.youtube_ytdlp_search import youtube_search
from app.discovery.playwright_vimeo_search import vimeo_search
from app.discovery.playwright_dailymotion_search import dailymotion_search


async def discover_urls_for_platform_query(
    platform: str,
    query: str,
    youtube_max: int,
    vimeo_pages: int,
    dailymotion_pages: int,
) -> List[str]:
    """
    Discover URLs for exactly ONE platform + ONE query.
    """
    p = (platform or "").lower().strip()

    if p == "youtube":
        return await youtube_search(query, max_results=youtube_max)

    if p == "vimeo":
        return await vimeo_search(query, max_pages=vimeo_pages)

    if p == "dailymotion":
        return await dailymotion_search(query, max_pages=dailymotion_pages)

    raise ValueError(f"Unsupported platform: {platform}")


# Backward-compatible helper (optional): keep the old behavior available
async def discover_urls_for_query(
    query: str,
    youtube_max: int,
    vimeo_pages: int,
    dailymotion_pages: int,
    enable_youtube: bool = True,
    enable_vimeo: bool = True,
    enable_dailymotion: bool = True,
) -> List[str]:
    urls: List[str] = []

    if enable_youtube:
        try:
            urls.extend(await youtube_search(query, max_results=youtube_max))
        except Exception:
            pass

    if enable_vimeo:
        try:
            urls.extend(await vimeo_search(query, max_pages=vimeo_pages))
        except Exception:
            pass

    if enable_dailymotion:
        try:
            urls.extend(await dailymotion_search(query, max_pages=dailymotion_pages))
        except Exception:
            pass

    # de-dupe while preserving order
    seen = set()
    out: List[str] = []
    for u in urls:
        if u and u not in seen:
            seen.add(u)
            out.append(u)
    return out