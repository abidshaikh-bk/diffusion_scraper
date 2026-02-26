from __future__ import annotations
from dataclasses import dataclass
from typing import Any
from app.sync.sync_manager import SyncManager
from app.sync.sheet_schema import build_header_map


@dataclass
class SheetDedupe:
    sync: SyncManager
    ttl_sec: int = 60
    _cache_urls: set[str] = None
    _cache_loaded_at: float = 0.0

    def _load(self) -> None:
        import time
        now = time.time()
        if self._cache_urls is not None and (now - self._cache_loaded_at) < self.ttl_sec:
            return

        rows = self.sync.fetch_all()
        if not rows or len(rows) < 2:
            self._cache_urls = set()
            self._cache_loaded_at = now
            return

        header = rows[0]
        hmap = build_header_map(header)
        url_i = hmap.get("Video URL")
        downloaded_i = hmap.get("Downloaded")
        status_i = hmap.get("STATUS")

        urls: set[str] = set()
        for r in rows[1:]:
            if url_i is None or url_i >= len(r):
                continue
            url = (r[url_i] or "").strip()
            if not url:
                continue

            downloaded = (r[downloaded_i] or "").strip().upper() if downloaded_i is not None and downloaded_i < len(r) else ""
            status = (r[status_i] or "").strip().upper() if status_i is not None and status_i < len(r) else ""

            if downloaded == "TRUE" or status == "DOWNLOADED":
                urls.add(url)

        self._cache_urls = urls
        self._cache_loaded_at = now

    def is_already_downloaded(self, url: str) -> bool:
        self._load()
        return url in (self._cache_urls or set())