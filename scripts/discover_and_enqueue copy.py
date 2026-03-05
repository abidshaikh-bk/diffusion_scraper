from __future__ import annotations

import asyncio
import os
import random
import socket
import yaml
from dotenv import load_dotenv

from app.sync.oauth import get_credentials
from app.sync.sheets_client import SheetsClient
from app.sync.sync_manager import SyncManager

from app.core.logger import setup_logger
from app.core.network import wait_for_internet
from app.core.retry import retry_with_backoff
from app.core.human_sleep import sleep_async

from app.discovery.discovery_runner import discover_urls_for_platform_query

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
load_dotenv()


def load_discovery_cfg():
    return yaml.safe_load(open("configs/discovery.yaml", "r", encoding="utf-8")) or {}


def _enabled_platforms_in_order(cfg: dict) -> list[str]:
    cycle = cfg.get("cycle", {}) or {}
    platform_order = cycle.get("platform_order") or ["youtube"]

    ps = cfg.get("platform_search", {}) or {}
    out: list[str] = []
    for p in platform_order:
        pcfg = ps.get(p, {}) or {}
        if bool(pcfg.get("enabled", False)):
            out.append(p)
    return out


def _build_query_bag(queries: list[str]) -> list[str]:
    bag = list(queries)
    random.shuffle(bag)
    return bag


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
    limits = cfg.get("limits", {}) or {}
    cycle = cfg.get("cycle", {}) or {}

    queries = cfg.get("queries", []) or []
    queries = [str(q).strip() for q in queries if str(q).strip()]
    if not queries:
        raise RuntimeError("discovery.yaml: queries is empty")

    per_query_cap = int(limits.get("per_query_max_urls", 30))
    per_query_cap = max(1, per_query_cap)

    chunk_size = int(limits.get("per_query_chunk", 6))  # optional
    chunk_size = max(1, min(chunk_size, per_query_cap))

    cycle_enabled = bool(cycle.get("enabled", True))
    sleep_seconds = int(cycle.get("sleep_seconds", 180))
    jitter_seconds = int(cycle.get("jitter_seconds", 30))
    queries_per_platform = int(cycle.get("queries_per_platform", 1))  # 1 = exactly one term per platform

    platforms = _enabled_platforms_in_order(cfg)
    if not platforms:
        raise RuntimeError("discovery.yaml: no enabled platforms in cycle.platform_order")

    ps = cfg.get("platform_search", {}) or {}
    yt = ps.get("youtube", {}) or {}
    vi = ps.get("vimeo", {}) or {}
    dm = ps.get("dailymotion", {}) or {}

    creds = get_credentials(SCOPES)
    client = SheetsClient(creds)
    sync = SyncManager(client, spreadsheet_id=sid, tab_name=tab)

    # Track how many we have taken per query (across all platforms)
    taken: dict[str, int] = {q: 0 for q in queries}

    # ✅ Shuffle-bag strategy: random order, minimal repeats until bag refills
    q_bag: list[str] = _build_query_bag(queries)

    async def _sleep_between_platforms():
        s = sleep_seconds + (random.randint(0, jitter_seconds) if jitter_seconds > 0 else 0)
        logger.info(f"[DISCOVERY] Sleeping {s}s before next platform...")
        await sleep_async(base=float(s))

    def _any_capacity_left() -> bool:
        return any((per_query_cap - taken[q]) > 0 for q in queries)

    def _pick_next_query_with_capacity() -> tuple[str | None, int]:
        """
        Returns (query, remaining_capacity). If none available, returns (None, 0).
        Uses shuffle-bag to avoid repeatedly hitting the same query.
        """
        nonlocal q_bag

        if not _any_capacity_left():
            return None, 0

        # Refill bag if empty
        if not q_bag:
            q_bag = _build_query_bag(queries)

        # Pop until we find a query with capacity. If bag empties, refill and try again.
        tries = 0
        while tries < (len(queries) * 2):  # safety
            if not q_bag:
                q_bag = _build_query_bag(queries)
            candidate = q_bag.pop()
            remaining = per_query_cap - taken[candidate]
            if remaining > 0:
                return candidate, remaining
            tries += 1

        # Fallback: direct scan (should be rare)
        for q in queries:
            remaining = per_query_cap - taken[q]
            if remaining > 0:
                return q, remaining

        return None, 0

    async def process_one_platform(platform: str):
        # Decide how many queries to run for this platform pass
        n = len(queries) if queries_per_platform == 0 else max(1, queries_per_platform)

        for _ in range(n):
            q, remaining = _pick_next_query_with_capacity()
            if not q:
                logger.info("[DISCOVERY] All queries hit per_query_cap; nothing left to do this cycle.")
                return

            logger.info(f'[DISCOVERY] platform="{platform}" query="{q}" remaining_for_query={remaining}')

            await wait_for_internet(logger=logger)

            urls = await retry_with_backoff(
                lambda: discover_urls_for_platform_query(
                    platform=platform,
                    query=q,
                    youtube_max=int(yt.get("max_results_per_query", 25)),
                    vimeo_pages=int(vi.get("max_pages", 2)),
                    dailymotion_pages=int(dm.get("max_pages", 2)),
                ),
                logger=logger,
                operation_name=f"discovery_search:{platform}",
                retries=None,  # infinite
            )

            urls = [u for u in (urls or []) if u]
            random.shuffle(urls)

            take_n = min(chunk_size, remaining, len(urls))
            chunk = urls[:take_n]

            # IMPORTANT: increment "taken" by how many we attempted to enqueue
            taken[q] += take_n

            if not chunk:
                logger.info(f'[DISCOVERY] platform="{platform}" query="{q}" found=0 (no append)')
                continue

            await wait_for_internet(logger=logger)

            added = await retry_with_backoff(
                lambda: asyncio.to_thread(sync.append_pending_urls, chunk, device),
                logger=logger,
                operation_name=f"sheet_append:{platform}",
                retries=None,  # infinite
            )

            logger.info(
                f'[DISCOVERY] platform="{platform}" query="{q}" chunk_found={len(chunk)} appended={added}'
            )
            print(
                f'[DISCOVERY] platform="{platform}" query="{q}" chunk_found={len(chunk)} appended={added}'
            )

    if cycle_enabled:
        logger.info("[DISCOVERY] cycle.enabled=true (round-robin platforms forever)")
        while True:
            for platform in platforms:
                await process_one_platform(platform)
                await _sleep_between_platforms()
    else:
        logger.info("[DISCOVERY] cycle.enabled=false (one pass through platforms)")
        for platform in platforms:
            await process_one_platform(platform)
            await _sleep_between_platforms()


if __name__ == "__main__":
    asyncio.run(main())