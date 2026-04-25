"""Scraper for topuniversities.com/scholarships."""
from __future__ import annotations
import re
from typing import List
from scrapers.base import BaseScraper
from scrapers.normalizer import NormalizedScholarship, make_scholarship, find_deadline_in_text

SITE_NAME = "TopUniversities"
BASE_URL = "https://www.topuniversities.com"
API_URL = "https://www.topuniversities.com/scholarships/search"


class TopUniversitiesScraper(BaseScraper):
    name = "topuniversities"
    base_url = BASE_URL
    delay = 2.0

    def scrape(self) -> List[NormalizedScholarship]:
        results = []
        page = 0
        while page < self.max_pages:
            data = self.get_json(
                API_URL,
                params={"page": page, "items_per_page": 20},
                headers={"Accept": "application/json", "X-Requested-With": "XMLHttpRequest"},
            )
            if not data:
                return self._scrape_html()
            items = data.get("results") or data.get("items") or data.get("data") or (data if isinstance(data, list) else [])
            if not items:
                break
            for item in items:
                results.append(self._parse_item(item))
            page += 1
        return results

    def _parse_item(self, item: dict) -> NormalizedScholarship:
        title = item.get("title") or item.get("name") or "Scholarship"
        url = item.get("url") or item.get("link") or BASE_URL
        if not url.startswith("http"):
            url = BASE_URL + url
        description = item.get("description") or item.get("body") or item.get("summary") or ""
        amount = str(item.get("value") or item.get("amount") or "")
        deadline = str(item.get("deadline") or "")
        org = item.get("organization") or item.get("sponsor") or ""
        degree_raw = str(item.get("study_level") or item.get("degree") or "any")
        return make_scholarship(
            title=title, source_url=url, source_site=SITE_NAME,
            organization=org, description=str(description)[:800],
            amount=amount, deadline_raw=deadline, degree_levels_raw=degree_raw,
        )

    def _scrape_html(self) -> List[NormalizedScholarship]:
        results = []
        page = 1
        while page <= self.max_pages:
            url = f"{BASE_URL}/scholarships/scholarships-for-students?page={page}"
            soup = self.get_soup(url)
            if not soup:
                break
            items = soup.find_all("div", class_=re.compile(r"scholarship|result|item|card", re.I)) or soup.find_all("article")
            found = 0
            for item in items:
                link = item.find("a", href=re.compile(r"/scholarships?/"))
                if not link:
                    continue
                title = link.get_text(strip=True)
                href = link.get("href", "")
                if not href.startswith("http"):
                    href = BASE_URL + href
                text = item.get_text(" ", strip=True)
                deadline_raw = find_deadline_in_text(text)
                if not deadline_raw:
                    deadline_raw = self._fetch_deadline(href)
                results.append(make_scholarship(
                    title=title, source_url=href, source_site=SITE_NAME,
                    degree_levels_raw=title,
                    deadline_raw=deadline_raw,
                ))
                found += 1
            if found == 0:
                break
            page += 1
        return results
