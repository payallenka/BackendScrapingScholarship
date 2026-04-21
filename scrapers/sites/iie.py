"""Scraper for IIE (iie.org) scholarship programs."""
from __future__ import annotations
import re
from typing import List
from scrapers.base import BaseScraper
from scrapers.normalizer import NormalizedScholarship, make_scholarship

SITE_NAME = "IIE"
BASE_URL = "https://www.iie.org"
LIST_URL = f"{BASE_URL}/scholarships-programs/"


class IIEScraper(BaseScraper):
    name = "iie"
    base_url = BASE_URL
    delay = 2.0

    def scrape(self) -> List[NormalizedScholarship]:
        results = []
        page = 1
        while page <= self.max_pages:
            url = LIST_URL if page == 1 else f"{LIST_URL}?pag={page}"
            params = {"iie-audience": "student", "pag": page}
            soup = self.get_soup(LIST_URL, params=params)
            if not soup:
                break

            items = (
                soup.find_all("div", class_=re.compile(r"program[-_]card|scholarship|listing|result", re.I))
                or soup.find_all("article")
                or soup.find_all("li", class_=re.compile(r"program|scholarship", re.I))
            )

            found = 0
            for item in items:
                link = item.find("a", href=re.compile(r"/programs?/|/scholarships?/"))
                if not link:
                    link = item.find("a", href=True)
                if not link:
                    continue
                title_tag = item.find(["h2", "h3", "h4"])
                title = (title_tag or link).get_text(strip=True)
                if not title or len(title) < 5:
                    continue
                href = link.get("href", "")
                if not href.startswith("http"):
                    href = BASE_URL + href
                text = item.get_text(" ", strip=True)
                deadline_m = re.search(r"[Dd]eadline[:\s]+([^\n|]+)", text)
                amount_m = re.search(r"(\$[\d,]+|€[\d,]+|fully funded|stipend)", text, re.I)
                degree_m = re.search(r"(undergraduate|bachelor|master|graduate|ph\.?d|doctoral)", text, re.I)
                results.append(make_scholarship(
                    title=title,
                    source_url=href,
                    source_site=SITE_NAME,
                    degree_levels_raw=degree_m.group(0) if degree_m else "any",
                    deadline_raw=deadline_m.group(1).strip() if deadline_m else None,
                    amount=amount_m.group(0) if amount_m else None,
                    tags=["IIE"],
                ))
                found += 1

            if found == 0:
                break
            page += 1
        return results
