from __future__ import annotations

import asyncio
import socket
import yaml

from app.auth.oauth import get_credentials
from app.core.config import AppConfig
from app.core.utils import format_source
from app.scraper.metadata_extractor import extract_metadata

from app.filtering.keyword_filter import KeywordFilter
from app.filtering.duration_filter import DurationFilter
from app.filtering.relevance_pipeline import RelevancePipeline

from app.duplicates.duplicate_checker import DuplicateChecker
from app.sync.sheets_client import SheetsClient
from app.sync.sync_manager import SyncManager

from app.downloader.yt_dlp_downloader import download_video

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]


def load_keywords(path: str = "configs/keywords.yaml") -> tuple[list[str], list[str]]:
    data = yaml.safe_load(open(path, "r", encoding="utf-8")) or {}
    return data.get("include_keywords", []) or [], data.get("exclude_keywords", []) or []


def load_filter_cfg(path: str = "configs/config.yaml") -> tuple[int | None, int | None]:
    data = yaml.safe_load(open(path, "r", encoding="utf-8")) or {}
    f = (data.get("filtering") or {})
    return f.get("min_duration_sec"), f.get("max_duration_sec")


async def worker_tick(
    sync: SyncManager,
    device_name: str,
    batch_size: int,
    relevance: RelevancePipeline,
    dupes: DuplicateChecker,
) -> None:
    pending = sync.fetch_pending(limit=batch_size)
    if not pending:
        return

    claimed = sync.claim_rows(pending, device_name=device_name)

    for row in claimed:
        try:
            meta = await extract_metadata(row.video_url)

            # 1) write metadata first
            fields = {
                "Title": meta.title or "",
                "Language": meta.language or "",
                "Video Type": meta.ext or "",
                "Quality": meta.quality or "",
                "Duration": meta.duration_hhmmss or "",
                "Source": format_source(meta.platform or "Unknown", None),
                "STATUS": "METADATA_DONE",
            }
            sync.update_row_fields(row.row_index, fields)

            # 2) relevance
            rel = relevance.evaluate(
                title=meta.title,
                description=None,              # (we’ll add description in next iteration if needed)
                duration_hhmmss=meta.duration_hhmmss,
            )
            if not rel.is_relevant:
                sync.update_row_fields(
                    row.row_index,
                    {
                        "Relevance": "FALSE",
                        "Downloaded": "FALSE",
                        "STATUS": "SKIPPED_IRRELEVANT",
                    },
                )
                continue
            else:
                sync.update_row_fields(row.row_index, {"Relevance": "TRUE"})

            # 3) duplicate
            if dupes.is_duplicate(row.video_url, current_row_index=row.row_index):
                sync.update_row_fields(
                    row.row_index,
                    {
                        "Downloaded": "FALSE",
                        "STATUS": "SKIPPED_DUPLICATE",
                    },
                )
                continue

            # 4) Download
            try:
                local_path = await download_video(
                    url=row.video_url,
                    title=meta.title or "video",
                    platform=meta.platform or "Other",
                    ext=meta.ext,
                )

                sync.update_row_fields(
                    row.row_index,
                    {
                        "Video  Local Saved Path": local_path,
                        "Downloaded": "TRUE",
                        "STATUS": "DOWNLOADED",
                    },
                )

            except Exception:
                sync.update_row_fields(
                    row.row_index,
                    {
                        "Downloaded": "FALSE",
                        "STATUS": "FAILED",
                    },
                )

        except Exception as e:
            sync.update_row_fields(
                row.row_index,
                {
                    "STATUS": "FAILED",
                    "Downloaded": "FALSE",
                },
            )


async def main():
    cfg = AppConfig.from_env()
    device_name = socket.gethostname()

    include_kw, exclude_kw = load_keywords()
    min_sec, max_sec = load_filter_cfg()

    relevance = RelevancePipeline(
        keyword_filter=KeywordFilter(tuple(include_kw), tuple(exclude_kw)),
        duration_filter=DurationFilter(min_sec=min_sec, max_sec=max_sec),
    )

    creds = get_credentials(SCOPES)
    client = SheetsClient(creds)
    sync = SyncManager(client, spreadsheet_id=cfg.spreadsheet_id, tab_name=cfg.sheet_tab_name)

    dupes = DuplicateChecker(sync=sync)  # TTL cache inside

    while True:
        await worker_tick(sync, device_name, cfg.batch_size, relevance, dupes)
        await asyncio.sleep(cfg.poll_interval_sec)


if __name__ == "__main__":
    asyncio.run(main())