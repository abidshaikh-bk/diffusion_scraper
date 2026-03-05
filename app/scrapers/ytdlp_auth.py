import os


def ytdlp_auth_args(platform_key: str | None = None) -> list[str]:
    """
    By default, apply cookies ONLY for YouTube (reduces cross-platform fingerprinting risk).
    If you want cookies for all, set YTDLP_COOKIES_APPLY_ALL=true.
    """
    apply_all = os.getenv("YTDLP_COOKIES_APPLY_ALL", "false").strip().lower() in {"1", "true", "yes", "on"}

    if not apply_all:
        pk = (platform_key or "").strip().lower()
        if pk and pk != "youtube":
            return []

    browser = os.getenv("YTDLP_COOKIES_FROM_BROWSER", "").strip()
    cookie_file = os.getenv("YTDLP_COOKIES_FILE", "").strip()

    args: list[str] = []
    if browser:
        args += ["--cookies-from-browser", browser]
    elif cookie_file:
        args += ["--cookies", cookie_file]

    return args