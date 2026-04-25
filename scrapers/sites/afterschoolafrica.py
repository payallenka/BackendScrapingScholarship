"""
Scraper for afterschoolafrica.com — JS-rendered, uses Playwright.
Falls back to requests if playwright is unavailable.
"""
from __future__ import annotations
import re
from typing import List
from scrapers.base import BaseScraper
from scrapers.normalizer import NormalizedScholarship, make_scholarship, find_deadline_in_text

SITE_NAME = "After School Africa"
BASE_URL = "https://www.afterschoolafrica.com"
LIST_URL = f"{BASE_URL}/?opp_type=scholarship"


class AfterSchoolAfricaScraper(BaseScraper):
    name = "afterschoolafrica"
    base_url = BASE_URL
    delay = 2.0

    def scrape(self) -> List[NormalizedScholarship]:
        try:
            return self._scrape_playwright()
        except Exception:
            return self._scrape_requests()

    def _scrape_playwright(self) -> List[NormalizedScholarship]:
        from playwright.sync_api import sync_playwright
        results = []
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.set_extra_http_headers({"User-Agent": "Mozilla/5.0"})
            page_num = 1
            while page_num <= self.max_pages:
                url = LIST_URL if page_num == 1 else f"{LIST_URL}&paged={page_num}"
                page.goto(url, wait_until="networkidle", timeout=30000)
                cards = page.query_selector_all("article, .opportunity-item, .post-item, .card")
                if not cards:
                    break
                for card in cards:
                    try:
                        title_el = card.query_selector("h2 a, h3 a, .title a, .entry-title a")
                        if not title_el:
                            continue
                        title = title_el.inner_text().strip()
                        href = title_el.get_attribute("href") or ""
                        text = card.inner_text()
                        deadline_raw = find_deadline_in_text(text)
                        amount_match = re.search(r"(\$[\d,]+|€[\d,]+|fully funded|full scholarship)", text, re.I)
                        amount = amount_match.group(0) if amount_match else None
                        results.append(make_scholarship(
                            title=title,
                            source_url=href if href.startswith("http") else BASE_URL + href,
                            source_site=SITE_NAME,
                            degree_levels_raw=title + " " + text[:200],
                            deadline_raw=deadline_raw,
                            amount=amount,
                            eligible_nationalities=["African"],
                            tags=["Africa"],
                        ))
                    except Exception:
                        continue
                page_num += 1
            browser.close()
        return results

    def _scrape_requests(self) -> List[NormalizedScholarship]:
        """Fallback HTML scraping."""
        results = []
        page_num = 1
        while page_num <= self.max_pages:
            url = LIST_URL if page_num == 1 else f"{LIST_URL}&paged={page_num}"
            soup = self.get_soup(url)
            if not soup:
                break
            articles = soup.find_all(["article", "div"], class_=re.compile(r"post|opportunity|card", re.I))
            if not articles:
                break
            found = 0
            for art in articles:
                title_tag = art.find(["h2", "h3"], class_=re.compile(r"title|entry", re.I)) or art.find("h2") or art.find("h3")
                if not title_tag:
                    continue
                link = title_tag.find("a") or art.find("a")
                if not link:
                    continue
                title = link.get_text(strip=True)
                href = link.get("href", "")
                if not title or not href:
                    continue
                text = art.get_text(" ", strip=True)
                deadline_raw = find_deadline_in_text(text)
                full_url = href if href.startswith("http") else BASE_URL + href
                if not deadline_raw:
                    deadline_raw = self._fetch_deadline(full_url)
                amount_match = re.search(r"(\$[\d,]+|€[\d,]+|fully funded)", text, re.I)
                amount = amount_match.group(0) if amount_match else None
                results.append(make_scholarship(
                    title=title,
                    source_url=full_url,
                    source_site=SITE_NAME,
                    degree_levels_raw=title,
                    deadline_raw=deadline_raw,
                    amount=amount,
                    eligible_nationalities=["African"],
                    tags=["Africa"],
                ))
                found += 1
            if found == 0:
                break
            page_num += 1
        return results
