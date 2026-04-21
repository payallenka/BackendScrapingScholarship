"""Scraper for wemakescholars.com — HTML + possible API."""
from __future__ import annotations
import re
from typing import List
from scrapers.base import BaseScraper
from scrapers.normalizer import NormalizedScholarship, make_scholarship

SITE_NAME = "WeMakeScholars"
BASE_URL = "https://www.wemakescholars.com"
LIST_URL = f"{BASE_URL}/scholarship"


class WeMakeScholarsScraper(BaseScraper):
    name = "wemakescholars"
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

            items = (
                soup.find_all("div", class_=re.compile(r"scholarship[-_]card|scholarship[-_]item|scholarship[-_]list|card", re.I))
                or soup.find_all("article")
                or soup.find_all("li", class_=re.compile(r"scholarship", re.I))
            )

            found = 0
            for item in items:
                link = item.find("a", href=re.compile(r"/scholarship/"), )
                if not link:
                    link = item.find("a", href=True)
                if not link:
                    continue
                title_el = item.find(["h2", "h3", "h4", ".title", ".scholarship-name"])
                title = (title_el or link).get_text(strip=True)
                if not title or len(title) < 5:
                    continue
                href = link.get("href", "")
                if not href.startswith("http"):
                    href = BASE_URL + href
                text = item.get_text(" ", strip=True)
                deadline_m = re.search(r"[Dd]eadline[:\s]+([^\n|]+)", text)
                amount_m = re.search(r"(\$[\d,]+|€[\d,]+|₹[\d,]+|fully funded|Award[:\s]+[^\n|]+)", text, re.I)
                degree_m = re.search(r"(undergraduate|bachelor|master|graduate|ph\.?d|doctoral|post.?grad)", text, re.I)
                org_m = item.find(class_=re.compile(r"org|provider|sponsor|university", re.I))
                results.append(make_scholarship(
                    title=title,
                    source_url=href,
                    source_site=SITE_NAME,
                    organization=org_m.get_text(strip=True) if org_m else None,
                    degree_levels_raw=degree_m.group(0) if degree_m else "any",
                    deadline_raw=deadline_m.group(1).strip() if deadline_m else None,
                    amount=amount_m.group(0) if amount_m else None,
                ))
                found += 1
            if found == 0:
                break
            page += 1
        return results
