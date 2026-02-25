from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, Optional


COLUMNS = [
    "Sr. No",
    "Title",
    "Language",
    "Video Type",
    "Quality",
    "Video URL",
    "Video  Local Saved Path",
    "Created Datetime",
    "STATUS",
    "Video  Country",
    "Source",
    "Duration",
    "Relevance",
    "Downloaded",
    "Device name",
]

COL_INDEX = {name: i for i, name in enumerate(COLUMNS)}


@dataclass
class SheetRow:
    row_index: int  # 1-based index in Google Sheets
    sr_no: Optional[str] = None
    title: Optional[str] = None
    language: Optional[str] = None
    video_type: Optional[str] = None
    quality: Optional[str] = None
    video_url: Optional[str] = None
    local_path: Optional[str] = None
    created_datetime: Optional[str] = None
    status: Optional[str] = None
    video_country: Optional[str] = None
    source: Optional[str] = None
    duration: Optional[str] = None
    relevance: Optional[str] = None
    downloaded: Optional[str] = None
    device_name: Optional[str] = None

    @staticmethod
    def now_iso() -> str:
        return datetime.now().isoformat(timespec="seconds")

    def to_updates(self) -> Dict[str, Any]:
        """Map object fields -> sheet column updates."""
        return {
            "Sr. No": self.sr_no,
            "Title": self.title,
            "Language": self.language,
            "Video Type": self.video_type,
            "Quality": self.quality,
            "Video URL": self.video_url,
            "Video  Local Saved Path": self.local_path,
            "Created Datetime": self.created_datetime,
            "STATUS": self.status,
            "Video  Country": self.video_country,
            "Source": self.source,
            "Duration": self.duration,
            "Relevance": self.relevance,
            "Downloaded": self.downloaded,
            "Device name": self.device_name,
        }