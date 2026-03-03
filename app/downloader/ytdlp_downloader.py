from __future__ import annotations

import asyncio
import os
from pathlib import Path

from app.downloader.path_builder import build_output_template
from app.core.utils import short_hash
from app.scrapers.ytdlp_auth import ytdlp_auth_args
from app.core.human_sleep import sleep_async


EJS_MARKERS = (
    "yt_n_challenge_needs_ejs",
    "n challenge solving failed",
    "signature",
    "nsig",
)

FORMAT_MARKERS = (
    "requested format is not available",
    "use --list-formats",
)

UNAVAILABLE_MARKERS = (
    "this video is unavailable",
    "private video",
)

ONLY_IMAGES_MARKERS = (
    "only images are available",
)


def _contains_any(stderr: str, markers: tuple[str, ...]) -> bool:
    s = (stderr or "").lower()
    return any(m in s for m in markers)


async def _run_ytdlp_download(url: str, out_template: str, extra_args: list[str]) -> None:
    sleep_requests = os.getenv("YTDLP_SLEEP_REQUESTS_SEC", "1").strip()
    min_sleep = os.getenv("YTDLP_MIN_SLEEP_INTERVAL_SEC", "2").strip()
    max_sleep = os.getenv("YTDLP_MAX_SLEEP_INTERVAL_SEC", "5").strip()

    cmd = [
        "yt-dlp",

        # output
        "-o", out_template,

        # throttling + cleanup
        "--sleep-requests", sleep_requests,
        "--min-sleep-interval", min_sleep,
        "--max-sleep-interval", max_sleep,
        "--no-part",
        "--rm-cache-dir",

        # merge preferences
        "--prefer-ffmpeg",
        "--merge-output-format", "mp4",
        "--postprocessor-args", "ffmpeg:-movflags +faststart",
        "--no-keep-video",

        *extra_args,
        *ytdlp_auth_args(),
        url,
    ]

    # ✅ human-ish pause before hitting yt-dlp
    await sleep_async(base=1.3)

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr_b = await proc.communicate()

    stderr = stderr_b.decode(errors="ignore")

    if proc.returncode != 0:
        raise RuntimeError(stderr[:700] or "yt-dlp download failed (unknown stderr)")


async def download_video(
    url: str,
    title: str,
    platform: str,
    base_dir: str = "data/downloads",
) -> str:
    """
    Downloads with internal fallback:
      1) relaxed bestvideo*+bestaudio/best
      2) more relaxed bv*+ba/b
      3) android player client
      4) ios player client
    Returns absolute path of the downloaded file.
    """
    out_template = build_output_template(base_dir, platform, title, url)

    # format + client fallbacks
    args_primary = [
        "-f", "bestvideo*+bestaudio/best",
        "--extractor-args", "youtube:player_client=web,web_safari,tv",
    ]
    args_relaxed = [
        "-f", "bv*+ba/b",
        "--extractor-args", "youtube:player_client=web,web_safari,tv",
    ]
    args_android = [
        "-f", "bestvideo*+bestaudio/best",
        "--extractor-args", "youtube:player_client=android",
    ]
    args_ios = [
        "-f", "bestvideo*+bestaudio/best",
        "--extractor-args", "youtube:player_client=ios",
    ]

    attempts = [args_primary, args_relaxed, args_android, args_ios]
    last_err = ""

    for i, extra in enumerate(attempts, start=1):
        try:
            await _run_ytdlp_download(url, out_template, extra)
            break
        except Exception as e:
            last_err = str(e)

            # stop early on truly non-retryable
            if _contains_any(last_err, UNAVAILABLE_MARKERS) or _contains_any(last_err, ONLY_IMAGES_MARKERS):
                raise RuntimeError(f"yt-dlp download failed (non-retryable): {last_err[:400]}")

            # otherwise, continue to next fallback
            await sleep_async(base=0.9)

    else:
        # exhausted fallbacks
        if _contains_any(last_err, EJS_MARKERS):
            raise RuntimeError(f"yt-dlp download failed: YT_N_CHALLENGE_NEEDS_EJS: {last_err[:400]}")
        if _contains_any(last_err, FORMAT_MARKERS):
            raise RuntimeError(f"yt-dlp download failed: FORMAT_NOT_AVAILABLE: {last_err[:400]}")
        raise RuntimeError(f"yt-dlp download failed: {last_err[:400]}")

    # find downloaded file by hash suffix
    platform_dir = Path(base_dir) / (platform or "Other")
    h = short_hash(url)

    # prefer merged mp4
    mp4 = list(platform_dir.glob(f"*__{h}.mp4"))
    if mp4:
        return str(mp4[0].resolve())

    # fallback: pick the largest matching file
    matches = list(platform_dir.glob(f"*__{h}.*"))
    if not matches:
        raise RuntimeError("Download finished but output file not found")

    matches.sort(key=lambda p: p.stat().st_size, reverse=True)
    return str(matches[0].resolve())