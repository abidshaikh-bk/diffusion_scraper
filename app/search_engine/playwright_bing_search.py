from __future__ import annotations

import random
from dataclasses import dataclass
from typing import List, Set
from urllib.parse import urlparse, parse_qs

from playwright.async_api import async_playwright

from app.search_engine.base_search import BaseSearchProvider, SearchQuery

VIDEO_HOSTS = {"www.youtube.com", "youtube.com", "youtu.be", "vimeo.com", "www.vimeo.com"}


def _is_video_url(u: str) -> bool:
    try:
        host = (urlparse(u).netloc or "").lower()
        return host in VIDEO_HOSTS
    except Exception:
        return False


def _normalize_youtube(u: str) -> str:
    try:
        p = urlparse(u)
        if p.netloc.lower() == "youtu.be":
            vid = p.path.strip("/").split("/")[0]
            if vid:
                return f"https://www.youtube.com/watch?v={vid}"
        return u
    except Exception:
        return u


@dataclass
class PlaywrightBingSerpProvider(BaseSearchProvider):
    max_pages: int = 3
    headless: bool = True

    async def search(self, query: SearchQuery) -> List[str]:
        q = query.text.strip()
        if not q:
            return []

        # Bias to your target platforms
        bing_q = f'{q} (site:youtube.com OR site:youtu.be OR site:vimeo.com)'

        results: List[str] = []
        seen: Set[str] = set()

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=self.headless)
            context = await browser.new_context(
                viewport={"width": 1280, "height": 720},
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/122.0.0.0 Safari/537.36"
                ),
            )
            page = await context.new_page()

            for page_no in range(self.max_pages):
                first = 1 + page_no * 10
                url = f"https://www.bing.com/search?q={bing_q}&first={first}"
                await page.goto(url, wait_until="domcontentloaded")

                await page.wait_for_timeout(int(700 + random.random() * 900))

                anchors = await page.query_selector_all("a")
                for a in anchors:
                    href = await a.get_attribute("href")
                    if not href or not href.startswith("http"):
                        continue

                    href = _normalize_youtube(href)
                    if not _is_video_url(href):
                        continue
                    if href in seen:
                        continue

                    seen.add(href)
                    results.append(href)
                    if len(results) >= query.max_results:
                        await context.close()
                        await browser.close()
                        return results

            await context.close()
            await browser.close()

        return results