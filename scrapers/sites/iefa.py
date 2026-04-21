"""Scraper for iefa.org — static HTML scholarship listings."""
from __future__ import annotations
import re
from typing import List
from scrapers.base import BaseScraper
from scrapers.normalizer import NormalizedScholarship, make_scholarship

SITE_NAME = "IEFA"
BASE_URL = "https://www.iefa.org"
LIST_URL = f"{BASE_URL}/scholarships"


class IefaScraper(BaseScraper):
    name = "iefa"
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

            # IEFA typically has scholarship listings in divs or table rows
            items = soup.find_all("div", class_=re.compile(r"scholarship|listing|result|item", re.I))
            if not items:
                items = soup.find_all(["article", "li"], class_=re.compile(r"scholarship|award", re.I))

            found = 0
            for item in items:
                link = item.find("a", href=re.compile(r"/scholarships/|/scholarship/|/award/"))
                if not link:
                    link = item.find("a", href=True)
                if not link:
                    continue
                title = link.get_text(strip=True)
                href = link.get("href", "")
                if not href.startswith("http"):
                    href = BASE_URL + href
                if not title or len(title) < 5:
                    continue
                text = item.get_text(" ", strip=True)
                deadline_m = re.search(r"[Dd]eadline[:\s]+([^\n|]+)", text)
                amount_m = re.search(r"(\$[\d,]+|€[\d,]+|fully funded|Amount[:\s]+[^\n|]+)", text, re.I)
                degree_m = re.search(r"(undergraduate|bachelor|master|graduate|ph\.?d|doctoral)", text, re.I)
                org_m = re.search(r"(?:by|from|offered by)[:\s]+([^\n|.]+)", text, re.I)
                results.append(make_scholarship(
                    title=title,
                    source_url=href,
                    source_site=SITE_NAME,
                    organization=org_m.group(1).strip() if org_m else None,
                    degree_levels_raw=degree_m.group(0) if degree_m else "any",
                    deadline_raw=deadline_m.group(1).strip() if deadline_m else None,
                    amount=amount_m.group(0) if amount_m else None,
                ))
                found += 1

            if found == 0:
                break
            page += 1
        return results
