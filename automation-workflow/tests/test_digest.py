"""Offline end-to-end test with a local HTTP server (feed, web page and webhook receiver).
Run with:  python -m unittest
"""
import json
import os
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import digest

RSS = """<?xml version="1.0"?><rss version="2.0"><channel><title>T</title>
{items}</channel></rss>"""
ITEM = "<item><title>{t}</title><link>http://x/{t}</link><guid>{t}</guid></item>"
PAGE = '<html><body>{quotes}</body></html>'


class Handler(BaseHTTPRequestHandler):
    feed_titles = ["Python release", "Rust news"]
    quotes = ["first quote"]
    received = []

    def do_GET(self):
        if self.path == "/feed":
            body = RSS.format(items="".join(ITEM.format(t=t) for t in self.feed_titles))
        else:
            body = PAGE.format(quotes="".join(f'<span class="q">{q}</span>' for q in self.quotes))
        self.send_response(200)
        self.end_headers()
        self.wfile.write(body.encode())

    def do_POST(self):
        Handler.received.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
        self.send_response(200)
        self.end_headers()

    def log_message(self, *a):
        pass


class DigestTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ["NO_PROXY"] = os.environ["no_proxy"] = "127.0.0.1,localhost"  # bypass any system proxy
        cls.srv = HTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()
        cls.base_url = f"http://127.0.0.1:{cls.srv.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()

    def cfg(self, keywords=()):
        return {
            "report": {"title": "Test", "output_dir": "reports", "state_file": "state/seen.json"},
            "keywords": list(keywords),
            "sources": [
                {"name": "Feed", "type": "rss", "url": f"{self.base_url}/feed"},
                {"name": "Page", "type": "web", "url": f"{self.base_url}/page", "selector": ".q"},
                {"name": "Broken", "type": "rss", "url": "http://127.0.0.1:1/nothing"},
            ],
            "webhook": {"enabled": True, "format": "slack", "url": f"{self.base_url}/hook"},
        }

    def test_new_items_only_and_webhook(self):
        Handler.received.clear()
        Handler.feed_titles = ["Python release", "Rust news"]
        Handler.quotes = ["first quote"]
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            r1 = digest.run(self.cfg(), base)
            self.assertEqual(r1["new"], 3)
            self.assertEqual(len(r1["errors"]), 1)            # broken source reported, not fatal
            self.assertTrue(r1["webhook_sent"])
            self.assertIn("Python release", Handler.received[-1]["text"])
            self.assertTrue(Path(r1["excel"]).exists())

            r2 = digest.run(self.cfg(), base)
            self.assertEqual(r2["new"], 0)                    # nothing re-reported

            Handler.feed_titles.append("Go 2 announced")
            Handler.quotes.append("page changed")
            r3 = digest.run(self.cfg(), base)
            self.assertEqual(r3["new"], 2)                    # feed + page change detected
            md = Path(r3["markdown"]).read_text()
            self.assertIn("Go 2 announced", md)
            self.assertIn("page changed", md)

    def test_keyword_filter_and_payload_formats(self):
        Handler.feed_titles = ["Python release", "Rust news"]
        Handler.quotes = []
        with tempfile.TemporaryDirectory() as d:
            r = digest.run(self.cfg(keywords=["python"]), Path(d), dry_run=True)
            self.assertEqual(r["new"], 1)
            self.assertFalse(r["webhook_sent"])
        self.assertIn("content", digest.webhook_payload("discord", "x", [], "t"))
        self.assertEqual(digest.webhook_payload("generic", "x", [], "t")["count"], 0)


if __name__ == "__main__":
    unittest.main()
