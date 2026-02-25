from __future__ import annotations

from typing import Any, Dict, List, Optional

from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials


class SheetsClient:
    def __init__(self, creds: Credentials):
        self._service = build("sheets", "v4", credentials=creds, cache_discovery=False)

    def get_values(self, spreadsheet_id: str, range_a1: str) -> List[List[Any]]:
        resp = (
            self._service.spreadsheets()
            .values()
            .get(spreadsheetId=spreadsheet_id, range=range_a1)
            .execute()
        )
        return resp.get("values", [])

    def batch_update_values(
        self,
        spreadsheet_id: str,
        updates: List[Dict[str, Any]],
        value_input_option: str = "RAW",
    ) -> None:
        """
        updates: [{"range": "Sheet1!A2", "values": [[...]]}, ...]
        """
        body = {"valueInputOption": value_input_option, "data": updates}
        (
            self._service.spreadsheets()
            .values()
            .batchUpdate(spreadsheetId=spreadsheet_id, body=body)
            .execute()
        )
    
    def append_values(
        self,
        spreadsheet_id: str,
        range_a1: str,
        values: list[list[Any]],
        value_input_option: str = "RAW",
        insert_data_option: str = "INSERT_ROWS",
    ) -> None:
        body = {"values": values}
        (
            self._service.spreadsheets()
            .values()
            .append(
                spreadsheetId=spreadsheet_id,
                range=range_a1,
                valueInputOption=value_input_option,
                insertDataOption=insert_data_option,
                body=body,
            )
            .execute()
        )