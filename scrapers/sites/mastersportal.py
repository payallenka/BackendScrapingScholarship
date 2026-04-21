"""
Scraper for mastersportal.com — uses their JSON search endpoint.
"""
from __future__ import annotations
import re
from typing import List
from scrapers.base import BaseScraper
from scrapers.normalizer import NormalizedScholarship, make_scholarship

SITE_NAME = "MastersPortal"
BASE_URL = "https://www.mastersportal.com"
SEARCH_API = "https://search.mastersportal.com/scholarships"


class MastersPortalScraper(BaseScraper):
    name = "mastersportal"
    base_url = BASE_URL
    delay = 1.5

    def scrape(self) -> List[NormalizedScholarship]:
        results = []
        offset = 0
        per_page = 25
        while offset // per_page < self.max_pages:
            data = self.get_json(
                SEARCH_API,
                params={"limit": per_page, "offset": offset, "qualification": "master"},
                headers={"Accept": "application/json", "X-Requested-With": "XMLHttpRequest"},
            )
            if not data:
                # Try HTML scraping
                return self._scrape_html()
            items = data.get("items") or data.get("results") or data.get("scholarships") or (data if isinstance(data, list) else [])
            if not items:
                break
            for item in items:
                results.append(self._parse_item(item))
            total = data.get("total") or data.get("count") or 0
            offset += per_page
            if offset >= total and total > 0:
                break
        return results

    def _parse_item(self, item: dict) -> NormalizedScholarship:
        title = item.get("name") or item.get("title") or "Scholarship"
        url = item.get("url") or item.get("link") or BASE_URL
        if url and not url.startswith("http"):
            url = BASE_URL + url
        description = item.get("description") or item.get("summary") or ""
        amount = str(item.get("value") or item.get("amount") or "")
        deadline = str(item.get("deadline") or item.get("deadline_date") or "")
        org = item.get("organisation") or item.get("provider") or item.get("sponsor") or ""
        countries = item.get("countries") or []
        host = [c.get("name") if isinstance(c, dict) else str(c) for c in countries]

        return make_scholarship(
            title=title,
            source_url=url,
            source_site=SITE_NAME,
            organization=org,
            description=str(description)[:800],
            amount=amount,
            deadline_raw=deadline,
            degree_levels_raw="masters",
            host_countries=host,
        )

    def _scrape_html(self) -> List[NormalizedScholarship]:
        results = []
        page = 1
        while page <= self.max_pages:
            url = f"{BASE_URL}/search/scholarships/master?start={(page-1)*25}"
            soup = self.get_soup(url)
            if not soup:
                break
            items = soup.find_all(["article", "li"], class_=re.compile(r"scholarship|result|item|card", re.I))
            if not items:
                break
            found = 0
            for item in items:
                link = item.find("a", href=True)
                title_tag = item.find(["h2", "h3", "h4"])
                if not link or not title_tag:
                    continue
                title = title_tag.get_text(strip=True)
                href = link["href"]
                if not href.startswith("http"):
                    href = BASE_URL + href
                text = item.get_text(" ", strip=True)
                deadline_m = re.search(r"[Dd]eadline[:\s]+([^\n|]+)", text)
                amount_m = re.search(r"(\$[\d,]+|€[\d,]+|fully funded)", text, re.I)
                results.append(make_scholarship(
                    title=title,
                    source_url=href,
                    source_site=SITE_NAME,
                    degree_levels_raw="masters",
                    deadline_raw=deadline_m.group(1).strip() if deadline_m else None,
                    amount=amount_m.group(0) if amount_m else None,
                ))
                found += 1
            if found == 0:
                break
            page += 1
        return results
