"""Small, reusable REST client: retries with back-off, rate limiting and pagination.

Nothing here is specific to one API - point it at any JSON endpoint.
"""
from __future__ import annotations

import logging
import time
from typing import Callable, Iterator

import requests

log = logging.getLogger(__name__)

RETRY_STATUS = {429, 500, 502, 503, 504}


class ApiError(RuntimeError):
    pass


class RateLimiter:
    """Allow at most `max_calls` per `period` seconds (sliding window)."""

    def __init__(self, max_calls: int, period: float = 60.0, clock=time.monotonic, sleep=time.sleep):
        self.max_calls, self.period = max_calls, period
        self.clock, self.sleep = clock, sleep
        self.calls: list[float] = []

    def wait(self):
        now = self.clock()
        self.calls = [t for t in self.calls if now - t < self.period]
        if len(self.calls) >= self.max_calls:
            pause = self.period - (now - self.calls[0])
            if pause > 0:
                log.info("rate limit: sleeping %.1fs", pause)
                self.sleep(pause)
            now = self.clock()
            self.calls = [t for t in self.calls if now - t < self.period]
        self.calls.append(now)


class ApiClient:
    def __init__(self, base_url: str, *, headers: dict | None = None, max_retries: int = 4,
                 backoff: float = 1.0, timeout: float = 30, rate_limiter: RateLimiter | None = None,
                 session=None, sleep: Callable[[float], None] = time.sleep):
        self.base_url = base_url.rstrip("/")
        self.session = session or requests.Session()
        self.session.headers.update(headers or {})
        self.max_retries, self.backoff, self.timeout = max_retries, backoff, timeout
        self.rate_limiter = rate_limiter
        self.sleep = sleep
        self.requests_made = 0

    def get(self, path_or_url: str, params: dict | None = None) -> dict:
        url = path_or_url if path_or_url.startswith("http") else f"{self.base_url}/{path_or_url.lstrip('/')}"
        for attempt in range(self.max_retries + 1):
            if self.rate_limiter:
                self.rate_limiter.wait()
            self.requests_made += 1
            try:
                r = self.session.get(url, params=params, timeout=self.timeout)
            except requests.RequestException as e:          # timeouts, connection resets
                err = f"{type(e).__name__}: {e}"
                retry_after = None
            else:
                if r.status_code < 400:
                    return r.json()
                if r.status_code not in RETRY_STATUS:
                    raise ApiError(f"{r.status_code} for {url}: {r.text[:200]}")
                err = f"HTTP {r.status_code}"
                retry_after = r.headers.get("Retry-After")
            if attempt == self.max_retries:
                raise ApiError(f"giving up after {attempt + 1} attempts: {err} ({url})")
            delay = float(retry_after) if retry_after and str(retry_after).isdigit() else self.backoff * 2 ** attempt
            log.warning("%s - retry %d/%d in %.1fs", err, attempt + 1, self.max_retries, delay)
            self.sleep(delay)
        raise AssertionError("unreachable")

    def paginate(self, path: str, params: dict | None = None, *, data_key: str = "data",
                 page_param: str = "page", max_pages: int | None = None) -> Iterator[list[dict]]:
        """Yield one page of records at a time.

        Supports the two common styles:
          * a `next_url` / `next` link in the response (followed as-is)
          * page numbers with `pagination.total_pages` (or stop on an empty page)
        """
        params = dict(params or {})
        page, url = 1, path
        while True:
            body = self.get(url, params)
            records = body.get(data_key) or []
            if not records:
                return
            yield records
            if max_pages and page >= max_pages:
                return
            pag = body.get("pagination") or {}
            next_url = pag.get("next_url") or body.get("next")
            if next_url:
                url, params = next_url, None
            else:
                total = pag.get("total_pages")
                if total is not None and page >= total:
                    return
                params[page_param] = page + 1
            page += 1
