from __future__ import annotations
from typing import List, Set

from app.discovery.youtube_ytdlp_search import youtube_search
from app.discovery.playwright_vimeo_search import vimeo_search
from app.discovery.playwright_dailymotion_search import dailymotion_search

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
    seen: Set[str] = set()

    if enable_youtube:
        try:
            yt_urls = await youtube_search(query, max_results=youtube_max)
            for u in yt_urls:
                if u not in seen:
                    seen.add(u); urls.append(u)
        except Exception as e:
            # continue with other platforms
            pass

    if enable_vimeo:
        for u in await vimeo_search(query, max_pages=vimeo_pages):
            if u not in seen:
                seen.add(u); urls.append(u)

    if enable_dailymotion:
        for u in await dailymotion_search(query, max_pages=dailymotion_pages):
            if u not in seen:
                seen.add(u); urls.append(u)

    return urls