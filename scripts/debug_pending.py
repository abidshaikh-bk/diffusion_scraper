import os
from dotenv import load_dotenv
from app.sync.oauth import get_credentials
from app.sync.sheets_client import SheetsClient
from app.sync.sync_manager import SyncManager
from app.sync.sheet_schema import build_header_map, _norm

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
load_dotenv()

def main():
    sid = os.getenv("SPREADSHEET_ID", "").strip()
    tab = os.getenv("SHEET_TAB_NAME", "Sheet1").strip()

    creds = get_credentials(SCOPES)
    client = SheetsClient(creds)
    sync = SyncManager(client, spreadsheet_id=sid, tab_name=tab)

    rows = sync.fetch_all()
    header = rows[0]
    hmap = build_header_map(header)

    def cell(r, name):
        i = hmap.get(_norm(name))
        if i is None or i >= len(r): return ""
        return str(r[i]).strip()

    print("Header keys found:", list(hmap.keys()))
    print("\nFirst 15 rows (row#, STATUS, Downloaded, URL):")
    for idx, r in enumerate(rows[1:16], start=2):
        print(idx, cell(r, "STATUS"), cell(r, "Downloaded"), cell(r, "Video URL")[:60])

if __name__ == "__main__":
    main()