"""Scraper for internationalscholarships.com — static HTML."""
from __future__ import annotations
import re
from typing import List
from scrapers.base import BaseScraper
from scrapers.normalizer import NormalizedScholarship, make_scholarship, find_deadline_in_text

SITE_NAME = "InternationalScholarships.com"
BASE_URL = "https://www.internationalscholarships.com"
LIST_URL = f"{BASE_URL}/scholarships"


class InternationalScholarshipsScraper(BaseScraper):
    name = "internationalscholarships"
    base_url = BASE_URL
    delay = 1.5

    def scrape(self) -> List[NormalizedScholarship]:
        results = []
        page = 1
        while page <= self.max_pages:
            url = LIST_URL if page == 1 else f"{LIST_URL}?page={page}"
            soup = self.get_soup(url)
            if not soup:
                break

            items = soup.find_all(["tr", "div", "li"], class_=re.compile(r"scholarship|result|listing|row", re.I))
            if not items:
                # Try table rows
                items = soup.select("table tr")

            found = 0
            for item in items:
                link = item.find("a", href=re.compile(r"/scholarships/\d+|/scholarship/"))
                if not link:
                    continue
                title = link.get_text(strip=True)
                href = link.get("href", "")
                if not href.startswith("http"):
                    href = BASE_URL + href
                if not title:
                    continue
                text = item.get_text(" ", strip=True)
                deadline_raw = find_deadline_in_text(text)
                if not deadline_raw:
                    deadline_raw = self._fetch_deadline(href)
                amount_m = re.search(r"(\$[\d,]+|€[\d,]+|fully funded|Award[:\s]+[^\n|]+)", text, re.I)
                degree_m = re.search(r"(undergraduate|bachelor|master|graduate|ph\.?d|doctoral)", text, re.I)
                results.append(make_scholarship(
                    title=title,
                    source_url=href,
                    source_site=SITE_NAME,
                    degree_levels_raw=degree_m.group(0) if degree_m else "any",
                    deadline_raw=deadline_raw,
                    amount=amount_m.group(0) if amount_m else None,
                ))
                found += 1

            if found == 0:
                break
            page += 1
        return results
