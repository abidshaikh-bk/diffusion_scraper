from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Optional

from app.downloader.path_builder import build_output_template
from app.core.utils import safe_filename, short_hash


async def download_video(
    url: str,
    title: str,
    platform: str,
    base_dir: str = "data/downloads",
) -> str:
    """
    Downloads the best available format using yt-dlp.
    Returns absolute path of the downloaded file.
    """
    out_template = build_output_template(base_dir, platform, title, url)

    # cmd = [
    #     "yt-dlp",
    #     "-f", "bestvideo+bestaudio/best",
    #     "--merge-output-format", "mp4",
    #     "-o", out_template,
    #     url,
    # ]

    cmd = [
        "yt-dlp",
        # "-f", "bv*+ba/b",                 # best video+audio, fallback to best single file
        "-f", "bv*[ext=mp4]+ba[ext=m4a]/b[ext=mp4]/b",                 # best video+audio, fallback to best single file
        "--merge-output-format", "mp4",    # always merge into mp4
        "--prefer-ffmpeg",                # force ffmpeg if available
        "--postprocessor-args", "ffmpeg:-movflags +faststart",
        "--rm-cache-dir",                 # optional: keeps things clean
        "--no-keep-video",                # remove intermediate files after merge
        "--no-part",                      # avoid leaving .part files
        "-o", out_template,
        url,
    ]

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    stdout, stderr = await proc.communicate()

    if proc.returncode != 0:
        raise RuntimeError(stderr.decode(errors="ignore")[:600])

    # Find the downloaded file by hash prefix
    # platform_dir = Path(base_dir) / (platform or "Other")
    # h = short_hash(url)
    # matches = list(platform_dir.glob(f"*__{h}.*"))

    # if not matches:
    #     raise RuntimeError("Download finished but output file not found")

    # return str(matches[0].resolve())

    platform_dir = Path(base_dir) / (platform or "Other")
    h = short_hash(url)

    # Prefer merged mp4
    mp4 = list(platform_dir.glob(f"*__{h}.mp4"))
    if mp4:
        return str(mp4[0].resolve())

    # fallback (if merge failed or format isn't mp4)
    matches = list(platform_dir.glob(f"*__{h}.*"))
    if not matches:
        raise RuntimeError("Download finished but output file not found")

    # choose the largest file as best guess
    matches.sort(key=lambda p: p.stat().st_size, reverse=True)
    return str(matches[0].resolve())