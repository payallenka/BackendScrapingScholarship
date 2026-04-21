"""
Scraper for bold.org — React SPA, uses their public search API.
"""
from __future__ import annotations
import re
from typing import List
from scrapers.base import BaseScraper
from scrapers.normalizer import NormalizedScholarship, make_scholarship

SITE_NAME = "Bold.org"
API_URL = "https://bold.org/api/scholarships/search/"
BASE_URL = "https://bold.org"


class BoldOrgScraper(BaseScraper):
    name = "bold_org"
    base_url = BASE_URL
    delay = 1.0

    def scrape(self) -> List[NormalizedScholarship]:
        results = []
        offset = 0
        per_page = 24
        while offset // per_page < self.max_pages:
            data = self.get_json(
                API_URL,
                params={"limit": per_page, "offset": offset, "sort": "deadline"},
            )
            if not data:
                # Try Playwright fallback
                return self._scrape_playwright()
            scholarships = data.get("results") or data.get("scholarships") or (data if isinstance(data, list) else [])
            if not scholarships:
                break
            for item in scholarships:
                results.append(self._parse_item(item))
            if len(scholarships) < per_page:
                break
            offset += per_page
        return results

    def _parse_item(self, item: dict) -> NormalizedScholarship:
        title = item.get("name") or item.get("title") or "Scholarship"
        slug = item.get("slug") or item.get("id") or ""
        url = f"{BASE_URL}/scholarships/{slug}" if slug else BASE_URL
        description = item.get("description") or item.get("summary") or ""
        amount_val = item.get("award_amount") or item.get("amount") or ""
        amount = f"${amount_val:,}" if isinstance(amount_val, (int, float)) and amount_val else str(amount_val)
        deadline = item.get("deadline") or item.get("deadline_date") or ""
        org = item.get("sponsor") or item.get("organization") or item.get("provider") or ""
        image = item.get("image_url") or item.get("thumbnail") or None

        return make_scholarship(
            title=title,
            source_url=url,
            source_site=SITE_NAME,
            organization=org,
            description=str(description)[:800] if description else None,
            amount=amount,
            deadline_raw=str(deadline),
            degree_levels_raw=str(item.get("eligible_grades", "")) + " " + title,
            image_url=image,
        )

    def _scrape_playwright(self) -> List[NormalizedScholarship]:
        try:
            from playwright.sync_api import sync_playwright
            import json
            results = []
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                ctx = browser.new_context()
                api_responses = []

                def handle_response(response):
                    if "scholarship" in response.url and response.status == 200:
                        try:
                            api_responses.append(response.json())
                        except Exception:
                            pass

                page = ctx.new_page()
                page.on("response", handle_response)
                page.goto(f"{BASE_URL}/scholarships/", wait_until="networkidle", timeout=30000)

                for data in api_responses:
                    items = data.get("results") or data.get("scholarships") or (data if isinstance(data, list) else [])
                    for item in items:
                        results.append(self._parse_item(item))

                if not results:
                    cards = page.query_selector_all("[class*='scholarship'], [class*='card']")
                    for card in cards[:50]:
                        try:
                            title_el = card.query_selector("h2, h3, [class*='title']")
                            link_el = card.query_selector("a")
                            if not title_el or not link_el:
                                continue
                            title = title_el.inner_text().strip()
                            href = link_el.get_attribute("href") or ""
                            text = card.inner_text()
                            amount_match = re.search(r"\$([\d,]+)", text)
                            amount = amount_match.group(0) if amount_match else None
                            results.append(make_scholarship(
                                title=title,
                                source_url=href if href.startswith("http") else BASE_URL + href,
                                source_site=SITE_NAME,
                                amount=amount,
                                degree_levels_raw=title,
                            ))
                        except Exception:
                            continue
                browser.close()
            return results
        except Exception:
            return []
