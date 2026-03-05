from __future__ import annotations

import asyncio
import os
import socket
import time
import yaml
import random
from dotenv import load_dotenv

from app.platforms.registry import PlatformRegistry
from app.scrapers.ytdlp_scraper import fetch_metadata
from app.filtering.keyword_filter import KeywordFilter
from app.filtering.duration_filter import DurationFilter
from app.filtering.pipeline import RelevancePipeline
from app.downloader.dispatcher import download_by_platform
from app.duplicates.sheet_dedupe import SheetDedupe
from app.core.logger import setup_logger
from app.core.network import wait_for_internet
from app.core.retry import retry_with_backoff, is_retryable_transient, is_non_retryable
from app.core.human_sleep import sleep_async  # ✅ FIX: missing import

from app.sync.oauth import get_credentials
from app.sync.sheets_client import SheetsClient
from app.sync.sync_manager import SyncManager, TaskRow

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
load_dotenv()

# DISABLE_YOUTUBE = os.getenv("DISABLE_YOUTUBE", "false").strip().lower() in {"1", "true", "yes", "on"}
# ONLY_PLATFORM = (os.getenv("ONLY_PLATFORM", "").strip().lower() or None)

def load_keywords():
    data = yaml.safe_load(open("configs/keywords.yaml", "r", encoding="utf-8")) or {}
    return tuple(data.get("include_keywords", []) or []), tuple(data.get("exclude_keywords", []) or [])


def load_config():
    cfg = yaml.safe_load(open("configs/config.yaml", "r", encoding="utf-8")) or {}
    f = cfg.get("filtering", {}) or {}
    d = cfg.get("downloads", {}) or {}
    r = cfg.get("runtime", {}) or {}
    limits = cfg.get("limits", {}) or {}
    return (
        f.get("min_duration_sec"),
        f.get("max_duration_sec"),
        d.get("base_dir", "data/downloads"),
        int(r.get("poll_interval_sec", 3)),
        int(r.get("batch_size", 10)),
        int(r.get("concurrency", 3)),
        int(limits.get("min_delay_sec", 1)),
        int(limits.get("max_delay_sec", 3)),
    )


def load_discovery_platform_order() -> list[str]:
    """
    Reuse discovery.yaml cycle.platform_order for download rotation as well.
    Only return platforms that are enabled.
    """
    cfg = yaml.safe_load(open("configs/discovery.yaml", "r", encoding="utf-8")) or {}
    cycle = cfg.get("cycle", {}) or {}
    order = cycle.get("platform_order") or ["youtube", "dailymotion", "vimeo"]

    ps = cfg.get("platform_search", {}) or {}
    enabled = []
    for p in order:
        pcfg = ps.get(p, {}) or {}
        if bool(pcfg.get("enabled", False)):
            enabled.append(p)
    return enabled or ["youtube"]


def _norm_platform_key(key: str) -> str:
    return (key or "").strip().lower()


def _fmt_secs(secs: float) -> str:
    if secs < 60:
        return f"{secs:.0f}s"
    if secs < 3600:
        return f"{secs/60:.0f}m"
    return f"{secs/3600:.1f}h"


class PlatformCooldowns:
    """
    Per-platform cooldowns (epoch seconds).
    """
    def __init__(self):
        self.until: dict[str, float] = {}

    def in_cooldown(self, platform_key: str) -> tuple[bool, float]:
        now = time.time()
        p = _norm_platform_key(platform_key)
        t = self.until.get(p, 0.0)
        if t > now:
            return True, (t - now)
        return False, 0.0

    def set(self, platform_key: str, *, base_seconds: int, jitter_seconds: int, reason: str, logger):
        now = time.time()
        cd = base_seconds + (random.randint(0, jitter_seconds) if jitter_seconds > 0 else 0)
        new_until = now + cd

        p = _norm_platform_key(platform_key)
        prev = self.until.get(p, 0.0)
        self.until[p] = max(prev, new_until)

        logger.warning(f"[COOLDOWN] platform={p} cooldown={_fmt_secs(cd)} reason={reason}")


def _platform_key(registry: PlatformRegistry, url: str) -> str:
    """
    Single source of truth for platform key in worker.
    """
    try:
        pk = registry.platform_key_for(url)
        pk = _norm_platform_key(pk)
        return pk or "unknown"
    except Exception:
        return "unknown"


async def process_one(
    sync: SyncManager,
    registry: PlatformRegistry,
    relevance: RelevancePipeline,
    base_dir: str,
    row_index: int,
    url: str,
    device: str,
    logger,
    cooldowns: PlatformCooldowns,
    min_delay_sec: int,
    max_delay_sec: int,
):
    pk = _platform_key(registry, url)

    # if ONLY_PLATFORM and pk != ONLY_PLATFORM:
    #     sync.update_fields(row_index, {
    #         "Status": "SKIPPED_DISABLED_PLATFORM",
    #         "Downloaded": "FALSE",
    #         "Relevance": "FALSE",
    #         "Relevance Reason": f"only_platform={ONLY_PLATFORM}",
    #     })
    #     return "skipped_not_only_platform"

    # if DISABLE_YOUTUBE and pk == "youtube":
    #     sync.update_fields(row_index, {
    #         "Status": "SKIPPED_DISABLED_PLATFORM",
    #         "Downloaded": "FALSE",
    #         "Relevance": "FALSE",
    #         "Relevance Reason": "youtube_disabled_for_testing",
    #     })
    #     return "skipped_youtube_disabled"

    in_cd, left = cooldowns.in_cooldown(pk)
    if in_cd:
        sync.update_fields(row_index, {
            "Status": "PENDING",
            "Relevance Reason": f"platform_cooldown:{pk}:{int(left)}s",
            "Downloaded": "FALSE",
        })
        return "cooldown_deferred"

    await wait_for_internet(logger=logger)

    dedupe = SheetDedupe(sync)
    logger.info(f"[{row_index}] Processing {url} (platform={pk})")

    # Allowlist
    if not registry.is_allowed(url):
        sync.update_fields(row_index, {
            "Status": "SKIPPED_NOT_ALLOWED_PLATFORM",
            "Downloaded": "FALSE",
            "Relevance": "FALSE",
            "Relevance Reason": "not_allowed_platform",
        })
        return "skipped_not_allowed"

    try:
        # ---- METADATA ----
        meta = await retry_with_backoff(
            lambda: fetch_metadata(url),
            logger=logger,
            operation_name=f"fetch_metadata:{pk}",
            retries=8,  # avoids hammering on rate-limit
        )

        # keep registry key as truth for cooldown/rotation; sheet Source can be meta.platform
        sync.update_fields(row_index, {
            "Title": meta.title,
            "Language": meta.language,
            "Video Type": meta.video_type,
            "Quality": meta.quality,
            "Duration": meta.duration,
            "Source": getattr(meta, "platform", "") or pk,
            "Device name": device,
            "Status": "METADATA_DONE",
        })

        logger.info(f"Metadata extracted: {meta.title}")

        # ---- RELEVANCE ----
        res = relevance.evaluate(meta)
        reason_text = "; ".join(res.reasons)[:450]
        if not res.is_relevant:
            logger.info(f"Skipped irrelevant: {url}")
            sync.update_fields(row_index, {
                "Relevance": "FALSE",
                "Relevance Reason": reason_text,
                "Downloaded": "FALSE",
                "Status": "SKIPPED_IRRELEVANT",
            })
            return "skipped_irrelevant"

        sync.update_fields(row_index, {"Relevance": "TRUE", "Relevance Reason": reason_text})

        # ---- DEDUPE ----
        if dedupe.is_already_downloaded(url):
            sync.update_fields(row_index, {
                "Status": "SKIPPED_DUPLICATE",
                "Downloaded": "FALSE",
                "Relevance Reason": "duplicate_already_downloaded",
            })
            return "skipped_duplicate"

        # ---- LOCK ----
        locked = sync.try_lock_url(row_index=row_index, device_name=device)
        if not locked:
            sync.update_fields(row_index, {
                "Status": "SKIPPED_DUPLICATE",
                "Downloaded": "FALSE",
                "Relevance Reason": "duplicate_locked_by_other_device",
            })
            return "skipped_duplicate"

        sync.update_fields(row_index, {"Status": "DOWNLOADING"})
        await wait_for_internet(logger=logger)

        platform_label = getattr(meta, "platform", "") or pk

        path = await retry_with_backoff(
            lambda: download_by_platform(
                platform_key=pk,
                url=meta.url,
                title=meta.title,
                platform_label=platform_label,
                base_dir=base_dir,
            ),
            logger=logger,
            operation_name=f"download:{pk}",
            retries=6,
        )

        sync.update_fields(row_index, {
            "Video Local Saved Path": path,
            "Downloaded": "TRUE",
            "Status": "DOWNLOADED",
        })
        # logger.info(f"Downloaded successfully: {url}")

        # await sleep_async(base=random.uniform(min_delay_sec, max_delay_sec))
        # return "downloaded"

        logger.info(f"Downloaded successfully: {url}")

        # ✅ platform-safe cooldown after successful download
        cooldown = random.uniform(3, 5)
        logger.info(f"[COOLDOWN] sleeping {cooldown:.1f}s after download")

        await asyncio.sleep(cooldown)

        return "downloaded"

    except Exception as e:
        msg = str(e).lower()

        networkish = any(x in msg for x in [
            "name or service not known",
            "temporary failure in name resolution",
            "network is unreachable",
            "connection reset",
            "connection aborted",
            "timed out",
            "timeout",
            "dns",
            "connection refused",
            "tls",
            "ssl",
            "remote end closed connection",
            "http error 5",
        ])

        # Rate-limit/transient -> cooldown platform, keep PENDING
        if is_retryable_transient(e) or any(x in msg for x in ["http error 429", "too many requests", "rate-limit", "try again later"]):
            cooldowns.set(
                pk,
                base_seconds=45 * 60,
                jitter_seconds=15 * 60,
                reason="rate-limit/429",
                logger=logger,
            )
            sync.update_fields(row_index, {
                "Status": "PENDING",
                "Relevance Reason": f"rate_limited_retry_later:{pk}",
                "Downloaded": "FALSE",
            })
            logger.warning(f"Rate-limited for {url}: {e}")
            return "rate_limited"

        # Bot-check/private/non-retryable -> longer cooldown, keep PENDING
        if is_non_retryable(e) or any(x in msg for x in ["sign in to confirm", "private video", "this video is unavailable"]):
            cooldowns.set(
                pk,
                base_seconds=60 * 60,
                jitter_seconds=20 * 60,
                reason="bot-check/private/non-retryable",
                logger=logger,
            )
            sync.update_fields(row_index, {
                "Status": "PENDING",
                "Relevance Reason": f"blocked_or_private_retry_later:{pk}",
                "Downloaded": "FALSE",
            })
            logger.warning(f"Blocked/private for {url}: {e}")
            return "deferred_blocked"

        if networkish:
            sync.update_fields(row_index, {
                "Status": "PENDING",
                "Relevance Reason": f"network_retry:{type(e).__name__}",
                "Downloaded": "FALSE",
            })
            return "network_retry"

        # EJS / solver missing -> skip (YT-specific but safe)
        ejs_missing = any(x in msg for x in [
            "n challenge solving failed",
            "only images are available",
            "yt_n_challenge_needs_ejs",
        ])
        if ejs_missing:
            sync.update_fields(row_index, {
                "Status": "SKIPPED_NEEDS_EJS",
                "Downloaded": "FALSE",
                "Relevance Reason": "yt_n_challenge_solver_missing",
            })
            logger.error(f"EJS/solver issue for {url}: {e}")
            return "skipped_needs_ejs"

        # Format missing -> skip
        format_missing = "requested format is not available" in msg or "format_not_available" in msg
        if format_missing:
            sync.update_fields(row_index, {
                "Status": "SKIPPED_FORMAT_NOT_AVAILABLE",
                "Downloaded": "FALSE",
                "Relevance Reason": "format_not_available",
            })
            logger.warning(f"Format selection issue for {url}: {e}")
            return "skipped_format_not_available"

        # Real failure
        sync.update_fields(row_index, {
            "Status": "FAILED",
            "Downloaded": "FALSE",
            "Relevance Reason": f"error:{type(e).__name__}",
        })
        logger.error(f"Failed processing {url}: {e}")
        logger.exception(f"[{row_index}] Failed {url}")
        return "failed"


async def main():
    sid = os.getenv("SPREADSHEET_ID", "").strip()
    tab = os.getenv("SHEET_TAB_NAME", "Sheet1").strip()
    if not sid:
        raise ValueError("SPREADSHEET_ID missing in .env")

    logger = setup_logger()
    device = socket.gethostname()
    logger.info("Worker started")
    logger.info(f"Spreadsheet={sid} Tab={tab} Device={device}")

    registry = PlatformRegistry.from_yaml()

    inc, exc = load_keywords()
    min_sec, max_sec, base_dir, poll, batch, concurrency, min_delay_sec, max_delay_sec = load_config()

    relevance = RelevancePipeline(
        KeywordFilter(include=inc, exclude=exc),
        DurationFilter(min_sec=min_sec, max_sec=max_sec),
    )

    creds = get_credentials(SCOPES)
    client = SheetsClient(creds)
    sync = SyncManager(client, spreadsheet_id=sid, tab_name=tab)

    sem = asyncio.Semaphore(concurrency)

    async def guarded(coro):
        async with sem:
            return await coro

    # platform rotation order for downloads
    platform_order = [_norm_platform_key(p) for p in load_discovery_platform_order()]
    rr_index = 0

    cooldowns = PlatformCooldowns()

    while True:
        await wait_for_internet(logger=logger)

        pending = await retry_with_backoff(
            lambda: asyncio.to_thread(sync.fetch_pending, max(batch * 3, batch)),
            logger=logger,
            operation_name="fetch_pending",
            retries=None,
        )

        if not pending:
            await asyncio.sleep(poll)
            continue

        # Group pending by platform key (registry)
        buckets: dict[str, list[TaskRow]] = {}
        for t in pending:
            pkey = _platform_key(registry, t.url)
            buckets.setdefault(pkey, []).append(t)

        selected: list[TaskRow] = []
        attempts = 0
        max_attempts = len(platform_order) * 6 + 20

        while len(selected) < batch and attempts < max_attempts:
            attempts += 1
            p = platform_order[rr_index % len(platform_order)]
            rr_index += 1

            if p not in buckets or not buckets[p]:
                continue

            in_cd, left = cooldowns.in_cooldown(p)
            if in_cd:
                logger.warning(f"[WORKER] platform={p} skipped (cooldown {_fmt_secs(left)})")
                continue

            selected.append(buckets[p].pop())

        if not selected:
            logger.warning("[WORKER] No selectable tasks (cooldowns/empty buckets). Sleeping briefly.")
            await asyncio.sleep(max(poll, 3))
            continue

        claimed = await retry_with_backoff(
            lambda: asyncio.to_thread(sync.claim, selected, device),
            logger=logger,
            operation_name="claim",
            retries=None,
        )

        random.shuffle(claimed)

        tasks = [
            asyncio.create_task(
                guarded(
                    process_one(
                        sync=sync,
                        registry=registry,
                        relevance=relevance,
                        base_dir=base_dir,
                        row_index=t.row_index,
                        url=t.url,
                        device=device,
                        logger=logger,
                        cooldowns=cooldowns,
                        min_delay_sec=min_delay_sec,
                        max_delay_sec=max_delay_sec,
                    )
                )
            )
            for t in claimed
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        for r in results:
            if isinstance(r, Exception):
                logger.error(f"Task failed: {r}", exc_info=r)

        await asyncio.sleep(1)


if __name__ == "__main__":
    asyncio.run(main())