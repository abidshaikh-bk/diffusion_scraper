from __future__ import annotations
import asyncio, os, socket, yaml, random
from dotenv import load_dotenv

from app.sync.oauth import get_credentials
from app.sync.sheets_client import SheetsClient
from app.sync.sync_manager import SyncManager
from app.discovery.discovery_runner import discover_urls_for_query

import logging
from app.core.logger import setup_logger
from app.core.network import wait_for_internet
from app.core.retry import retry_with_backoff
from app.core.human_sleep import sleep_async

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
load_dotenv()

def load_discovery_cfg():
    return yaml.safe_load(open("configs/discovery.yaml", "r", encoding="utf-8")) or {}

async def main():

    sid = os.getenv("SPREADSHEET_ID", "").strip()
    tab = os.getenv("SHEET_TAB_NAME", "Sheet1").strip()
    device = socket.gethostname()
    logger = setup_logger()
    logger.info("Discovery started")
    logger.info(f"Device={device} Spreadsheet={sid} Tab={tab}")
    if not sid:
        raise ValueError("SPREADSHEET_ID missing in .env")

    cfg = load_discovery_cfg()
    queries = cfg.get("queries", []) or []
    per_query_cap = int((cfg.get("limits", {}) or {}).get("per_query_max_urls", 30))

    ps = cfg.get("platform_search", {}) or {}
    yt = ps.get("youtube", {}) or {}
    vi = ps.get("vimeo", {}) or {}
    dm = ps.get("dailymotion", {}) or {}


    creds = get_credentials(SCOPES)
    client = SheetsClient(creds)
    sync = SyncManager(client, spreadsheet_id=sid, tab_name=tab)

    total_added = 0

    # build a mutable pool of queries
    q_pool = [q for q in queries if str(q).strip()]
    random.shuffle(q_pool)

    # how many urls to take from each query per “round”
    chunk_size = int((cfg.get("limits", {}) or {}).get("per_query_chunk", 6))  # add in yaml if you want
    chunk_size = max(1, min(chunk_size, per_query_cap))

    # keep track of how many we already took from each query this run
    taken = {q: 0 for q in q_pool}

    while q_pool:
        # pick next query randomly (human-like)
        q = random.choice(q_pool)

        await wait_for_internet(logger=logger)
        urls = await retry_with_backoff(
            lambda: discover_urls_for_query(
                q,
                youtube_max=int(yt.get("max_results_per_query", 25)),
                vimeo_pages=int(vi.get("max_pages", 2)),
                dailymotion_pages=int(dm.get("max_pages", 2)),
                enable_youtube=bool(yt.get("enabled", True)),
                enable_vimeo=bool(vi.get("enabled", True)),
                enable_dailymotion=bool(dm.get("enabled", True)),
            ),
            logger=logger,
            operation_name="discovery_search",
            retries=None,  # infinite if you want
        )

        # de-dupe and take only a small chunk so we mix sources/queries
        urls = [u for u in (urls or []) if u]
        random.shuffle(urls)

        # cap total per query
        remaining = per_query_cap - taken[q]
        if remaining <= 0:
            q_pool.remove(q)
            continue

        take_n = min(chunk_size, remaining, len(urls))
        chunk = urls[:take_n]
        taken[q] += take_n

        if not chunk:
            # if a query yields nothing repeatedly you may want to drop it
            # for now, just remove so it doesn't dominate the loop
            q_pool.remove(q)
            continue

        await wait_for_internet(logger=logger)
        added = await retry_with_backoff(
            lambda: asyncio.to_thread(sync.append_pending_urls, chunk, device),
            logger=logger,
            operation_name="sheet_append",
            retries=None,  # infinite if you want
        )

        total_added += added
        logger.info(f'Query="{q}" chunk_found={len(chunk)} appended={added} total_appended={total_added}')
        print(f'Query="{q}" chunk_found={len(chunk)} appended={added} total_appended={total_added}')

        # ✅ human-like pause between queries so behavior doesn't look botty
        await sleep_async(base=1.1)

if __name__ == "__main__":
    asyncio.run(main())