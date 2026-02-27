from __future__ import annotations

import asyncio
import os
import socket
import yaml
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


async def process_one(sync: SyncManager, registry: PlatformRegistry, relevance: RelevancePipeline, base_dir: str, row_index: int, url: str, device: str, logger):

    await wait_for_internet()
    
    dedupe = SheetDedupe(sync)
    # logger.info(f"Processing URL: {url}")

    logger.info(f"[{row_index}] Processing {url}")
    # Safety gate: allowlist
    if not registry.is_allowed(url):
        sync.update_fields(row_index, {"STATUS": "SKIPPED_NOT_ALLOWED_PLATFORM", "Downloaded": "FALSE", "Relevance": "FALSE"})
        return

    try:
        meta = await retry_with_backoff(lambda: fetch_metadata(url))

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
            return

        sync.update_fields(row_index, {"Relevance": "TRUE", "Relevance Reason": reason_text})

        # 1) Global skip if already downloaded anywhere (sheet-backed)
        if dedupe.is_already_downloaded(url):
            sync.update_fields(row_index, {
                "STATUS": "SKIPPED_DUPLICATE",
                "Downloaded": "FALSE",
                "Relevance Reason": "duplicate_already_downloaded",
            })
            return

        # 2) Acquire a lock before downloading to avoid concurrent multi-device duplicates
        locked = sync.try_lock_url(row_index=row_index, device_name=device)
        if not locked:
            sync.update_fields(row_index, {
                "STATUS": "SKIPPED_DUPLICATE",
                "Downloaded": "FALSE",
                "Relevance Reason": "duplicate_locked_by_other_device",
            })
            return

        # Optional: visible state
        sync.update_fields(row_index, {"STATUS": "DOWNLOADING"})

        await wait_for_internet()

        # Download locally
        path = await retry_with_backoff(lambda: download_video(
            url=meta.url,
            title=meta.title,
            platform=meta.platform,
            base_dir=base_dir,
        ))


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

    except Exception as e:
        msg = str(e).lower()

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

        if networkish:
            # Leave task for retry later
            sync.update_fields(row_index, {
                "STATUS": "PENDING",
                "Relevance Reason": f"network_retry:{type(e).__name__}",
                "Downloaded": "FALSE",
            })
            return

        # Real failure (not network)
        sync.update_fields(row_index, {
            "STATUS": "FAILED",
            "Downloaded": "FALSE",
            "Relevance Reason": f"error:{type(e).__name__}",
        })

        # sync.update_fields(row_index, {"STATUS": "FAILED", "Downloaded": "FALSE","Relevance Reason": f"error:{type(e).__name__}"})

        logger.error(f"Failed processing {url}: {e}")
        logger.exception(f"[{row_index}] Failed {url}")


async def main():
    sid = os.getenv("SPREADSHEET_ID", "").strip()
    tab = os.getenv("SHEET_TAB_NAME", "Sheet1").strip()
    poll = int(os.getenv("POLL_INTERVAL_SEC", "3"))
    batch = int(os.getenv("BATCH_SIZE", "10"))
    concurrency = int(os.getenv("CONCURRENCY", "3"))

    logger = setup_logger()
    logger.info("Worker started")

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

    async def guarded(task):
        async with sem:
            await task

    while True:
        # Ensure internet before talking to Sheets
        await wait_for_internet()
        pending = await retry_with_backoff(lambda: asyncio.to_thread(sync.fetch_pending, batch))
        
        if not pending:
            await asyncio.sleep(poll)
            continue

        claimed = await retry_with_backoff(lambda: asyncio.to_thread(sync.claim, pending, device))

        # process concurrently (async downloads/yt-dlp subprocesses)
        coros = [
            guarded(process_one(sync, registry, relevance, base_dir, t.row_index, t.url, device, logger))
            for t in claimed
        ]
        await asyncio.gather(*coros, return_exceptions=True)

        await asyncio.sleep(1)

if __name__ == "__main__":
    asyncio.run(main())