"""Optional Google Sheets export (off by default).

Turn it on with `--sheets` (or SHEETS_ENABLED=1) and provide:
  GOOGLE_SERVICE_ACCOUNT_JSON  path to a service-account key file
  GOOGLE_SHEET_ID              the spreadsheet ID (share the sheet with the service account's e-mail)
Install the extra packages:  pip install -r requirements-sheets.txt

The gspread import happens only when the export runs, so the rest of the project
(and the tests) work without these packages or any credentials.
"""
from __future__ import annotations

import os


class SheetsConfigError(RuntimeError):
    pass


def get_client():
    key = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON")
    if not key or not os.path.exists(key):
        raise SheetsConfigError("set GOOGLE_SERVICE_ACCOUNT_JSON to a service-account key file")
    try:
        import gspread
    except ImportError as e:
        raise SheetsConfigError("pip install -r requirements-sheets.txt") from e
    return gspread.service_account(filename=key)


def export_rows(headers: list[str], rows: list[list], *, sheet_id: str | None = None,
                worksheet: str = "artworks", client=None) -> int:
    """Replace the worksheet content with headers + rows. Returns the number of data rows written."""
    sheet_id = sheet_id or os.environ.get("GOOGLE_SHEET_ID")
    if not sheet_id:
        raise SheetsConfigError("set GOOGLE_SHEET_ID (or pass sheet_id)")
    client = client or get_client()
    sh = client.open_by_key(sheet_id)
    try:
        ws = sh.worksheet(worksheet)
    except Exception:                                      # gspread.WorksheetNotFound
        ws = sh.add_worksheet(title=worksheet, rows=len(rows) + 10, cols=len(headers))
    ws.clear()
    values = [headers] + [["" if v is None else v for v in r] for r in rows]
    ws.update(values, "A1")
    ws.freeze(rows=1)
    return len(rows)
