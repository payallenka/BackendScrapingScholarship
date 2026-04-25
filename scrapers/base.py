"""
Base scraper class with session management, rate limiting, and retry logic.
"""
from __future__ import annotations
import logging
import time
import random
from abc import ABC, abstractmethod
from typing import List, Optional
import requests
from requests.adapters import HTTPAdapter, Retry
from bs4 import BeautifulSoup

from scrapers.normalizer import NormalizedScholarship

logger = logging.getLogger(__name__)


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


class BaseScraper(ABC):
    name: str = "base"
    base_url: str = ""
    delay: float = 1.5  # seconds between requests

    def __init__(self, max_pages: int = 10):
        self.max_pages = max_pages
        self.session = self._build_session()
        self._last_request = 0.0

    def _build_session(self) -> requests.Session:
        session = requests.Session()
        retries = Retry(total=3, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504])
        adapter = HTTPAdapter(max_retries=retries)
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        session.headers.update(HEADERS)
        return session

    def _get(self, url: str, **kwargs) -> Optional[requests.Response]:
        elapsed = time.time() - self._last_request
        wait = self.delay + random.uniform(0, 0.5) - elapsed
        if wait > 0:
            time.sleep(wait)
        try:
            resp = self.session.get(url, timeout=15, **kwargs)
            resp.raise_for_status()
            self._last_request = time.time()
            return resp
        except Exception as e:
            logger.warning(f"[{self.name}] GET {url} failed: {e}")
            return None

    def get_soup(self, url: str, **kwargs) -> Optional[BeautifulSoup]:
        resp = self._get(url, **kwargs)
        if resp is None:
            return None
        return BeautifulSoup(resp.text, "lxml")

    def get_json(self, url: str, **kwargs):
        resp = self._get(url, **kwargs)
        if resp is None:
            return None
        try:
            return resp.json()
        except Exception as e:
            logger.warning(f"[{self.name}] JSON parse failed for {url}: {e}")
            return None

    def _fetch_deadline(self, url: str) -> Optional[str]:
        """Fetch a detail page and return an ISO deadline date string, or None.

        Used as a fallback when the list-page card text contains no deadline.
        """
        from scrapers.normalizer import extract_deadline_from_soup
        soup = self.get_soup(url)
        return extract_deadline_from_soup(soup) if soup else None

    def is_valid_scholarship(self, s: NormalizedScholarship) -> bool:
        """Return True if the scholarship has the minimum required fields and looks like a real scholarship."""
        from scrapers.normalizer import is_valid_scholarship_title
        if not (s and s.title and len(s.title) > 5 and s.source_url):
            return False
        return is_valid_scholarship_title(s.title, s.description or "")

    @abstractmethod
    def scrape(self) -> List[NormalizedScholarship]:
        """Run the scraper and return normalized scholarships."""
        ...

    def run(self) -> List[NormalizedScholarship]:
        logger.info(f"[{self.name}] Starting scrape ...")
        try:
            results = self.scrape()
            filtered = [s for s in results if self.is_valid_scholarship(s)]
            logger.info(f"[{self.name}] Scraped {len(filtered)} valid scholarships (from {len(results)} scraped).")
            return filtered
        except Exception as e:
            logger.error(f"[{self.name}] Scrape failed: {e}", exc_info=True)
            return []
