from __future__ import annotations

from pathlib import Path
from app.core.utils import safe_filename, short_hash


def build_output_template(
    base_dir: str,
    platform: str,
    title: str,
    url: str,
) -> str:
    """
    Returns yt-dlp output template path including %(ext)s placeholder.
    Example: data/downloads/YouTube/Some_Title__a1b2c3d4.%(ext)s
    """
    platform_dir = Path(base_dir) / (platform or "Other")
    platform_dir.mkdir(parents=True, exist_ok=True)

    name = safe_filename(title or "video")
    h = short_hash(url)
    return str(platform_dir / f"{name}__{h}.%(ext)s")