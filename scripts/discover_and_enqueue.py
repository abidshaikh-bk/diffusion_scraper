from __future__ import annotations

import asyncio
import os
import random
import socket
import time
import yaml
from dotenv import load_dotenv

from app.sync.oauth import get_credentials
from app.sync.sheets_client import SheetsClient
from app.sync.sync_manager import SyncManager

from app.core.logger import setup_logger
from app.core.network import wait_for_internet
from app.core.retry import retry_with_backoff, is_retryable_transient, is_non_retryable
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


def _fmt_secs(secs: float) -> str:
    if secs < 60:
        return f"{secs:.0f}s"
    if secs < 3600:
        return f"{secs/60:.0f}m"
    return f"{secs/3600:.1f}h"


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

    continue_on_provider_error = bool(limits.get("continue_on_provider_error", True))

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
    queries_per_platform = int(cycle.get("queries_per_platform", 1))  # 1 = one term per platform pass

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

    # Track how many we have successfully appended per query (across all platforms)
    taken: dict[str, int] = {q: 0 for q in queries}

    # Shuffle-bag query strategy
    q_bag: list[str] = _build_query_bag(queries)

    # ✅ platform cooldown map: platform -> epoch seconds until which platform is skipped
    cooldown_until: dict[str, float] = {}

    async def _sleep_between_platforms():
        s = sleep_seconds + (random.randint(0, jitter_seconds) if jitter_seconds > 0 else 0)
        logger.info(f"[DISCOVERY] Sleeping {s}s before next platform...")

        # ✅ show progress every 10 seconds
        remaining = s
        while remaining > 0:
            await asyncio.sleep(min(10, remaining))
            remaining -= 10
            if remaining > 0:
                logger.info(f"[DISCOVERY] ...sleeping, {remaining}s remaining")

    def _any_capacity_left() -> bool:
        return any((per_query_cap - taken[q]) > 0 for q in queries)

    def _pick_next_query_with_capacity() -> tuple[str | None, int]:
        """
        Returns (query, remaining_capacity). If none available, returns (None, 0).
        Uses shuffle-bag to avoid repeats until bag refills.
        """
        nonlocal q_bag

        if not _any_capacity_left():
            return None, 0

        if not q_bag:
            q_bag = _build_query_bag(queries)

        tries = 0
        while tries < (len(queries) * 2):
            if not q_bag:
                q_bag = _build_query_bag(queries)

            candidate = q_bag.pop()
            remaining = per_query_cap - taken[candidate]
            if remaining > 0:
                return candidate, remaining

            tries += 1

        # Fallback scan
        for q in queries:
            remaining = per_query_cap - taken[q]
            if remaining > 0:
                return q, remaining

        return None, 0

    def _set_cooldown(platform: str, *, base_seconds: int, jitter: int, reason: str):
        now = time.time()
        cd = base_seconds + (random.randint(0, jitter) if jitter > 0 else 0)
        until = now + cd

        prev = cooldown_until.get(platform, 0)
        # keep the longer cooldown if already set
        cooldown_until[platform] = max(prev, until)

        logger.warning(
            f"[COOLDOWN] platform={platform} cooling down for {_fmt_secs(cd)} "
            f"(reason={reason})"
        )

    def _is_in_cooldown(platform: str) -> tuple[bool, float]:
        now = time.time()
        until = cooldown_until.get(platform, 0.0)
        return (until > now), max(0.0, until - now)

    async def process_one_platform(platform: str):
        in_cd, left = _is_in_cooldown(platform)
        if in_cd:
            logger.warning(
                f"[DISCOVERY] platform={platform} skipped (cooldown remaining {_fmt_secs(left)})"
            )
            return

        n = len(queries) if queries_per_platform == 0 else max(1, queries_per_platform)

        for _ in range(n):
            q, remaining = _pick_next_query_with_capacity()
            if not q:
                logger.info("[DISCOVERY] All queries hit per_query_cap; nothing left to do this cycle.")
                return

            logger.info(f'[DISCOVERY] platform="{platform}" query="{q}" remaining_for_query={remaining}')

            # ---- DISCOVERY (rate-limit aware) ----
            try:
                await wait_for_internet(logger=logger)

                # IMPORTANT:
                # - retries=8 keeps us from hammering rate-limited platforms forever
                # - your retry_with_backoff will STILL keep going infinitely for network-ish errors
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
                    retries=8,
                )

            except Exception as e:
                # Cooldown rules:
                # - "non-retryable" (bot check/private/unavailable) => long cooldown + skip platform
                # - "retryable transient" (429/too many requests) => medium cooldown + skip platform
                if is_non_retryable(e):
                    _set_cooldown(platform, base_seconds=60 * 60, jitter=15 * 60, reason="non-retryable/bot-or-private")
                    if continue_on_provider_error:
                        return
                    raise

                if is_retryable_transient(e):
                    _set_cooldown(platform, base_seconds=45 * 60, jitter=15 * 60, reason="rate-limit/429")
                    if continue_on_provider_error:
                        return
                    raise

                logger.exception(f"[DISCOVERY] platform={platform} provider error: {type(e).__name__}: {e}")
                if continue_on_provider_error:
                    # short cooldown so we don’t rapid-fire a broken provider
                    _set_cooldown(platform, base_seconds=10 * 60, jitter=5 * 60, reason="provider-error")
                    return
                raise

            urls = [u for u in (urls or []) if u]
            random.shuffle(urls)

            take_n = min(chunk_size, remaining, len(urls))
            chunk = urls[:take_n]

            if not chunk:
                logger.info(f'[DISCOVERY] platform="{platform}" query="{q}" found=0 (no append)')
                continue

            # ---- APPEND TO SHEET ----
            await wait_for_internet(logger=logger)

            added = await retry_with_backoff(
                lambda: asyncio.to_thread(sync.append_pending_urls, chunk, device, q),
                logger=logger,
                operation_name=f"sheet_append:{platform}",
                retries=None,  # infinite (safe)
            )

            # ✅ count actual appended, not attempted
            taken[q] += int(added)

            logger.info(
                f'[DISCOVERY] platform="{platform}" query="{q}" chunk_found={len(chunk)} appended={added}'
            )
            print(
                f'[DISCOVERY] platform="{platform}" query="{q}" chunk_found={len(chunk)} appended={added}'
            )

            # Optional: tiny micro-pause after successful append (extra human-ish)
            # Keep it small so you don’t slow down too much.
            await sleep_async(base=random.uniform(0.8, 2.5))

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