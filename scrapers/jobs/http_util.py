"""
Shared resilient HTTP for job scrapers: a pooled session with automatic retry +
exponential backoff on rate-limit/5xx, a browser User-Agent, and polite
throttling between requests so we don't trip per-IP rate limits.
"""
import random
import time

import requests
from requests.adapters import HTTPAdapter, Retry

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

_session = None
_last_request = 0.0
DEFAULT_DELAY = 0.6  # seconds between requests (plus jitter)


def get_session() -> requests.Session:
    global _session
    if _session is None:
        s = requests.Session()
        retries = Retry(
            total=3,
            backoff_factor=1,                       # 1s, 2s, 4s
            status_forcelist=[429, 500, 502, 503, 504],
            respect_retry_after_header=True,
            allowed_methods=frozenset(["GET"]),
        )
        adapter = HTTPAdapter(max_retries=retries)
        s.mount("http://", adapter)
        s.mount("https://", adapter)
        s.headers.update(_HEADERS)
        _session = s
    return _session


def polite_get(url: str, *, delay: float = DEFAULT_DELAY, **kwargs) -> requests.Response:
    """GET with throttling, retry/backoff and a browser UA. Same signature as
    requests.get (timeout defaults to 20s)."""
    global _last_request
    wait = delay + random.uniform(0, 0.4) - (time.time() - _last_request)
    if wait > 0:
        time.sleep(wait)
    kwargs.setdefault("timeout", 20)
    resp = get_session().get(url, **kwargs)
    _last_request = time.time()
    return resp
