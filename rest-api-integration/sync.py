"""Sync records from a public REST API into SQLite and CSV (optional Google Sheets).

Demo source: the Art Institute of Chicago public API (https://api.artic.edu/docs/) -
free, no API key, paginated, rate-limited (anonymous: 60 requests/minute).

    python sync.py                                   # Claude Monet's works, 10 per page
    python sync.py --filter artist_id=40610 --page-size 25
    python sync.py --q "water lilies" --max-pages 2
    python sync.py --sheets                          # also push to Google Sheets (needs credentials)

Re-running is safe: rows are upserted by ID, and the run reports inserted / updated / unchanged.
"""
from __future__ import annotations

import argparse
import csv
import json
import logging
import os
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

from api_client import ApiClient, ApiError, RateLimiter

BASE_URL = "https://api.artic.edu/api/v1"
ENDPOINT = "artworks/search"
API_FIELDS = ["id", "title", "artist_title", "date_display", "date_start", "medium_display",
              "place_of_origin", "department_title", "is_public_domain", "updated_at"]
# (column, type) in SQLite and in the CSV/Sheet
COLUMNS = [("id", "INTEGER PRIMARY KEY"), ("title", "TEXT"), ("artist", "TEXT"), ("date_display", "TEXT"),
           ("year", "INTEGER"), ("medium", "TEXT"), ("place_of_origin", "TEXT"), ("department", "TEXT"),
           ("public_domain", "INTEGER"), ("url", "TEXT"), ("source_updated_at", "TEXT"), ("synced_at", "TEXT")]
COMPARE = [c for c, _ in COLUMNS if c != "synced_at"]       # columns that decide "updated" vs "unchanged"
HEADERS = {"User-Agent": "freelance-portfolio-sample/1.0",
           "AIC-User-Agent": "freelance-portfolio-sample (github.com/Airaconcept/freelance-portfolio)"}


def transform(rec: dict, synced_at: str) -> dict:
    return {
        "id": rec["id"],
        "title": (rec.get("title") or "").strip(),
        "artist": rec.get("artist_title"),
        "date_display": rec.get("date_display"),
        "year": rec.get("date_start"),
        "medium": rec.get("medium_display"),
        "place_of_origin": rec.get("place_of_origin"),
        "department": rec.get("department_title"),
        "public_domain": int(bool(rec.get("is_public_domain"))),
        "url": f"https://www.artic.edu/artworks/{rec['id']}",
        "source_updated_at": rec.get("updated_at"),
        "synced_at": synced_at,
    }


def open_db(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path)
    con.execute(f"CREATE TABLE IF NOT EXISTS artworks ({', '.join(f'{c} {t}' for c, t in COLUMNS)})")
    con.execute("""CREATE TABLE IF NOT EXISTS sync_runs (
        id INTEGER PRIMARY KEY AUTOINCREMENT, started_at TEXT, finished_at TEXT, query TEXT,
        pages INTEGER, fetched INTEGER, inserted INTEGER, updated INTEGER, unchanged INTEGER,
        requests INTEGER, status TEXT, error TEXT)""")
    return con


def upsert(con: sqlite3.Connection, rows: list[dict]) -> dict:
    stats = {"inserted": 0, "updated": 0, "unchanged": 0}
    cols = [c for c, _ in COLUMNS]
    for row in rows:
        cur = con.execute(f"SELECT {', '.join(COMPARE)} FROM artworks WHERE id = ?", (row["id"],)).fetchone()
        if cur is None:
            stats["inserted"] += 1
        elif tuple(cur) == tuple(row[c] for c in COMPARE):
            stats["unchanged"] += 1
            continue
        else:
            stats["updated"] += 1
        con.execute(
            f"INSERT INTO artworks ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))}) "
            f"ON CONFLICT(id) DO UPDATE SET {', '.join(f'{c}=excluded.{c}' for c in cols if c != 'id')}",
            [row[c] for c in cols])
    con.commit()
    return stats


def export_csv(con: sqlite3.Connection, path: Path) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    cols = [c for c, _ in COLUMNS]
    rows = con.execute(f"SELECT {', '.join(cols)} FROM artworks ORDER BY year, id").fetchall()
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(cols)
        w.writerows(rows)
    return len(rows)


def build_params(q: str | None, filters: list[str], page_size: int) -> dict:
    params = {"fields": ",".join(API_FIELDS), "limit": page_size}
    if q:
        params["q"] = q
    for f in filters:
        k, _, v = f.partition("=")
        params[f"query[term][{k}]"] = v
    return params


def run(client: ApiClient, db: Path, csv_path: Path, params: dict, max_pages: int | None,
        sheets: bool = False, sheets_client=None) -> dict:
    con = open_db(db)
    started = datetime.now(timezone.utc).isoformat(timespec="seconds")
    totals = {"pages": 0, "fetched": 0, "inserted": 0, "updated": 0, "unchanged": 0}
    status, error = "ok", None
    try:
        for records in client.paginate(ENDPOINT, params, max_pages=max_pages):
            totals["pages"] += 1
            totals["fetched"] += len(records)
            stats = upsert(con, [transform(r, started) for r in records])
            for k, v in stats.items():
                totals[k] += v
            logging.info("page %d: %d records %s", totals["pages"], len(records), stats)
    except ApiError as e:
        status, error = "failed", str(e)                  # keep what was synced, record the failure
        logging.error("sync stopped: %s", e)
    totals["csv_rows"] = export_csv(con, csv_path)
    if sheets and status == "ok":
        import sheets_export
        cols = [c for c, _ in COLUMNS]
        rows = con.execute(f"SELECT {', '.join(cols)} FROM artworks ORDER BY year, id").fetchall()
        totals["sheet_rows"] = sheets_export.export_rows(cols, [list(r) for r in rows], client=sheets_client)
    con.execute("INSERT INTO sync_runs (started_at, finished_at, query, pages, fetched, inserted, updated, "
                "unchanged, requests, status, error) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (started, datetime.now(timezone.utc).isoformat(timespec="seconds"), json.dumps(params),
                 totals["pages"], totals["fetched"], totals["inserted"], totals["updated"], totals["unchanged"],
                 client.requests_made, status, error))
    con.commit()
    con.close()
    totals.update(status=status, error=error, requests=client.requests_made)
    return totals


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Sync a paginated REST API into SQLite + CSV")
    ap.add_argument("--q", help="full-text search")
    ap.add_argument("--filter", action="append", default=None,
                    help="exact-match filter field=value (repeatable). Default: artist_id=35809 (Claude Monet)")
    ap.add_argument("--page-size", type=int, default=10)
    ap.add_argument("--max-pages", type=int)
    ap.add_argument("--rate", type=int, default=50, help="max requests per minute (API allows 60)")
    ap.add_argument("--db", default="output/artworks.db")
    ap.add_argument("--csv", default="output/artworks.csv")
    ap.add_argument("--sheets", action="store_true", default=os.environ.get("SHEETS_ENABLED") == "1",
                    help="also export to Google Sheets (see sheets_export.py)")
    ap.add_argument("-v", "--verbose", action="store_true")
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO if a.verbose else logging.WARNING, format="%(levelname)s %(message)s")
    filters = a.filter if a.filter is not None else ([] if a.q else ["artist_id=35809"])
    client = ApiClient(BASE_URL, headers=HEADERS, rate_limiter=RateLimiter(a.rate, 60))
    t = run(client, Path(a.db), Path(a.csv), build_params(a.q, filters, a.page_size), a.max_pages, a.sheets)
    print(f"{t['status']}: {t['pages']} pages, {t['fetched']} records fetched in {t['requests']} requests -> "
          f"{t['inserted']} inserted, {t['updated']} updated, {t['unchanged']} unchanged; "
          f"{t['csv_rows']} rows in {a.csv}" + (f"; {t['sheet_rows']} rows to Google Sheets" if "sheet_rows" in t else ""))
    if t["error"]:
        print("error:", t["error"], file=sys.stderr)
    return 0 if t["status"] == "ok" else 1


if __name__ == "__main__":
    sys.exit(main())
