"""Offline tests - a fake HTTP session stands in for the API, so no network or keys are needed.
Run with:  python -m unittest -v
"""
import csv
import sqlite3
import tempfile
import unittest
from pathlib import Path

import requests

import sheets_export
import sync
from api_client import ApiClient, ApiError, RateLimiter


class FakeResponse:
    def __init__(self, status=200, body=None, headers=None):
        self.status_code, self._body, self.headers = status, body or {}, headers or {}
        self.text = str(body)

    def json(self):
        return self._body


class FakeSession:
    """Returns queued responses (or raises queued exceptions) and records every call."""

    def __init__(self, responses):
        self.responses, self.calls, self.headers = list(responses), [], {}

    def get(self, url, params=None, timeout=None):
        self.calls.append((url, dict(params or {})))
        r = self.responses.pop(0)
        if isinstance(r, Exception):
            raise r
        return r


def page(ids, current, total_pages, title="Work"):
    return FakeResponse(body={
        "pagination": {"current_page": current, "total_pages": total_pages},
        "data": [{"id": i, "title": f"{title} {i}", "artist_title": "Test Artist", "date_start": 1900 + i,
                  "date_display": str(1900 + i), "is_public_domain": True, "updated_at": "2026-01-01"} for i in ids]})


def client(responses, sleeps=None):
    return ApiClient("https://api.example.test/v1", session=FakeSession(responses),
                     sleep=(sleeps.append if sleeps is not None else lambda s: None))


class ClientTests(unittest.TestCase):
    def test_page_number_pagination_stops_at_total_pages(self):
        c = client([page([1, 2], 1, 3), page([3, 4], 2, 3), page([5], 3, 3)])
        pages = list(c.paginate("items", {"limit": 2}))
        self.assertEqual([[r["id"] for r in p] for p in pages], [[1, 2], [3, 4], [5]])
        self.assertEqual([p.get("page") for _, p in c.session.calls], [None, 2, 3])

    def test_next_url_pagination_and_max_pages(self):
        r1 = FakeResponse(body={"data": [{"id": 1}], "pagination": {"next_url": "https://api.example.test/v1/items?page=2"}})
        r2 = FakeResponse(body={"data": [{"id": 2}], "pagination": {"next_url": "https://api.example.test/v1/items?page=3"}})
        c = client([r1, r2])
        self.assertEqual(len(list(c.paginate("items", max_pages=2))), 2)
        self.assertEqual(c.session.calls[1][0], "https://api.example.test/v1/items?page=2")

    def test_retries_429_with_retry_after_then_5xx_and_timeout(self):
        sleeps = []
        c = client([FakeResponse(429, headers={"Retry-After": "7"}), FakeResponse(503),
                    requests.Timeout("slow"), FakeResponse(200, {"ok": 1})], sleeps)
        self.assertEqual(c.get("x"), {"ok": 1})
        self.assertEqual(sleeps, [7.0, 2.0, 4.0])          # Retry-After honoured, then exponential back-off
        self.assertEqual(c.requests_made, 4)

    def test_gives_up_and_does_not_retry_client_errors(self):
        c = client([FakeResponse(500)] * 5)
        with self.assertRaises(ApiError):
            c.get("x")
        self.assertEqual(c.requests_made, 5)
        c = client([FakeResponse(404)])
        with self.assertRaises(ApiError):
            c.get("x")
        self.assertEqual(c.requests_made, 1)

    def test_rate_limiter_sleeps_when_window_is_full(self):
        t, slept = [0.0], []
        rl = RateLimiter(3, 60, clock=lambda: t[0], sleep=lambda s: (slept.append(s), t.__setitem__(0, t[0] + s)))
        for _ in range(3):
            rl.wait(); t[0] += 1
        rl.wait()                                            # 4th call inside the same minute
        self.assertEqual(slept, [57.0])


class SyncTests(unittest.TestCase):
    def test_sync_is_idempotent_and_detects_updates(self):
        with tempfile.TemporaryDirectory() as d:
            db, out = Path(d) / "a.db", Path(d) / "a.csv"
            params = sync.build_params(None, ["artist_id=1"], 2)
            self.assertEqual(params["query[term][artist_id]"], "1")

            t1 = sync.run(client([page([1, 2], 1, 2), page([3], 2, 2)]), db, out, params, None)
            self.assertEqual((t1["inserted"], t1["updated"], t1["unchanged"], t1["pages"]), (3, 0, 0, 2))

            t2 = sync.run(client([page([1, 2], 1, 2), page([3], 2, 2, title="Renamed")]), db, out, params, None)
            self.assertEqual((t2["inserted"], t2["updated"], t2["unchanged"]), (0, 1, 2))

            con = sqlite3.connect(db)
            self.assertEqual(con.execute("SELECT title FROM artworks WHERE id=3").fetchone()[0], "Renamed 3")
            self.assertEqual(con.execute("SELECT COUNT(*), MIN(status) FROM sync_runs").fetchone(), (2, "ok"))
            with out.open(encoding="utf-8-sig") as f:
                rows = list(csv.DictReader(f))
            self.assertEqual([r["id"] for r in rows], ["1", "2", "3"])
            self.assertEqual(rows[0]["url"], "https://www.artic.edu/artworks/1")

    def test_failure_keeps_synced_pages_and_is_logged(self):
        with tempfile.TemporaryDirectory() as d:
            db = Path(d) / "a.db"
            c = client([page([1, 2], 1, 3)] + [FakeResponse(500)] * 5)
            t = sync.run(c, db, Path(d) / "a.csv", sync.build_params(None, [], 2), None)
            self.assertEqual((t["status"], t["inserted"], t["csv_rows"]), ("failed", 2, 2))
            con = sqlite3.connect(db)
            self.assertEqual(con.execute("SELECT status FROM sync_runs").fetchone()[0], "failed")


class FakeWorksheet:
    def __init__(self): self.values, self.frozen = None, None
    def clear(self): self.values = None
    def update(self, values, rng): self.values = values
    def freeze(self, rows): self.frozen = rows


class FakeSpreadsheet:
    def __init__(self): self.ws = None
    def worksheet(self, name):
        if self.ws is None: raise LookupError(name)
        return self.ws
    def add_worksheet(self, title, rows, cols): self.ws = FakeWorksheet(); return self.ws


class FakeGspread:
    def __init__(self): self.sh = FakeSpreadsheet()
    def open_by_key(self, key): self.key = key; return self.sh


class SheetsTests(unittest.TestCase):
    def test_export_with_fake_client(self):
        g = FakeGspread()
        n = sheets_export.export_rows(["id", "title"], [[1, "A"], [2, None]], sheet_id="SHEET123", client=g)
        self.assertEqual(n, 2)
        self.assertEqual(g.key, "SHEET123")
        self.assertEqual(g.sh.ws.values, [["id", "title"], [1, "A"], [2, ""]])
        self.assertEqual(g.sh.ws.frozen, 1)

    def test_missing_config_gives_clear_error(self):
        with self.assertRaises(sheets_export.SheetsConfigError):
            sheets_export.export_rows(["id"], [], sheet_id=None, client=FakeGspread())

    def test_sync_pushes_to_sheets_only_when_enabled(self):
        with tempfile.TemporaryDirectory() as d:
            g = FakeGspread()
            import os
            os.environ["GOOGLE_SHEET_ID"] = "SHEET123"
            try:
                t = sync.run(client([page([1], 1, 1)]), Path(d) / "a.db", Path(d) / "a.csv",
                             sync.build_params(None, [], 1), None, sheets=True, sheets_client=g)
            finally:
                del os.environ["GOOGLE_SHEET_ID"]
            self.assertEqual(t["sheet_rows"], 1)
            self.assertEqual(g.sh.ws.values[0][:2], ["id", "title"])


if __name__ == "__main__":
    unittest.main()
