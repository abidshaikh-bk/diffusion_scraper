import asyncio
import yaml

from app.platforms.registry import PlatformRegistry
from app.scrapers.ytdlp_scraper import fetch_metadata
from app.downloader.ytdlp_downloader import download_video


def load_download_dir():
    data = yaml.safe_load(open("configs/config.yaml", "r", encoding="utf-8")) or {}
    d = data.get("downloads", {}) or {}
    return d.get("base_dir", "data/downloads")


async def main():
    registry = PlatformRegistry.from_yaml()
    base_dir = load_download_dir()

    with open("inputs/seed_urls.txt", "r", encoding="utf-8") as f:
        urls = [l.strip() for l in f if l.strip()]

    for url in urls:
        if not registry.is_allowed(url):
            print("SKIP:", url)
            continue

        meta = await fetch_metadata(url)
        print("Downloading:", meta.title)

        path = await download_video(
            url=meta.url,
            title=meta.title,
            platform=meta.platform,
            base_dir=base_dir,
        )
        print("Saved to:", path)
        break  # download only first allowed URL


if __name__ == "__main__":
    asyncio.run(main())