from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse, parse_qs

import aiohttp

from app.search_engine.base_search import BaseSearchProvider, SearchQuery


VIDEO_HOSTS = {"www.youtube.com", "youtube.com", "youtu.be", "vimeo.com", "www.vimeo.com"}


def _normalize_url(u: str) -> str:
    u = (u or "").strip()
    if not u:
        return ""
    return u


def _extract_youtube_watch_url(u: str) -> str:
    """
    Normalize youtu.be links -> youtube watch links when possible.
    """
    try:
        p = urlparse(u)
    except Exception:
        return u

    host = p.netloc.lower()
    if host == "youtu.be":
        vid = p.path.strip("/").split("/")[0]
        if vid:
            return f"https://www.youtube.com/watch?v={vid}"
    return u


def _is_video_url(u: str) -> bool:
    try:
        p = urlparse(u)
    except Exception:
        return False
    host = (p.netloc or "").lower()
    return host in VIDEO_HOSTS


@dataclass
class GoogleCustomSearchProvider(BaseSearchProvider):
    api_key: str
    cx: str
    page_size: int = 10       # Google CSE supports up to 10 per page
    max_pages: int = 3        # keep costs bounded

    @staticmethod
    def from_env() -> "GoogleCustomSearchProvider":
        api_key = os.getenv("GOOGLE_CSE_API_KEY", "").strip()
        cx = os.getenv("GOOGLE_CSE_CX", "").strip()
        if not api_key or not cx:
            raise ValueError("GOOGLE_CSE_API_KEY and GOOGLE_CSE_CX must be set in .env")
        page_size = int(os.getenv("SEARCH_PAGE_SIZE", "10"))
        max_pages = int(os.getenv("SEARCH_MAX_PAGES", "3"))
        return GoogleCustomSearchProvider(api_key=api_key, cx=cx, page_size=page_size, max_pages=max_pages)

    async def _call(self, session: aiohttp.ClientSession, q: str, start: int) -> Dict[str, Any]:
        url = "https://www.googleapis.com/customsearch/v1"
        params = {
            "key": self.api_key,
            "cx": self.cx,
            "q": q,
            "num": self.page_size,
            "start": start,  # 1, 11, 21...
        }
        async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=30)) as resp:
            data = await resp.json(content_type=None)
            if resp.status != 200:
                raise RuntimeError(f"Custom Search API error {resp.status}: {str(data)[:300]}")
            return data

    async def search(self, query: SearchQuery) -> List[str]:
        q = query.text.strip()
        if not q:
            return []

        # Bias towards video results (doesn't guarantee, but helps)
        # You can further restrict using "site:youtube.com OR site:vimeo.com" if needed.
        q2 = f'{q} (site:youtube.com OR site:youtu.be OR site:vimeo.com)'

        results: List[str] = []
        seen: set[str] = set()

        async with aiohttp.ClientSession() as session:
            start = 1
            for _ in range(self.max_pages):
                data = await self._call(session, q2, start=start)
                items = data.get("items", []) or []

                for it in items:
                    link = _normalize_url(it.get("link", ""))
                    if not link:
                        continue
                    link = _extract_youtube_watch_url(link)

                    if not _is_video_url(link):
                        continue
                    if link in seen:
                        continue
                    seen.add(link)
                    results.append(link)

                    if len(results) >= query.max_results:
                        return results

                # Next page
                start += self.page_size

                # stop if API returns no items
                if not items:
                    break

        return results