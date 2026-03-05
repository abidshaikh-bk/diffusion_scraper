from __future__ import annotations

COLUMNS = [
    "Sr. No",
    "Title",	
    "Language",	
    "Video Type",	
    "Quality",	
    "Video URL",	
    "Video Local Saved Path",	
    "Created Datetime",	
    "Status",	
    "Video Country",	
    "Source",	
    "Duration",	
    "Relevance",	
    "Downloaded",	
    "Device name",
    "Discovered By",
    "Relevance Reason",
    "URL Lock",

    "Discovery Query",

    # ✅ YouTube/Platform rich metadata (ML-friendly)
    "Upload Date",          # e.g. 20250921 (YYYYMMDD)
    "Timestamp",            # epoch seconds if available
    "Uploader",
    "Uploader ID",
    "Channel",
    "Channel ID",
    "Channel URL",
    "Uploader URL",

    "View Count",
    "Like Count",
    "Comment Count",

    "Categories",
    "Tags",

    # Descriptive signals
    "Description",          # truncated
    "Webpage URL",          # canonical url from extractor (if different)
]

def _norm(s: str) -> str:
    return " ".join((s or "").strip().split()).lower()

def build_header_map(header_row: list[str]) -> dict[str, int]:
    # map normalized header -> index
    return {_norm(h): i for i, h in enumerate(header_row) if h and h.strip()}


def col_to_a1(col_idx_0: int) -> str:
    # 0-based to letters
    col = ""
    n = col_idx_0 + 1
    while n:
        n, r = divmod(n - 1, 26)
        col = chr(65 + r) + col
    return col