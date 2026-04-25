"""Fulbright Program — scrapes real program pages."""
from __future__ import annotations
from typing import List
from scrapers.base import BaseScraper
from scrapers.normalizer import NormalizedScholarship, make_scholarship, find_deadline_in_text

SITE_NAME = "Fulbright Program"
BASE_URL = "https://foreign.fulbrightonline.org"
VISITING_SCHOLAR_URL = "https://fulbrightscholars.org/non-us-scholars/fulbright-visiting-scholar-program"

PROGRAM_PAGES = [
    (f"{BASE_URL}/about/foreign-student-program", "Fulbright Foreign Student Program", "masters phd"),
    (f"{BASE_URL}/about/flta-program", "Fulbright FLTA Program", "fellowship"),
    (VISITING_SCHOLAR_URL, "Fulbright Visiting Scholar Program", "postdoctoral fellowship"),
]


class FulbrightScraper(BaseScraper):
    name = "fulbright"
    base_url = BASE_URL
    delay = 2.0

    def scrape(self) -> List[NormalizedScholarship]:
        results = []

        # Fetch main page once for a shared deadline hint
        main_soup = self.get_soup(BASE_URL)
        global_deadline = None
        if main_soup:
            global_deadline = find_deadline_in_text(main_soup.get_text(" ", strip=True))

        for url, fallback_title, degree_raw in PROGRAM_PAGES:
            soup = self.get_soup(url)
            description, deadline_raw = None, global_deadline

            if soup:
                text = soup.get_text(" ", strip=True)
                deadline_raw = find_deadline_in_text(text) or global_deadline
                # Some pages have two h1s; pick the one that isn't a site-wide header
                h1s = soup.find_all("h1")
                title = fallback_title
                for h in h1s:
                    t = h.get_text(strip=True)
                    if len(t) > 15 and "Foreign Fulbright Program -" not in t:
                        title = t
                        break
                paras = soup.find_all("p")
                if paras:
                    description = " ".join(p.get_text(strip=True) for p in paras[:5])[:600]
            else:
                title = fallback_title

            results.append(make_scholarship(
                title=title,
                source_url=url,
                source_site=SITE_NAME,
                organization="Fulbright Program / U.S. Department of State",
                description=description,
                degree_levels_raw=degree_raw,
                deadline_raw=deadline_raw,
                amount="Fully Funded",
                host_countries=["USA"],
                tags=["Fulbright", "USA", "US government", "fully funded", "State Department"],
            ))

        return results
