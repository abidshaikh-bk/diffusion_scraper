import os

def ytdlp_auth_args() -> list[str]:
    browser = os.getenv("YTDLP_COOKIES_FROM_BROWSER", "").strip()
    cookie_file = os.getenv("YTDLP_COOKIES_FILE", "").strip()

    args: list[str] = []

    # Prefer browser cookies if configured
    if browser:
        args += ["--cookies-from-browser", browser]

    # Or use exported cookies.txt
    elif cookie_file:
        args += ["--cookies", cookie_file]

    return args