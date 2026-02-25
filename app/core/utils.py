def format_source(platform: str, search_engine: str | None = None) -> str:
    platform = (platform or "").strip()
    se = (search_engine or "").strip()
    return f"{platform} ({se})" if se else platform


def seconds_to_hhmmss(seconds: int | None) -> str:
    if seconds is None or seconds < 0:
        return ""
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    return f"{h:02d}:{m:02d}:{s:02d}"