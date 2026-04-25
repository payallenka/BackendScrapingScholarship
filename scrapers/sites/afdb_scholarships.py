"""African Development Bank Group Scholarships — hardcoded programs + dynamic deadline fetch."""
from __future__ import annotations
from typing import List
from scrapers.base import BaseScraper
from scrapers.normalizer import NormalizedScholarship, make_scholarship, find_deadline_in_text

SITE_NAME = "African Development Bank"
BASE_URL = "https://www.afdb.org"

PROGRAMS = [
    {
        "title": "African Development Bank Japan Scholarship Program (AfDB-JSP)",
        "url": f"{BASE_URL}/en/careers/scholarships#japan-scholarship",
        "description": (
            "The AfDB Japan Scholarship Program offers scholarships to highly qualified Africans to pursue "
            "postgraduate studies at designated academic institutions in Japan, in fields related to "
            "economic and social development. Fully funded: covers tuition, monthly allowance, airfare, "
            "and health insurance."
        ),
        "degree_levels_raw": "masters phd",
        "host_countries": ["Japan"],
        "tags": ["AfDB", "Africa", "Japan", "development", "postgraduate", "fully funded"],
    },
    {
        "title": "AfDB Graduate Research Fellowship Program",
        "url": f"{BASE_URL}/en/careers/scholarships#research-fellowship",
        "description": (
            "The AfDB Graduate Research Fellowship supports outstanding African researchers and "
            "graduate students working on topics directly related to Africa's development challenges. "
            "Fellows receive funding to conduct their research at the AfDB headquarters or in the field."
        ),
        "degree_levels_raw": "masters phd",
        "host_countries": [],
        "tags": ["AfDB", "Africa", "research", "fellowship", "development", "stipend"],
    },
    {
        "title": "AfDB Presidential Fellowship Program",
        "url": f"{BASE_URL}/en/careers/scholarships#presidential-fellowship",
        "description": (
            "The African Development Bank Presidential Fellowship recruits exceptional young professionals "
            "from African countries and the diaspora to work on high-impact projects within the Bank. "
            "Fellows work directly with senior Bank management. Fully funded with salary, housing, and insurance."
        ),
        "degree_levels_raw": "masters phd fellowship",
        "host_countries": ["Ivory Coast"],
        "tags": ["AfDB", "Africa", "presidential fellowship", "leadership", "development bank"],
    },
]


class AfDBScholarshipScraper(BaseScraper):
    name = "afdb_scholarships"
    base_url = BASE_URL
    delay = 2.0

    def scrape(self) -> List[NormalizedScholarship]:
        deadline_raw = None
        soup = self.get_soup(f"{BASE_URL}/en/careers/scholarships")
        if soup:
            deadline_raw = find_deadline_in_text(soup.get_text(" ", strip=True))

        results = []
        for prog in PROGRAMS:
            results.append(make_scholarship(
                title=prog["title"],
                source_url=prog["url"],
                source_site=SITE_NAME,
                organization="African Development Bank Group (AfDB)",
                description=prog["description"],
                degree_levels_raw=prog["degree_levels_raw"],
                deadline_raw=deadline_raw,
                amount="Fully Funded",
                eligible_nationalities=["African"],
                host_countries=prog.get("host_countries", []),
                tags=prog["tags"],
            ))
        return results
