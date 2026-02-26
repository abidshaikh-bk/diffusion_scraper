import asyncio
from app.platforms.registry import PlatformRegistry
from app.scrapers.ytdlp_scraper import fetch_metadata


async def main():
    registry = PlatformRegistry.from_yaml()

    with open("inputs/seed_urls.txt", "r", encoding="utf-8") as f:
        urls = [l.strip() for l in f if l.strip()]

    for url in urls:
        if not registry.is_allowed(url):
            print(f"SKIP (not allowed): {url}")
            continue

        meta = await fetch_metadata(url)
        print("\n---")
        print("URL:", meta.url)
        print("Platform:", meta.platform)
        print("Title:", meta.title)
        print("Duration:", meta.duration)
        print("Language:", meta.language)
        print("Type:", meta.video_type)
        print("Quality:", meta.quality)


if __name__ == "__main__":
    asyncio.run(main())