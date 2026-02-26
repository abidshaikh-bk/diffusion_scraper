import asyncio
import yaml

from app.platforms.registry import PlatformRegistry
from app.scrapers.ytdlp_scraper import fetch_metadata
from app.filtering.keyword_filter import KeywordFilter
from app.filtering.duration_filter import DurationFilter
from app.filtering.pipeline import RelevancePipeline


def load_keywords():
    data = yaml.safe_load(open("configs/keywords.yaml", "r", encoding="utf-8")) or {}
    inc = tuple(data.get("include_keywords", []) or [])
    exc = tuple(data.get("exclude_keywords", []) or [])
    return inc, exc


def load_duration_bounds():
    data = yaml.safe_load(open("configs/config.yaml", "r", encoding="utf-8")) or {}
    f = data.get("filtering", {}) or {}
    return f.get("min_duration_sec"), f.get("max_duration_sec")


async def main():
    registry = PlatformRegistry.from_yaml()
    inc, exc = load_keywords()
    min_sec, max_sec = load_duration_bounds()

    pipeline = RelevancePipeline(
        KeywordFilter(include=inc, exclude=exc),
        DurationFilter(min_sec=min_sec, max_sec=max_sec),
    )

    with open("inputs/seed_urls.txt", "r", encoding="utf-8") as f:
        urls = [l.strip() for l in f if l.strip()]

    for url in urls:
        if not registry.is_allowed(url):
            print(f"SKIP (not allowed): {url}")
            continue

        meta = await fetch_metadata(url)
        res = pipeline.evaluate(meta)

        print("\n---")
        print("Title:", meta.title)
        print("Duration:", meta.duration)
        print("Relevant:", res.is_relevant)
        if res.reasons:
            print("Reasons:", ", ".join(res.reasons))


if __name__ == "__main__":
    asyncio.run(main())