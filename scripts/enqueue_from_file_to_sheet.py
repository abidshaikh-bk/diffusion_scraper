import os
import socket
from dotenv import load_dotenv

from app.platforms.registry import PlatformRegistry
from app.sync.oauth import get_credentials
from app.sync.sheets_client import SheetsClient
from app.sync.sync_manager import SyncManager

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

load_dotenv()

def read_urls(path: str) -> list[str]:
    urls = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            u = line.strip()
            if u and not u.startswith("#"):
                urls.append(u)
    return urls

def main():
    sid = os.getenv("SPREADSHEET_ID", "").strip()
    tab = os.getenv("SHEET_TAB_NAME", "Sheet1").strip()
    if not sid:
        raise ValueError("SPREADSHEET_ID missing in .env")

    device = socket.gethostname()
    registry = PlatformRegistry.from_yaml()

    urls = read_urls("inputs/seed_urls.txt")
    allowed = [u for u in urls if registry.is_allowed(u)]
    rejected = [u for u in urls if not registry.is_allowed(u)]

    creds = get_credentials(SCOPES)
    client = SheetsClient(creds)
    sync = SyncManager(client, spreadsheet_id=sid, tab_name=tab)

    added = sync.append_pending_urls(allowed, device_name=device)

    print(f"Read={len(urls)} Allowed={len(allowed)} Rejected={len(rejected)} Appended={added}")
    if rejected:
        print("Rejected (not allowlisted):")
        for u in rejected[:20]:
            print(" -", u)

if __name__ == "__main__":
    main()