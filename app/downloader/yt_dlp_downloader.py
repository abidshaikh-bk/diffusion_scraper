from __future__ import annotations

import asyncio
import hashlib
import os
import re
from pathlib import Path


def _safe_filename(name: str) -> str:
    name = re.sub(r"[^\w\s-]", "", name)
    name = re.sub(r"\s+", "_", name.strip())
    return name[:120]


def _short_hash(text: str) -> str:
    return hashlib.md5(text.encode("utf-8")).hexdigest()[:8]


async def download_video(
    url: str,
    title: str,
    platform: str,
    ext: str | None,
    base_dir: str = "data/downloads",
) -> str:
    """
    Async yt-dlp downloader.
    Returns local file path.
    """

    platform_dir = Path(base_dir) / (platform or "Other")
    platform_dir.mkdir(parents=True, exist_ok=True)

    safe_title = _safe_filename(title or "video")
    hash_part = _short_hash(url)

    filename_template = f"{safe_title}__{hash_part}.%(ext)s"
    output_path = str(platform_dir / filename_template)

    cmd = [
        "yt-dlp",
        "-f", "bestvideo+bestaudio/best",
        "-o", output_path,
        url,
    ]

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    stdout, stderr = await proc.communicate()

    if proc.returncode != 0:
        raise RuntimeError(stderr.decode(errors="ignore")[:500])

    # Find the downloaded file (yt-dlp resolves %(ext)s)
    files = list(platform_dir.glob(f"{safe_title}__{hash_part}.*"))
    if not files:
        raise RuntimeError("Download completed but file not found")

    return str(files[0].resolve())