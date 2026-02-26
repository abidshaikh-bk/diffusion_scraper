from __future__ import annotations
import random
from typing import List, Set
from playwright.async_api import async_playwright

async def dailymotion_search(query: str, max_pages: int = 2) -> List[str]:
    results: List[str] = []
    seen: Set[str] = set()

    q = query.strip().replace(" ", "%20")
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context(viewport={"width": 1280, "height": 720})
        page = await ctx.new_page()

        for page_no in range(1, max_pages + 1):
            url = f"https://www.dailymotion.com/search/{q}/videos?page={page_no}"
            await page.goto(url, wait_until="domcontentloaded")
            await page.wait_for_timeout(int(700 + random.random() * 800))

            anchors = await page.query_selector_all("a")
            for a in anchors:
                href = await a.get_attribute("href")
                if not href:
                    continue
                if href.startswith("/"):
                    full = "https://www.dailymotion.com" + href
                else:
                    full = href

                # Dailymotion videos are typically /video/<id>
                if full.startswith("https://www.dailymotion.com/video/"):
                    if full not in seen:
                        seen.add(full)
                        results.append(full)

        await ctx.close()
        await browser.close()

    return results