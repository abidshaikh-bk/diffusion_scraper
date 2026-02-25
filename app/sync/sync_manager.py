from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from app.models.sheet_row import COLUMNS, COL_INDEX, SheetRow
from app.sync.sheets_client import SheetsClient


class SyncManager:
    """
    Operates on a single tab.
    Uses STATUS + Device name for claiming.
    """

    def __init__(self, client: SheetsClient, spreadsheet_id: str, tab_name: str = "Sheet1"):
        self.client = client
        self.spreadsheet_id = spreadsheet_id
        self.tab = tab_name

    def _a1(self, col_idx_0: int, row_idx_1: int) -> str:
        # col index (0-based) -> Excel letters
        col = ""
        n = col_idx_0 + 1
        while n:
            n, r = divmod(n - 1, 26)
            col = chr(65 + r) + col
        return f"{self.tab}!{col}{row_idx_1}"

    def fetch_all_rows(self):
        # NOTE: get a wide enough range; easiest is A1:Z for now
        rng = f"{self.tab}!A1:Z"
        return self.client.get_values(self.spreadsheet_id, rng)

    def _header_map(self, header_row: list[str]) -> dict[str, int]:
        return {h.strip(): i for i, h in enumerate(header_row) if h and h.strip()}

    def fetch_pending(self, limit: int = 50) -> List[SheetRow]:
        values = self.fetch_all_rows()
        if not values:
            return []

        header = values[0]
        hmap = self._header_map(header)
        # Assume header matches COLUMNS; if not, we still try by index.
        rows = values[1:]
        pending: List[SheetRow] = []

        def get(padded_row, col_name: str) -> str:
            idx = hmap.get(col_name)
            if idx is None or idx >= len(padded_row):
                return ""
            return padded_row[idx] or ""

        for i, row in enumerate(rows, start=2):  # sheet row index starts at 2
            # pad row
            padded = list(row) + [""] * (len(header) - len(row))
            # status = padded[COL_INDEX["STATUS"]] if COL_INDEX["STATUS"] < len(padded) else ""
            # url = padded[COL_INDEX["Video URL"]] if COL_INDEX["Video URL"] < len(padded) else ""
            url = get(padded, "Video URL").strip()
            status = get(paded, "STATUS").strip()

            if not url:
                continue

            if (status or "").strip() in ("", "PENDING"):
                pending.append(
                    SheetRow(
                        row_index=i,
                        sr_no=padded[COL_INDEX["Sr. No"]] or None,
                        title=padded[COL_INDEX["Title"]] or None,
                        language=padded[COL_INDEX["Language"]] or None,
                        video_type=padded[COL_INDEX["Video Type"]] or None,
                        quality=padded[COL_INDEX["Quality"]] or None,
                        video_url=url,
                        local_path=padded[COL_INDEX["Video  Local Saved Path"]] or None,
                        created_datetime=padded[COL_INDEX["Created Datetime"]] or None,
                        status=status or None,
                        video_country=padded[COL_INDEX["Video  Country"]] or None,
                        source=padded[COL_INDEX["Source"]] or None,
                        duration=padded[COL_INDEX["Duration"]] or None,
                        relevance=padded[COL_INDEX["Relevance"]] or None,
                        downloaded=padded[COL_INDEX["Downloaded"]] or None,
                        device_name=padded[COL_INDEX["Device name"]] or None,
                    )
                )

            if len(pending) >= limit:
                break

        return pending

    def claim_rows(self, rows: List[SheetRow], device_name: str) -> List[SheetRow]:
        """
        Claim by setting STATUS=IN_PROGRESS and Device name=<device>.
        NOTE: This is a practical MVP. If two devices claim same row at same time,
        last-write wins. We’ll reduce collisions by small batch sizes + short polling.
        """
        updates: List[Dict[str, Any]] = []
        claimed: List[SheetRow] = []

        for r in rows:
            r.status = "IN_PROGRESS"
            r.device_name = device_name
            if not r.created_datetime:
                r.created_datetime = SheetRow.now_iso()

            # Update just STATUS, Device name, Created Datetime
            status_cell = self._a1(COL_INDEX["STATUS"], r.row_index)
            device_cell = self._a1(COL_INDEX["Device name"], r.row_index)
            created_cell = self._a1(COL_INDEX["Created Datetime"], r.row_index)

            updates.append({"range": status_cell, "values": [[r.status]]})
            updates.append({"range": device_cell, "values": [[r.device_name]]})
            updates.append({"range": created_cell, "values": [[r.created_datetime]]})
            claimed.append(r)

        if updates:
            self.client.batch_update_values(self.spreadsheet_id, updates)

        return claimed

    def update_row_fields(self, row_index: int, fields: Dict[str, Any]) -> None:
        updates: List[Dict[str, Any]] = []
        for col_name, value in fields.items():
            if col_name not in COL_INDEX:
                continue
            cell = self._a1(COL_INDEX[col_name], row_index)
            updates.append({"range": cell, "values": [[value]]})

        if updates:
            self.client.batch_update_values(self.spreadsheet_id, updates)

    def append_pending_urls(self, urls: list[str], source_value: str = "", device_name: str = "") -> int:
        """
        Append new rows with Video URL + STATUS=PENDING.
        Returns how many were appended.
        """
        rows = self.fetch_all_rows()
        if not rows:
            raise RuntimeError("Sheet is empty; please add header row first.")

        header = rows[0]
        hmap = {h.strip(): i for i, h in enumerate(header) if h and h.strip()}

        # existing URLs to avoid adding duplicates
        url_idx = hmap.get("Video URL")
        existing: set[str] = set()
        if url_idx is not None:
            for r in rows[1:]:
                if url_idx < len(r):
                    u = (r[url_idx] or "").strip()
                    if u:
                        existing.add(u)

        # build append rows
        to_append: list[list[str]] = []
        for u in urls:
            u = (u or "").strip()
            if not u or u in existing:
                continue

            new_row = [""] * len(header)
            if "Video URL" in hmap: new_row[hmap["Video URL"]] = u
            if "STATUS" in hmap: new_row[hmap["STATUS"]] = "PENDING"
            if "Downloaded" in hmap: new_row[hmap["Downloaded"]] = "FALSE"
            if "Device name" in hmap: new_row[hmap["Device name"]] = device_name
            if "Source" in hmap and source_value: new_row[hmap["Source"]] = source_value

            to_append.append(new_row)
            existing.add(u)

        if not to_append:
            return 0

        # Append using batchUpdate values.append (add this to SheetsClient if missing)
        self.client.append_values(self.spreadsheet_id, f"{self.tab}!A1", to_append)
        return len(to_append)