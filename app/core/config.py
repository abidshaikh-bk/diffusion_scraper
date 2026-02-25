from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class AppConfig:
    spreadsheet_id: str
    sheet_tab_name: str = "Sheet1"
    poll_interval_sec: int = 3
    batch_size: int = 10

    @staticmethod
    def from_env() -> "AppConfig":
        spreadsheet_id = os.getenv("SPREADSHEET_ID", "").strip()
        if not spreadsheet_id:
            raise ValueError("SPREADSHEET_ID is required in .env")

        return AppConfig(
            spreadsheet_id=spreadsheet_id,
            sheet_tab_name=os.getenv("SHEET_TAB_NAME", "Sheet1").strip() or "Sheet1",
            poll_interval_sec=int(os.getenv("POLL_INTERVAL_SEC", "3")),
            batch_size=int(os.getenv("BATCH_SIZE", "10")),
        )