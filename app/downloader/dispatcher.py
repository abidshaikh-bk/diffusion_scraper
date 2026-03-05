from __future__ import annotations

from app.downloader.ytdlp_downloader import download_video
from app.downloader.vimeo_downloader import download_vimeo
from app.downloader.dailymotion_downloader import download_dailymotion


def _norm(k: str) -> str:
    return (k or "").strip().lower()


async def download_by_platform(
    *,
    platform_key: str,
    url: str,
    title: str,
    platform_label: str,
    base_dir: str,
) -> str:
    """
    platform_key: youtube / vimeo / dailymotion / ...
    platform_label: what you want written into folder names (e.g. 'Vimeo')
    """
    pk = _norm(platform_key)

    if pk == "vimeo":
        return await download_vimeo(url=url, title=title, platform=platform_label or "Vimeo", base_dir=base_dir)

    if pk == "dailymotion":
        return await download_dailymotion(url=url, title=title, platform=platform_label or "Dailymotion", base_dir=base_dir)

    # youtube + everything else uses the generic hardened yt-dlp downloader
    return await download_video(url=url, title=title, platform=platform_label, base_dir=base_dir)