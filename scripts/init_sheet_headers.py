import os
from dotenv import load_dotenv

from app.sync.oauth import get_credentials
from app.sync.sheets_client import SheetsClient
from app.sync.sync_manager import SyncManager

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

load_dotenv()

def main():
    sid = os.getenv("SPREADSHEET_ID", "").strip()
    tab = os.getenv("SHEET_TAB_NAME", "Sheet1").strip()
    if not sid:
        raise ValueError("SPREADSHEET_ID missing in .env")

    creds = get_credentials(SCOPES)
    client = SheetsClient(creds)
    sync = SyncManager(client, spreadsheet_id=sid, tab_name=tab)

    sync.ensure_headers(rewrite_if_mismatch=True)
    print("✅ Headers verified/initialized.")

if __name__ == "__main__":
    main()