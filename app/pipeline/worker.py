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
from app.downloader.ytdlp_downloader import download_video
from app.duplicates.sheet_dedupe import SheetDedupe
from app.core.logger import setup_logger
from app.core.network import wait_for_internet
from app.core.retry import retry_with_backoff

from app.sync.oauth import get_credentials
from app.sync.sheets_client import SheetsClient
from app.sync.sync_manager import SyncManager

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

load_dotenv()

def load_keywords():
    data = yaml.safe_load(open("configs/keywords.yaml", "r", encoding="utf-8")) or {}
    return tuple(data.get("include_keywords", []) or []), tuple(data.get("exclude_keywords", []) or [])


def load_config():
    cfg = yaml.safe_load(open("configs/config.yaml", "r", encoding="utf-8")) or {}
    f = cfg.get("filtering", {}) or {}
    d = cfg.get("downloads", {}) or {}
    return f.get("min_duration_sec"), f.get("max_duration_sec"), d.get("base_dir", "data/downloads")


def _is_rate_limited_message(msg: str) -> bool:
    return any(x in msg for x in [
        "rate-limited by youtube",
        "too many requests",
        "http error 429",
        "try again later",
    ])


async def process_one(
    sync: SyncManager,
    registry: PlatformRegistry,
    relevance: RelevancePipeline,
    base_dir: str,
    row_index: int,
    url: str,
    device: str,
    logger,
    cooldown_state: dict | None = None,
):

    if cooldown_state and cooldown_state.get("enabled") and time.monotonic() < cooldown_state.get("until", 0.0):
        sync.update_fields(row_index, {
            "STATUS": "PENDING",
            "Relevance Reason": "global_cooldown_active",
            "Downloaded": "FALSE",
        })
        return "cooldown_deferred"

    await wait_for_internet(logger=logger)
    
    dedupe = SheetDedupe(sync)
    # logger.info(f"Processing URL: {url}")

    logger.info(f"[{row_index}] Processing {url}")
    # Safety gate: allowlist
    if not registry.is_allowed(url):
        sync.update_fields(row_index, {"STATUS": "SKIPPED_NOT_ALLOWED_PLATFORM", "Downloaded": "FALSE", "Relevance": "FALSE"})
        return "skipped_not_allowed"

    try:
        meta = await retry_with_backoff(
            lambda: fetch_metadata(url),
            logger=logger,
            operation_name="fetch_metadata",
            retries=None,
        )

        # Update metadata fields early
        sync.update_fields(row_index, {
            "Title": meta.title,
            "Language": meta.language,
            "Video Type": meta.video_type,
            "Quality": meta.quality,
            "Duration": meta.duration,
            "Source": meta.platform,      # platform only (as you wanted)
            "Device name": device,
            "STATUS": "METADATA_DONE",
        })

        logger.info(f"Metadata extracted: {meta.title}")

        # Relevance
        res = relevance.evaluate(meta)
        reason_text = "; ".join(res.reasons)[:450]
        if not res.is_relevant:
            logger.info(f"Skipped irrelevant: {url}")
            sync.update_fields(row_index, {
                "Relevance": "FALSE",
                "Relevance Reason": reason_text,
                "Downloaded": "FALSE",
                "STATUS": "SKIPPED_IRRELEVANT",
            })
            return "skipped_irrelevant"

        sync.update_fields(row_index, {"Relevance": "TRUE", "Relevance Reason": reason_text})

        # 1) Global skip if already downloaded anywhere (sheet-backed)
        if dedupe.is_already_downloaded(url):
            sync.update_fields(row_index, {
                "STATUS": "SKIPPED_DUPLICATE",
                "Downloaded": "FALSE",
                "Relevance Reason": "duplicate_already_downloaded",
            })
            return "skipped_duplicate"

        # 2) Acquire a lock before downloading to avoid concurrent multi-device duplicates
        locked = sync.try_lock_url(row_index=row_index, device_name=device)
        if not locked:
            sync.update_fields(row_index, {
                "STATUS": "SKIPPED_DUPLICATE",
                "Downloaded": "FALSE",
                "Relevance Reason": "duplicate_locked_by_other_device",
            })
            return "skipped_duplicate"

        # Optional: visible state
        sync.update_fields(row_index, {"STATUS": "DOWNLOADING"})

        await wait_for_internet(logger=logger)

        # Download locally
        path = await retry_with_backoff(
            lambda: download_video(
                url=meta.url,
                title=meta.title,
                platform=meta.platform,
                base_dir=base_dir,
            ),
            logger=logger,
            operation_name="download_video",
        )


        # path = await download_video(
        #     url=meta.url,
        #     title=meta.title,
        #     platform=meta.platform,
        #     base_dir=base_dir,
        # )

        sync.update_fields(row_index, {
            "Video  Local Saved Path": path,
            "Downloaded": "TRUE",
            "STATUS": "DOWNLOADED",
        })
        logger.info(f"Downloaded successfully: {url}")
        return "downloaded"

    except Exception as e:
        msg = str(e).lower()

        authish = any(x in msg for x in [
            "could not copy chrome cookie database",
            "failed to decrypt with dpapi",
            "sign in to confirm",
            "--cookies-from-browser",
            "--cookies for the authentication",
        ])

        # crude but effective network detection
        networkish = any(x in msg for x in [
            "name or service not known",
            "temporary failure in name resolution",
            "network is unreachable",
            "connection reset",
            "connection aborted",
            "timed out",
            "timeout",
            "dns",
            "http error 5",
        ])

        rate_limited = _is_rate_limited_message(msg)

        ejs_missing = any(x in msg for x in [
            "n challenge solving failed",
            "only images are available",
            # "requested format is not available",
        ])

        if networkish:
            # Leave task for retry later
            sync.update_fields(row_index, {
                "STATUS": "PENDING",
                "Relevance Reason": f"network_retry:{type(e).__name__}",
                "Downloaded": "FALSE",
            })
            return "network_retry"

        if rate_limited:
            sync.update_fields(row_index, {
                "STATUS": "PENDING",
                "Relevance Reason": "yt_rate_limited_retry_later",
                "Downloaded": "FALSE",
            })
            if cooldown_state and cooldown_state.get("enabled"):
                sec = max(int(cooldown_state.get("sec", 1800)), 1)
                new_until = time.monotonic() + sec
                if new_until > cooldown_state.get("until", 0.0):
                    cooldown_state["until"] = new_until
                    logger.warning(f"Entering global cooldown for {sec}s (first rate-limit hit)")
            logger.warning(f"Rate-limited for {url}: {e}")
            return "rate_limited"
        
        if authish:
            sync.update_fields(row_index, {
                "STATUS": "SKIPPED_AUTH_REQUIRED",
                "Downloaded": "FALSE",
                "Relevance Reason": "yt_auth_required_or_cookie_access_failed",
            })
            logger.error(f"Auth/cookies issue for {url}: {e}")
            return "skipped_auth_required"

        if ejs_missing:
            sync.update_fields(row_index, {
                "STATUS": "SKIPPED_NEEDS_EJS",
                "Downloaded": "FALSE",
                "Relevance Reason": "yt_n_challenge_solver_missing",
            })
            logger.error(f"EJS/solver issue for {url}: {e}")
            return "skipped_needs_ejs"

        if "yt_n_challenge_needs_ejs" in msg:
            sync.update_fields(row_index, {
                "STATUS": "SKIPPED_NEEDS_EJS",
                "Downloaded": "FALSE",
                "Relevance Reason": "yt_n_challenge_solver_missing",
            })
            return "skipped_needs_ejs"

        # Real failure (not network)
        sync.update_fields(row_index, {
            "STATUS": "FAILED",
            "Downloaded": "FALSE",
            "Relevance Reason": f"error:{type(e).__name__}",
        })

        format_missing = "requested format is not available" in msg or "format_not_available" in msg

        if format_missing:
            sync.update_fields(row_index, {
                "STATUS": "SKIPPED_FORMAT_NOT_AVAILABLE",
                "Downloaded": "FALSE",
                "Relevance Reason": "format_not_available",
            })
            logger.warning(f"Format selection issue for {url}: {e}")
            return "skipped_format_not_available"

        # sync.update_fields(row_index, {"STATUS": "FAILED", "Downloaded": "FALSE","Relevance Reason": f"error:{type(e).__name__}"})

        logger.error(f"Failed processing {url}: {e}")
        logger.exception(f"[{row_index}] Failed {url}")
        return "failed"


async def main():
    sid = os.getenv("SPREADSHEET_ID", "").strip()
    tab = os.getenv("SHEET_TAB_NAME", "Sheet1").strip()
    poll = int(os.getenv("POLL_INTERVAL_SEC", "3"))
    batch = int(os.getenv("BATCH_SIZE", "10"))
    concurrency = int(os.getenv("CONCURRENCY", "3"))
    cooldown_enabled = os.getenv("YT_RATE_LIMIT_COOLDOWN_ENABLED", "true").strip().lower() in {"1", "true", "yes", "on"}
    cooldown_sec = int(os.getenv("YT_RATE_LIMIT_COOLDOWN_SEC", "1800"))
    cooldown_state = {
        "enabled": cooldown_enabled,
        "sec": max(cooldown_sec, 1),
        "until": 0.0,
    }

    logger = setup_logger()
    logger.info("Worker started")
    logger.info(
        f"Rate-limit cooldown enabled={cooldown_state['enabled']} cooldown_sec={cooldown_state['sec']}"
    )

    if not sid:
        raise ValueError("SPREADSHEET_ID missing in .env")

    device = socket.gethostname()
    logger.info(f"Spreadsheet={sid} Tab={tab} Device={device}")

    # filters + registry
    registry = PlatformRegistry.from_yaml()
    inc, exc = load_keywords()
    min_sec, max_sec, base_dir = load_config()

    relevance = RelevancePipeline(
        KeywordFilter(include=inc, exclude=exc),
        DurationFilter(min_sec=min_sec, max_sec=max_sec),
    )

    # sheets
    creds = get_credentials(SCOPES)
    client = SheetsClient(creds)
    sync = SyncManager(client, spreadsheet_id=sid, tab_name=tab)

    sem = asyncio.Semaphore(concurrency)

    async def guarded(coro):
        async with sem:
            return await coro

    while True:
        now = time.monotonic()
        if cooldown_state["enabled"] and now < cooldown_state["until"]:
            remaining = int(cooldown_state["until"] - now)
            logger.warning(f"Global cooldown active for {remaining}s due to YouTube rate limiting")
            await asyncio.sleep(max(remaining, 1))
            continue

        # Ensure internet before talking to Sheets
        await wait_for_internet(logger=logger)
        pending = await retry_with_backoff(
            lambda: asyncio.to_thread(sync.fetch_pending, batch),
            logger=logger,
            operation_name="fetch_pending"
        )
        
        if not pending:
            await asyncio.sleep(poll)
            continue

        claimed = await retry_with_backoff(
            lambda: asyncio.to_thread(sync.claim, pending, device),
            logger=logger,
            operation_name="claim"
        )

        random.shuffle(claimed)

        tasks = [
            asyncio.create_task(
                guarded(process_one(sync, registry, relevance, base_dir, t.row_index, t.url, device, logger, cooldown_state))
            )
            for t in claimed
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # optional: log exceptions clearly
        for r in results:
            if isinstance(r, Exception):
                logger.error(f"Task failed: {r}", exc_info=r)

        await asyncio.sleep(1)

if __name__ == "__main__":
    asyncio.run(main())
