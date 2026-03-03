import asyncio
import json
import sys


async def run_once(url: str, extractor_args: str):
    cmd = [
        "yt-dlp",
        "--dump-single-json",
        "--no-warnings",
        "--skip-download",
        "--no-playlist",
        "--geo-bypass",
        "--geo-bypass-country", "IN",
        "--extractor-args", extractor_args,
        url,
    ]

    print(f"\n=== Trying client: {extractor_args} ===")

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    out, err = await proc.communicate()

    stderr = err.decode(errors="ignore")

    if proc.returncode != 0:
        print("❌ FAILED")
        print("Return code:", proc.returncode)
        print("STDERR:")
        print(stderr[:2000])
        return False

    try:
        info = json.loads(out.decode("utf-8", errors="ignore"))
        print("✅ SUCCESS")
        print("Title:", info.get("title"))
        print("Duration:", info.get("duration"))
        print("Extractor:", info.get("extractor"))
        return True
    except Exception as e:
        print("⚠ JSON parse failed:", e)
        return False


async def main():
    if len(sys.argv) < 2:
        print("Usage: python debug_metadata.py <youtube_url>")
        return

    url = sys.argv[1]

    clients = [
        "youtube:player_client=web,web_safari,tv",
        "youtube:player_client=android",
        "youtube:player_client=ios",
    ]

    for c in clients:
        ok = await run_once(url, c)
        if ok:
            break


if __name__ == "__main__":
    asyncio.run(main())