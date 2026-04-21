"""Scraper for goabroad.com/scholarships-abroad."""
from __future__ import annotations
import re
from typing import List
from scrapers.base import BaseScraper
from scrapers.normalizer import NormalizedScholarship, make_scholarship

SITE_NAME = "GoAbroad"
BASE_URL = "https://www.goabroad.com"
LIST_URL = f"{BASE_URL}/scholarships-abroad/study-abroad"


class GoAbroadScraper(BaseScraper):
    name = "goabroad"
    base_url = BASE_URL
    delay = 2.0

    def scrape(self) -> List[NormalizedScholarship]:
        results = []
        page = 1
        while page <= self.max_pages:
            url = LIST_URL if page == 1 else f"{LIST_URL}/{page}"
            soup = self.get_soup(url)
            if not soup:
                break

            items = (
                soup.find_all("div", class_=re.compile(r"listing[-_]item|program[-_]listing|result", re.I))
                or soup.find_all("article")
                or soup.find_all("div", class_=re.compile(r"card", re.I))
            )

            found = 0
            for item in items:
                title_tag = item.find(["h2", "h3", "h4"])
                if not title_tag:
                    continue
                link = title_tag.find("a") or item.find("a", href=True)
                if not link:
                    continue
                title = title_tag.get_text(strip=True)
                href = link.get("href", "")
                if not href.startswith("http"):
                    href = BASE_URL + href
                if not title or len(title) < 5:
                    continue
                text = item.get_text(" ", strip=True)
                deadline_m = re.search(r"[Dd]eadline[:\s]+([^\n|]+)", text)
                amount_m = re.search(r"(\$[\d,]+|€[\d,]+|fully funded|stipend)", text, re.I)
                degree_m = re.search(r"(undergraduate|bachelor|master|graduate|ph\.?d)", text, re.I)
                org_m = item.find(class_=re.compile(r"org|sponsor|provider|university|school", re.I))
                results.append(make_scholarship(
                    title=title,
                    source_url=href,
                    source_site=SITE_NAME,
                    organization=org_m.get_text(strip=True) if org_m else None,
                    degree_levels_raw=degree_m.group(0) if degree_m else "any",
                    deadline_raw=deadline_m.group(1).strip() if deadline_m else None,
                    amount=amount_m.group(0) if amount_m else None,
                    tags=["study abroad"],
                ))
                found += 1
            if found == 0:
                break
            page += 1
        return results
