from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional

from app.sync.sheets_client import SheetsClient
from app.sync.sheet_schema import build_header_map, _norm, col_to_a1, COLUMNS


@dataclass
class TaskRow:
    row_index: int          # 1-based row number in sheet
    url: str
    status: str


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


class SyncManager:
    """
    Distributed coordination using:
      - STATUS
      - Device name
      - Downloaded
    """

    def __init__(self, client: SheetsClient, spreadsheet_id: str, tab_name: str = "Sheet1"):
        self.client = client
        self.spreadsheet_id = spreadsheet_id
        self.tab = tab_name

    def fetch_all(self) -> List[List[Any]]:
        # wide range for safety; header-driven
        return self.client.get_values(self.spreadsheet_id, f"{self.tab}!A1:Z")

    def _norm(self, s: str) -> str:
        return " ".join((s or "").strip().split()).lower()

    def ensure_headers(self, rewrite_if_mismatch: bool = True) -> None:
        values = self.fetch_all()
        if not values:
            self.client.append_values(self.spreadsheet_id, f"{self.tab}!A1", [COLUMNS])
            return

        current = values[0]
        expected = COLUMNS

        # Normalize both
        cur_norm = [self._norm(x) for x in current]
        exp_norm = [self._norm(x) for x in expected]

        # If same length and normalized equal -> OK
        if len(cur_norm) >= len(exp_norm) and cur_norm[: len(exp_norm)] == exp_norm:
            return

        if not rewrite_if_mismatch:
            raise RuntimeError(
                f"Header mismatch.\nCurrent: {current}\nExpected: {expected}\n"
                "Set rewrite_if_mismatch=True to auto-fix."
            )

        # Rewrite header row A1:O1 (based on expected length)
        updates = [{
            "range": f"{self.tab}!A1:{chr(65+len(expected)-1)}1",
            "values": [expected],
        }]
        self.client.batch_update_values(self.spreadsheet_id, updates)

    def append_pending_urls(self, urls: list[str], device_name: str = "") -> int:
        values = self.fetch_all()
        if not values:
            raise RuntimeError("Sheet is empty; run init headers first.")

        header = values[0]
        hmap = build_header_map(header)
        url_idx = hmap.get("Video URL")

        existing: set[str] = set()
        if url_idx is not None:
            for r in values[1:]:
                if url_idx < len(r):
                    u = (r[url_idx] or "").strip()
                    if u:
                        existing.add(u)

        to_append: list[list[Any]] = []
        for u in urls:
            u = (u or "").strip()
            if not u or u in existing:
                continue

            new_row = [""] * len(header)
            if "Video URL" in hmap: new_row[hmap["Video URL"]] = u
            if "STATUS" in hmap: new_row[hmap["STATUS"]] = "PENDING"
            if "Downloaded" in hmap: new_row[hmap["Downloaded"]] = "FALSE"
            # Discovery device should not occupy downloader device column
            if "Discovered By" in hmap and device_name: new_row[hmap["Discovered By"]] = device_name
            if "Created Datetime" in hmap: new_row[hmap["Created Datetime"]] = now_iso()

            to_append.append(new_row)
            existing.add(u)

        if not to_append:
            return 0

        self.client.append_values(self.spreadsheet_id, f"{self.tab}!A1", to_append)
        return len(to_append)

    def fetch_pending(self, limit: int = 20) -> list[TaskRow]:
        values = self.fetch_all()
        if not values or len(values) < 2:
            return []

        header = values[0]
        hmap = build_header_map(header)

        def get(row: list[Any], col: str) -> str:
            idx = hmap.get(_norm(col))
            if idx is None or idx >= len(row):
                return ""
            return (row[idx] or "").strip()

        out: list[TaskRow] = []
        for i, row in enumerate(values[1:], start=2):
            url = get(row, "Video URL")
            status = get(row, "STATUS")
            if not url:
                continue
            downloaded = get(row, "Downloaded").upper()
            status_u = status.upper()

            terminal = {
                "DOWNLOADED",
                "SKIPPED_IRRELEVANT",
                "SKIPPED_DUPLICATE",
                "SKIPPED_NOT_ALLOWED_PLATFORM",
                "FAILED",
            }

            if downloaded == "TRUE":
                continue
            if status_u in terminal:
                continue

            # treat blank as pending
            if status_u in ("", "PENDING"):
                out.append(TaskRow(row_index=i, url=url, status=status))
        return out

    def claim(self, tasks: list[TaskRow], device_name: str) -> list[TaskRow]:
        values = self.fetch_all()
        header = values[0]
        hmap = build_header_map(header)

        updates: list[Dict[str, Any]] = []
        for t in tasks:
            if "STATUS" in hmap:
                updates.append({"range": f"{self.tab}!{col_to_a1(hmap[_norm('STATUS')])}{t.row_index}", "values": [["IN_PROGRESS"]]})
            if "Device name" in hmap:
                updates.append({"range": f"{self.tab}!{col_to_a1(hmap[_norm('Device name')])}{t.row_index}", "values": [[device_name]]})
            if "Created Datetime" in hmap:
                updates.append({"range": f"{self.tab}!{col_to_a1(hmap[_norm('Created Datetime')])}{t.row_index}", "values": [[now_iso()]]})

        if updates:
            self.client.batch_update_values(self.spreadsheet_id, updates)

        # return as claimed
        for t in tasks:
            t.status = "IN_PROGRESS"
        return tasks

    def update_fields(self, row_index: int, fields: dict[str, Any]) -> None:
        values = self.fetch_all()
        header = values[0]
        hmap = build_header_map(header)

        updates: list[Dict[str, Any]] = []
        for col, val in fields.items():
            idx = hmap.get(_norm(col))
            if idx is None:
                continue
            updates.append({"range": f"{self.tab}!{col_to_a1(idx)}{row_index}", "values": [[val]]})

        if updates:
            self.client.batch_update_values(self.spreadsheet_id, updates)