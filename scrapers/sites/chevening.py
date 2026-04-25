"""Chevening Scholarship — hardcoded programs + dynamic deadline fetch."""
from __future__ import annotations
from typing import List
from scrapers.base import BaseScraper
from scrapers.normalizer import NormalizedScholarship, make_scholarship, find_deadline_in_text

SITE_NAME = "Chevening Scholarship"
BASE_URL = "https://www.chevening.org"

PROGRAMS = [
    {
        "title": "Chevening Scholarship",
        "url": f"{BASE_URL}/scholarships/#chevening-scholarship",
        "description": (
            "Chevening Scholarships are the UK government's global scholarship programme, funded by the "
            "Foreign, Commonwealth and Development Office (FCDO) and partner organisations. "
            "Awarded to individuals with demonstrable leadership potential who wish to pursue a one-year "
            "master's degree at any UK university. Fully funded: tuition fees, living expenses, "
            "return airfare, and all other allowances are covered."
        ),
        "degree_levels_raw": "masters",
        "tags": ["Chevening", "UK", "FCDO", "government", "fully funded", "leadership", "masters"],
    },
    {
        "title": "Chevening Fellowship",
        "url": f"{BASE_URL}/scholarships/#chevening-fellowship",
        "description": (
            "Chevening Fellowships are short, tailor-made programmes designed by UK universities in "
            "collaboration with the FCDO. They bring mid-career professionals from across the world to "
            "the UK for short-term development and networking opportunities, including covering all fees, "
            "travel, accommodation, and subsistence."
        ),
        "degree_levels_raw": "fellowship",
        "tags": ["Chevening", "UK", "FCDO", "fellowship", "mid-career", "professional development"],
    },
]


class CheveningScraper(BaseScraper):
    name = "chevening"
    base_url = BASE_URL
    delay = 2.0

    def scrape(self) -> List[NormalizedScholarship]:
        # chevening.org can timeout — try once for deadline, continue regardless
        deadline_raw = None
        soup = self.get_soup(f"{BASE_URL}/scholarships/")
        if soup:
            deadline_raw = find_deadline_in_text(soup.get_text(" ", strip=True))

        results = []
        for prog in PROGRAMS:
            results.append(make_scholarship(
                title=prog["title"],
                source_url=prog["url"],
                source_site=SITE_NAME,
                organization="UK Foreign, Commonwealth & Development Office (FCDO)",
                description=prog["description"],
                degree_levels_raw=prog["degree_levels_raw"],
                deadline_raw=deadline_raw,
                amount="Fully Funded",
                host_countries=["UK"],
                tags=prog["tags"],
            ))
        return results
