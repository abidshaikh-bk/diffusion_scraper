from __future__ import annotations
import asyncio, json
from typing import List

def _extract_urls_from_ytdlp_json(data: dict) -> List[str]:
    urls = []
    for e in data.get("entries", []) or []:
        if not isinstance(e, dict):
            continue
        u = e.get("webpage_url") or e.get("url")
        if u and isinstance(u, str):
            urls.append(u)
    return urls

async def youtube_search(query: str, max_results: int = 25) -> List[str]:
    """
    Fault-tolerant YouTube discovery using yt-dlp search.
    Key flags:
      --ignore-errors: skip unavailable/private videos
      --no-abort-on-error: don't fail entire run due to one bad entry
      --flat-playlist: faster, returns URLs without deep extraction
    """
    search_url = f"ytsearch{max_results}:{query}"
    cmd = [
        "yt-dlp",
        "--dump-single-json",
        "--no-warnings",
        "--skip-download",
        "--ignore-errors",
        "--no-abort-on-error",
        "--flat-playlist",
        search_url,
    ]

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    out, err = await proc.communicate()

    # yt-dlp may still return non-zero sometimes; if we got JSON, try to parse it anyway.
    text_out = out.decode("utf-8", errors="ignore").strip()
    if not text_out:
        raise RuntimeError(f"yt-dlp search produced no output: {err.decode(errors='ignore')[:400]}")

    try:
        data = json.loads(text_out)
    except Exception:
        # If JSON is not parseable, then raise with stderr.
        raise RuntimeError(f"yt-dlp search output not JSON: {err.decode(errors='ignore')[:400]}")

    return _extract_urls_from_ytdlp_json(data)