import os
import base64
import json
import time
import logging
import gspread
from google.oauth2.service_account import Credentials
from typing import List, Generator

logger = logging.getLogger(__name__)

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

class GoogleSheetsService:
    def __init__(self):
        self._client = None
        self._init_client()

    def _init_client(self):
        b64_creds = os.environ.get("GOOGLE_CREDENTIALS_BASE64")
        if not b64_creds:
            raise ValueError("GOOGLE_CREDENTIALS_BASE64 environment variable is not set")
        
        try:
            creds_json = base64.b64decode(b64_creds).decode('utf-8')
            creds_dict = json.loads(creds_json)
        except Exception as e:
            raise ValueError(f"Failed to decode GOOGLE_CREDENTIALS_BASE64: {str(e)}")

        credentials = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
        self._client = gspread.authorize(credentials)

    def create_export_sheet(self, title: str) -> gspread.Spreadsheet:
        """Creates a new spreadsheet."""
        spreadsheet = self._client.create(title)
        return spreadsheet

    def write_headers(self, sheet: gspread.Worksheet):
        """Writes headers to the worksheet and formats them."""
        headers = ["name", "address", "phone", "email", "website", "category", "district", "state", "verified"]
        sheet.append_row(headers)
        
        # Format headers: bold, background color, frozen row
        sheet.format("A1:I1", {
            "textFormat": {"bold": True},
            "backgroundColor": {"red": 0.9, "green": 0.9, "blue": 0.9}
        })
        sheet.freeze(rows=1)

    def _append_with_retry(self, sheet: gspread.Worksheet, batch: List[list], max_retries: int = 3):
        """Appends rows to the sheet with exponential backoff for rate limits."""
        for attempt in range(max_retries):
            try:
                sheet.append_rows(batch, value_input_option="RAW")
                return
            except Exception as e:
                # 429 Too Many Requests or 500 Internal Server Error
                if attempt == max_retries - 1:
                    logger.error(f"Failed to append rows after {max_retries} attempts: {e}")
                    raise
                
                sleep_time = (2 ** attempt) + 1  # 2s, 3s, 5s...
                logger.warning(f"Google Sheets API error: {e}. Retrying in {sleep_time} seconds (Attempt {attempt + 1}/{max_retries})")
                time.sleep(sleep_time)

    def stream_rows_to_sheet(self, sheet: gspread.Worksheet, row_generator: Generator, batch_size: int = 1000) -> int:
        """
        Streams rows from a generator into the Google Sheet in batches.
        Returns the total number of rows inserted.
        """
        batch = []
        total_rows = 0
        
        for biz in row_generator:
            batch.append([
                biz.name,
                biz.address,
                biz.phone if biz.phone else "",
                biz.email,
                biz.website,
                biz.category,
                biz.district,
                biz.state,
                biz.is_valid
            ])
            
            if len(batch) >= batch_size:
                self._append_with_retry(sheet, batch)
                total_rows += len(batch)
                batch.clear()
                
        if batch:
            self._append_with_retry(sheet, batch)
            total_rows += len(batch)
            
        return total_rows
