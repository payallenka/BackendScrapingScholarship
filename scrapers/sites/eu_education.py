"""Scraper for EU education.ec.europa.eu scholarships and funding page."""
from __future__ import annotations
import re
from typing import List
from scrapers.base import BaseScraper
from scrapers.normalizer import NormalizedScholarship, make_scholarship

SITE_NAME = "EU Education Portal"
BASE_URL = "https://education.ec.europa.eu"
LIST_URL = f"{BASE_URL}/study-in-europe/planning-your-studies/scholarships-and-funding"


class EUEducationScraper(BaseScraper):
    name = "eu_education"
    base_url = BASE_URL
    delay = 2.0

    def scrape(self) -> List[NormalizedScholarship]:
        results = []
        soup = self.get_soup(LIST_URL)
        if not soup:
            return results

        # EU Education page typically has programme tiles/cards
        items = (
            soup.find_all("div", class_=re.compile(r"card|item|programme|scholarship|listing|tile", re.I))
            or soup.find_all("article")
            or soup.find_all("li", class_=re.compile(r"programme|scholarship", re.I))
        )

        for item in items:
            title_tag = item.find(["h2", "h3", "h4"])
            if not title_tag:
                continue
            link = title_tag.find("a") or item.find("a", href=True)
            if not link:
                continue
            title = title_tag.get_text(strip=True)
            if not title or len(title) < 5:
                continue
            href = link.get("href", "")
            if not href.startswith("http"):
                href = BASE_URL + href
            text = item.get_text(" ", strip=True)
            deadline_m = re.search(r"[Dd]eadline[:\s]+([^\n|<.]+)", text)
            amount_m = re.search(r"(€[\d,]+|\$[\d,]+|fully funded|stipend|grant)", text, re.I)
            degree_m = re.search(r"(undergraduate|bachelor|master|graduate|ph\.?d|doctoral)", text, re.I)
            results.append(make_scholarship(
                title=title,
                source_url=href,
                source_site=SITE_NAME,
                degree_levels_raw=degree_m.group(0) if degree_m else "any",
                deadline_raw=deadline_m.group(1).strip() if deadline_m else None,
                amount=amount_m.group(0) if amount_m else None,
                host_countries=["Europe"],
                tags=["EU", "Europe"],
            ))

        # Also look for inline links to programmes (text-based listing)
        if not results:
            for a in soup.find_all("a", href=re.compile(r"erasmus|horizon|marie|scholarship|fund", re.I)):
                title = a.get_text(strip=True)
                if not title or len(title) < 8:
                    continue
                href = a.get("href", "")
                if not href.startswith("http"):
                    href = BASE_URL + href
                results.append(make_scholarship(
                    title=title,
                    source_url=href,
                    source_site=SITE_NAME,
                    degree_levels_raw="any",
                    host_countries=["Europe"],
                    tags=["EU", "Europe"],
                ))

        return results
