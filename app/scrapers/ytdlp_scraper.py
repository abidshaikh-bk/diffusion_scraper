from __future__ import annotations

import asyncio
import json
import os
from typing import Tuple

from app.core.human_sleep import sleep_async
from app.core.utils import seconds_to_hhmmss
from app.models.video_metadata import VideoMetadata
from app.scrapers.ytdlp_auth import ytdlp_auth_args


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

ONLY_IMAGES_MARKERS = (
    "only images are available",
)

UNAVAILABLE_MARKERS = (
    "this video is unavailable",
    "private video",
)


def _platform_from_info(info: dict) -> str:
    key = (info.get("extractor_key") or info.get("extractor") or "").lower()
    if "youtube" in key:
        return "YouTube"
    if "vimeo" in key:
        return "Vimeo"
    if "dailymotion" in key:
        return "Dailymotion"
    return (info.get("extractor_key") or info.get("extractor") or "Unknown")


def _quality_from_info(info: dict) -> str:
    if info.get("resolution"):
        return str(info["resolution"])
    h = info.get("height")
    if isinstance(h, int):
        return f"{h}p"
    return ""


def _contains_any(stderr: str, markers: Tuple[str, ...]) -> bool:
    s = (stderr or "").lower()
    return any(m in s for m in markers)


async def _run_ytdlp_metadata(url: str, extractor_args: str) -> dict:
    sleep_requests = os.getenv("YTDLP_SLEEP_REQUESTS_SEC", "1").strip()
    min_sleep = os.getenv("YTDLP_MIN_SLEEP_INTERVAL_SEC", "2").strip()
    max_sleep = os.getenv("YTDLP_MAX_SLEEP_INTERVAL_SEC", "5").strip()

    cmd = [
        "yt-dlp",
        "--dump-single-json",
        "--no-warnings",
        "--skip-download",
        "--no-playlist",
        "--geo-bypass",
        "--geo-bypass-country", "IN",

        "--sleep-requests", sleep_requests,
        "--min-sleep-interval", min_sleep,
        "--max-sleep-interval", max_sleep,

        "--extractor-args", extractor_args,

        *ytdlp_auth_args(),
        url,
    ]

    await sleep_async(base=1.1)

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    out, err = await proc.communicate()

    stderr = err.decode(errors="ignore")
    if proc.returncode != 0:
        # IMPORTANT: raise full stderr snippet so worker logs show real reason
        raise RuntimeError(stderr[:900] or "yt-dlp metadata failed (empty stderr)")

    return json.loads(out.decode("utf-8", errors="ignore"))


async def fetch_metadata(url: str) -> VideoMetadata:
    # Metadata should NOT depend on -f selection.
    clients = [
        "youtube:player_client=web,web_safari,tv",
        "youtube:player_client=android",
        "youtube:player_client=ios",
    ]

    last_err = ""
    for extractor_args in clients:
        try:
            info = await _run_ytdlp_metadata(url, extractor_args)

            duration_sec = info.get("duration") if isinstance(info.get("duration"), int) else None
            categories = info.get("categories") or []
            tags = info.get("tags") or []

            return VideoMetadata(
                url=url,
                title=info.get("title") or "",
                description=info.get("description") or "",
                language=info.get("language") or "",
                video_type=info.get("ext") or "",
                quality=_quality_from_info(info),
                duration=seconds_to_hhmmss(duration_sec),
                platform=_platform_from_info(info),
                uploader=info.get("uploader") or "",
                channel=info.get("channel") or info.get("uploader") or "",
                categories=[str(x) for x in categories if x],
                tags=[str(x) for x in tags if x],
            )

        except Exception as e:
            last_err = str(e)

            if _contains_any(last_err, UNAVAILABLE_MARKERS) or _contains_any(last_err, ONLY_IMAGES_MARKERS):
                raise RuntimeError(f"yt-dlp failed (non-retryable): {last_err[:400]}")

            # if EJS-ish -> try next client
            if _contains_any(last_err, EJS_MARKERS):
                await sleep_async(base=0.8)
                continue

            # other errors -> still try next client
            await sleep_async(base=0.6)
            continue

    # exhausted clients
    if _contains_any(last_err, EJS_MARKERS):
        raise RuntimeError(f"yt-dlp failed: YT_N_CHALLENGE_NEEDS_EJS: {last_err[:400]}")

    raise RuntimeError(f"yt-dlp failed: {last_err[:400]}")