"""Commonwealth Scholarship Commission — scrapes real listing page."""
from __future__ import annotations
from typing import List
from scrapers.base import BaseScraper
from scrapers.normalizer import NormalizedScholarship, make_scholarship, find_deadline_in_text

SITE_NAME = "Commonwealth Scholarship"
BASE_URL = "https://cscuk.fcdo.gov.uk"
LISTING_URL = f"{BASE_URL}/scholarships/"

DEGREE_HINTS = {
    "master": "masters",
    "distance": "masters",
    "shared": "masters",
    "phd": "phd",
    "doctoral": "phd",
    "split": "phd",
    "fellowship": "fellowship",
    "startup": "fellowship",
    "professional": "fellowship",
}


class CommonwealthScholarshipScraper(BaseScraper):
    name = "commonwealth_scholarship"
    base_url = BASE_URL
    delay = 1.5

    def scrape(self) -> List[NormalizedScholarship]:
        results = []
        seen = set()

        soup = self.get_soup(LISTING_URL)
        if not soup:
            return results

        # Each scholarship is an <h2> with an <a> child linking to its detail page
        for h2 in soup.find_all("h2"):
            a = h2.find("a", href=True)
            if not a:
                continue
            href = a["href"]
            if not href.startswith("http"):
                href = BASE_URL + href
            if href in seen or href == LISTING_URL:
                continue
            seen.add(href)

            title = a.get_text(strip=True)
            if not title or len(title) < 8:
                continue

            # Degree level from title keywords
            title_l = title.lower()
            degree_raw = next((v for k, v in DEGREE_HINTS.items() if k in title_l), "postgraduate")

            # Fetch detail page for description + deadline
            description, deadline_raw = None, None
            detail = self.get_soup(href)
            if detail:
                text = detail.get_text(" ", strip=True)
                deadline_raw = find_deadline_in_text(text)
                paras = detail.find_all("p")
                if paras:
                    description = " ".join(p.get_text(strip=True) for p in paras[:4])[:600]

            # Nationality eligibility from title
            nat = []
            if "high income" in title_l:
                nat = ["Commonwealth citizens (high income countries)"]
            elif "least developed" in title_l or "low" in title_l:
                nat = ["Commonwealth citizens (least developed countries)"]
            else:
                nat = ["Commonwealth citizens"]

            results.append(make_scholarship(
                title=title,
                source_url=href,
                source_site=SITE_NAME,
                organization="Commonwealth Scholarship Commission (CSC)",
                description=description,
                degree_levels_raw=degree_raw,
                deadline_raw=deadline_raw,
                amount="Fully Funded",
                eligible_nationalities=nat,
                host_countries=["UK"],
                tags=["Commonwealth", "UK", "FCDO", "CSC", "fully funded"],
            ))

        return results
