from __future__ import annotations

import hashlib
import re


def seconds_to_hhmmss(seconds: int | None) -> str:
    if seconds is None or seconds < 0:
        return ""
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    return f"{h:02d}:{m:02d}:{s:02d}"


def safe_filename(name: str, max_len: int = 120) -> str:
    name = (name or "").strip()
    name = re.sub(r"[^\w\s-]", "", name)
    name = re.sub(r"\s+", "_", name)
    return name[:max_len] or "video"


def short_hash(text: str) -> str:
    return hashlib.md5(text.encode("utf-8")).hexdigest()[:8]