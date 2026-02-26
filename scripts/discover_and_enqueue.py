from __future__ import annotations
import asyncio, os, socket, yaml
from dotenv import load_dotenv

from app.sync.oauth import get_credentials
from app.sync.sheets_client import SheetsClient
from app.sync.sync_manager import SyncManager
from app.discovery.discovery_runner import discover_urls_for_query

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
load_dotenv()

def load_discovery_cfg():
    return yaml.safe_load(open("configs/discovery.yaml", "r", encoding="utf-8")) or {}

async def main():
    sid = os.getenv("SPREADSHEET_ID", "").strip()
    tab = os.getenv("SHEET_TAB_NAME", "Sheet1").strip()
    if not sid:
        raise ValueError("SPREADSHEET_ID missing in .env")

    cfg = load_discovery_cfg()
    queries = cfg.get("queries", []) or []
    per_query_cap = int((cfg.get("limits", {}) or {}).get("per_query_max_urls", 30))

    ps = cfg.get("platform_search", {}) or {}
    yt = ps.get("youtube", {}) or {}
    vi = ps.get("vimeo", {}) or {}
    dm = ps.get("dailymotion", {}) or {}

    device = socket.gethostname()

    creds = get_credentials(SCOPES)
    client = SheetsClient(creds)
    sync = SyncManager(client, spreadsheet_id=sid, tab_name=tab)

    total_added = 0
    for q in queries:
        urls = await discover_urls_for_query(
            q,
            youtube_max=int(yt.get("max_results_per_query", 25)),
            vimeo_pages=int(vi.get("max_pages", 2)),
            dailymotion_pages=int(dm.get("max_pages", 2)),
            enable_youtube=bool(yt.get("enabled", True)),
            enable_vimeo=bool(vi.get("enabled", True)),
            enable_dailymotion=bool(dm.get("enabled", True)),
        )
        urls = urls[:per_query_cap]
        added = sync.append_pending_urls(urls, device_name=device)
        total_added += added
        print(f'Query="{q}" found={len(urls)} appended={added}')

    print("Total appended:", total_added)

if __name__ == "__main__":
    asyncio.run(main())