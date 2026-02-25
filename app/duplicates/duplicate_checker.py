from __future__ import annotations

from app.duplicates.local_cache import DedupeCache
from app.sync.sync_manager import SyncManager


class DuplicateChecker:
    def __init__(self, sync: SyncManager, cache: DedupeCache | None = None):
        self.sync = sync
        self.cache = cache or DedupeCache(ttl_sec=60)

    def refresh_cache_if_needed(self) -> None:
        if not self.cache.should_refresh():
            return
        # Pull URLs from the sheet and build a set
        rows = self.sync.fetch_all_rows()
        if not rows or len(rows) < 2:
            self.cache.update(set())
            return

        header = rows[0]
        hmap = {h.strip(): i for i, h in enumerate(header) if h and h.strip()}
        url_idx = hmap.get("Video URL")

        urls: set[str] = set()
        for r in rows[1:]:
            if url_idx is None or url_idx >= len(r):
                continue
            u = (r[url_idx] or "").strip()
            if u:
                urls.add(u)

        self.cache.update(urls)

    def is_duplicate(self, url: str, current_row_index: int | None = None) -> bool:
        # Note: current_row_index not used in MVP; we dedupe by URL globally.
        self.refresh_cache_if_needed()
        return self.cache.contains(url)