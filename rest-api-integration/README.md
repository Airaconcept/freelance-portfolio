# REST API Integration - paginated API -> SQLite + CSV (+ Google Sheets)

A small, production-style integration that pulls records from a REST API, **follows pagination**, **retries** temporary errors, **respects rate limits**, and keeps a local **SQLite** database and **CSV** export in sync. An optional **Google Sheets** export is included and switched off by default.

The demo source is the [Art Institute of Chicago public API](https://api.artic.edu/docs/): free, no API key, paginated and rate-limited, so you can run it right away.

## What problem it solves

"Get the data from this API into a spreadsheet/database every day" is one of the most common automation jobs. The hard parts are not the first request but everything around it:

- **pagination** - page numbers (`page=2`, `total_pages`) or a `next_url` link; both are supported by `ApiClient.paginate()`
- **retries** - 429 and 5xx responses, timeouts and connection resets are retried with exponential back-off; a `Retry-After` header is honoured; 4xx errors fail fast with a clear message
- **rate limiting** - a sliding-window limiter (default 50 requests/minute, under the API's 60)
- **safe re-runs** - rows are **upserted by ID**; each run reports `inserted / updated / unchanged`, so nothing is duplicated
- **audit trail** - every run is logged in a `sync_runs` table (time, query, pages, counts, requests, status, error)
- **partial failures** - if the API goes down mid-run, the pages already synced are kept and the run is marked `failed`

## Output example

Included from a real run: [`output/artworks.db`](output/artworks.db) (SQLite) and [`output/artworks.csv`](output/artworks.csv).

```
$ python sync.py -v
INFO page 1: 10 records {'inserted': 10, 'updated': 0, 'unchanged': 0}
...
INFO page 5: 6 records {'inserted': 6, 'updated': 0, 'unchanged': 0}
ok: 5 pages, 46 records fetched in 5 requests -> 46 inserted, 0 updated, 0 unchanged; 46 rows in output/artworks.csv
$ python sync.py
ok: 5 pages, 46 records fetched in 5 requests -> 0 inserted, 0 updated, 46 unchanged; 46 rows in output/artworks.csv
```

![Output preview](docs/preview.png)

| Column | Example |
|---|---|
| id | 16568 |
| title | Water Lilies |
| artist | Claude Monet |
| date_display / year | 1906 / 1906 |
| medium, place_of_origin, department | Oil on canvas, France, Painting and Sculpture of Europe |
| public_domain | 1 |
| url | https://www.artic.edu/artworks/16568 |
| source_updated_at, synced_at | timestamps |

## Install and run

Requires Python 3.9+.

```bash
pip install -r requirements.txt
python sync.py                                   # default demo: all works by Claude Monet, 10 per page
python sync.py --filter artist_id=40610          # another artist (exact-match filter, repeatable)
python sync.py --q "water lilies" --max-pages 2  # full-text search, first 2 pages
python sync.py --db data/art.db --csv data/art.csv --rate 30 -v
```

### Optional: Google Sheets export

```bash
pip install -r requirements-sheets.txt
export GOOGLE_SERVICE_ACCOUNT_JSON=/path/to/service-account.json
export GOOGLE_SHEET_ID=<spreadsheet id>          # share the sheet with the service account's e-mail
python sync.py --sheets                          # or SHEETS_ENABLED=1
```

It replaces the content of the `artworks` worksheet (created if missing) with the current table and freezes the header row. Without `--sheets` nothing Google-related is imported.

### Tests (offline)

```bash
python -m unittest -v
```

A fake HTTP session replaces the network, so the tests cover pagination (both styles), retry/back-off, `Retry-After`, give-up behaviour, the rate limiter, upsert/idempotency, partial failure and the Sheets export (with a fake gspread client) - no internet or credentials needed.

## Adapting it to your API

1. **`BASE_URL`, `ENDPOINT`, `HEADERS`** in `sync.py` - your API, plus an auth header if it needs one (e.g. `{"Authorization": f"Bearer {os.environ['API_TOKEN']}"}`).
2. **`paginate(data_key=..., page_param=...)`** - the key that holds the records and the page parameter name; `next`/`next_url` links are followed automatically. For cursor APIs, add the cursor field next to `next_url`.
3. **`transform()` and `COLUMNS`** - map API fields to your table columns.
4. **Destination** - swap SQLite for PostgreSQL/MySQL (same SQL, different driver), or reuse `sheets_export.py`, or add an Excel export.
5. **Scheduling** - cron / Windows Task Scheduler / GitHub Actions; the `sync_runs` table tells you if a night run failed.

## Project structure

```
api_client.py          # generic client: retries, back-off, rate limit, pagination
sync.py                # API -> transform -> SQLite upsert -> CSV (CLI)
sheets_export.py       # optional Google Sheets export (off by default)
requirements.txt       # requests
requirements-sheets.txt# + gspread, google-auth (only for --sheets)
output/                # artworks.db + artworks.csv from a real run
tests/test_sync.py     # offline tests with a fake HTTP session
docs/preview.png       # screenshot of the output
```

Data: Art Institute of Chicago API - artwork metadata is published under CC0; see the API's terms for details.

## License

MIT
