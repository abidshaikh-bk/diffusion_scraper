from __future__ import annotations

from app.downloader.ytdlp_downloader import download_video


async def download_dailymotion(
    *,
    url: str,
    title: str,
    platform: str = "Dailymotion",
    base_dir: str = "data/downloads",
) -> str:
    # Dailymotion is supported by yt-dlp; we reuse the hardened downloader.
    return await download_video(url=url, title=title, platform=platform, base_dir=base_dir)