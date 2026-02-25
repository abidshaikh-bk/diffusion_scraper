from __future__ import annotations

import asyncio
import socket

from app.auth.oauth import get_credentials
from app.core.config import AppConfig
from app.search_engine.base_search import SearchQuery
from app.search_engine.playwright_bing_search import PlaywrightBingSerpProvider
from app.sync.sheets_client import SheetsClient
from app.sync.sync_manager import SyncManager

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

DEFAULT_QUERIES = [
    "CPR practical demonstration",
    "First aid hands-on training",
    "Fire safety drill demonstration",
    "Emergency evacuation drill",
    "Trauma care procedure demonstration",
]

async def main():
    cfg = AppConfig.from_env()
    device_name = socket.gethostname()

    provider = PlaywrightBingSerpProvider(max_pages=3, headless=True)

    creds = get_credentials(SCOPES)
    client = SheetsClient(creds)
    sync = SyncManager(client, spreadsheet_id=cfg.spreadsheet_id, tab_name=cfg.sheet_tab_name)

    total_added = 0
    for q in DEFAULT_QUERIES:
        urls = await provider.search(SearchQuery(text=q, max_results=25, search_engine_name="BingSERP"))
        # We’ll put platform later after metadata; for now Source can be blank.
        added = sync.append_pending_urls(urls, device_name=device_name)
        total_added += added
        print(f'Query="{q}" -> found {len(urls)} urls, appended {added}')

    print(f"Total appended: {total_added}")

if __name__ == "__main__":
    asyncio.run(main())