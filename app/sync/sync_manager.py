from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List

from app.sync.sheets_client import SheetsClient
from app.sync.sheet_schema import build_header_map, _norm, col_to_a1, COLUMNS


@dataclass
class TaskRow:
    row_index: int          # 1-based row number in sheet
    url: str
    status: str
    discovery_query: str = ""   # ✅ NEW


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


class SyncManager:
    """
    Distributed coordination using:
      - Status
      - Device name
      - Downloaded
    """

    def __init__(self, client: SheetsClient, spreadsheet_id: str, tab_name: str = "Sheet1"):
        self.client = client
        self.spreadsheet_id = spreadsheet_id
        self.tab = tab_name

    def fetch_all(self) -> List[List[Any]]:
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

        cur_norm = [self._norm(x) for x in current]
        exp_norm = [self._norm(x) for x in expected]

        if len(cur_norm) >= len(exp_norm) and cur_norm[: len(exp_norm)] == exp_norm:
            return

        if not rewrite_if_mismatch:
            raise RuntimeError(
                f"Header mismatch.\nCurrent: {current}\nExpected: {expected}\n"
                "Set rewrite_if_mismatch=True to auto-fix."
            )

        # rewrite header row exactly to expected
        end_col = col_to_a1(len(expected) - 1)
        updates = [{
            "range": f"{self.tab}!A1:{end_col}1",
            "values": [expected],
        }]
        self.client.batch_update_values(self.spreadsheet_id, updates)

    def append_pending_urls(self, urls: list[str], device_name: str = "", discovery_query: str = "") -> int:
        values = self.fetch_all()
        if not values:
            raise RuntimeError("Sheet is empty; run init headers first.")

        header = values[0]
        hmap = build_header_map(header)

        url_idx = hmap.get(_norm("Video URL"))

        # ✅ IMPORTANT: your schema uses "Status" (not STATUS), but we support both
        status_idx = hmap.get(_norm("Status"))
        if status_idx is None:
            status_idx = hmap.get(_norm("STATUS"))

        if url_idx is None or status_idx is None:
            raise RuntimeError(
                "Sheet header missing required columns. "
                f"Have keys={list(hmap.keys())}"
            )

        discovered_by_idx = hmap.get(_norm("Discovered By"))
        downloaded_idx = hmap.get(_norm("Downloaded"))
        created_idx = hmap.get(_norm("Created Datetime"))
        dq_idx = hmap.get(_norm("Discovery Query"))  # ✅ NEW

        existing: set[str] = set()
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
            new_row[url_idx] = u
            new_row[status_idx] = "PENDING"

            if downloaded_idx is not None:
                new_row[downloaded_idx] = "FALSE"
            if created_idx is not None:
                new_row[created_idx] = now_iso()
            if discovered_by_idx is not None and device_name:
                new_row[discovered_by_idx] = device_name

            # ✅ write query into the row at discovery time
            if dq_idx is not None and discovery_query:
                new_row[dq_idx] = discovery_query

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

            # ✅ support both spellings
            status = get(row, "Status") or get(row, "STATUS")
            dq = get(row, "Discovery Query")

            if not url:
                continue

            downloaded = get(row, "Downloaded").upper()
            status_u = (status or "").upper()

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

            if status_u in ("", "PENDING"):
                out.append(TaskRow(row_index=i, url=url, status=status, discovery_query=dq))

            if len(out) >= limit:
                break

        return out

    def claim(self, tasks: list[TaskRow], device_name: str) -> list[TaskRow]:
        values = self.fetch_all()
        header = values[0]
        hmap = build_header_map(header)

        status_key = _norm("Status")
        device_key = _norm("Device name")
        created_key = _norm("Created Datetime")

        updates: list[Dict[str, Any]] = []
        for t in tasks:
            if status_key in hmap:
                updates.append({
                    "range": f"{self.tab}!{col_to_a1(hmap[status_key])}{t.row_index}",
                    "values": [["IN_PROGRESS"]],
                })
            if device_key in hmap:
                updates.append({
                    "range": f"{self.tab}!{col_to_a1(hmap[device_key])}{t.row_index}",
                    "values": [[device_name]],
                })
            if created_key in hmap:
                updates.append({
                    "range": f"{self.tab}!{col_to_a1(hmap[created_key])}{t.row_index}",
                    "values": [[now_iso()]],
                })

        if updates:
            self.client.batch_update_values(self.spreadsheet_id, updates)

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

    def try_lock_url(self, row_index: int, device_name: str) -> bool:
        values = self.fetch_all()
        header = values[0]
        hmap = build_header_map(header)

        lock_idx = hmap.get(_norm("URL Lock"))
        if lock_idx is None:
            return True

        row = values[row_index - 1] if row_index - 1 < len(values) else []
        current = ""
        if lock_idx < len(row):
            current = (row[lock_idx] or "").strip()

        if current and current != device_name:
            return False
        if current == device_name:
            return True

        self.update_fields(row_index, {"URL Lock": device_name})
        return True