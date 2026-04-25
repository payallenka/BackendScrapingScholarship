"""EducationUSA — scrapes real U.S. scholarship program pages."""
from __future__ import annotations
from typing import List
from scrapers.base import BaseScraper
from scrapers.normalizer import NormalizedScholarship, make_scholarship, find_deadline_in_text

SITE_NAME = "EducationUSA"
BASE_URL = "https://educationusa.state.gov"
HUMPHREY_URL = "https://www.humphreyfellowship.org"

# Real pages with scholarship content
PROGRAM_PAGES = [
    (
        f"{BASE_URL}/your-5-steps-us-study/finance-your-studies/graduate",
        "U.S. Graduate Scholarships for International Students (EducationUSA)",
        "masters phd",
    ),
    (
        f"{BASE_URL}/your-5-steps-us-study/finance-your-studies/undergraduate",
        "U.S. Undergraduate Scholarships for International Students (EducationUSA)",
        "undergraduate",
    ),
    (
        f"{BASE_URL}/your-5-steps-us-study/finance-your-studies/community-college",
        "U.S. Community College Scholarships for International Students (EducationUSA)",
        "undergraduate",
    ),
    (
        HUMPHREY_URL,
        "Hubert H. Humphrey Fellowship Program",
        "fellowship",
    ),
]

SCHOLARSHIP_LINK_KEYWORDS = (
    "scholarship", "fellowship", "fulbright", "grant", "fund", "award",
    "opportunity", "humphrey", "finance",
)


class EducationUSAScraper(BaseScraper):
    name = "educationusa"
    base_url = BASE_URL
    delay = 2.0

    def scrape(self) -> List[NormalizedScholarship]:
        results = []
        seen = set()

        for url, fallback_title, degree_raw in PROGRAM_PAGES:
            soup = self.get_soup(url)
            description, deadline_raw = None, None
            title = fallback_title

            if soup:
                text = soup.get_text(" ", strip=True)
                deadline_raw = find_deadline_in_text(text)
                h1 = soup.find("h1")
                if h1:
                    h1_text = h1.get_text(strip=True)
                    if len(h1_text) > 8:
                        title = h1_text
                paras = soup.find_all("p")
                if paras:
                    description = " ".join(p.get_text(strip=True) for p in paras[:5])[:600]

            if url not in seen:
                seen.add(url)
                results.append(make_scholarship(
                    title=title,
                    source_url=url,
                    source_site=SITE_NAME,
                    organization="U.S. Department of State / EducationUSA",
                    description=description,
                    degree_levels_raw=degree_raw,
                    deadline_raw=deadline_raw,
                    amount="Fully Funded" if "humphrey" in url else None,
                    host_countries=["USA"],
                    tags=["EducationUSA", "USA", "State Department", "international"],
                ))

            # Follow scholarship-related sub-links from main pages (only for educationusa.state.gov)
            if soup and BASE_URL in url:
                for a in soup.find_all("a", href=True):
                    href = a["href"]
                    txt = a.get_text(strip=True)
                    if (
                        txt and len(txt) > 10
                        and any(k in (href + txt).lower() for k in SCHOLARSHIP_LINK_KEYWORDS)
                        and href.startswith("/")
                        and href not in seen
                        and "finance-your-studies" not in href
                        and "step" not in href
                        and "higher-education-professionals" not in href
                        and "leveraging" not in href
                    ):
                        full = BASE_URL + href
                        if full in seen:
                            continue
                        seen.add(full)

                        detail = self.get_soup(full)
                        d_desc, d_dl = None, None
                        d_title = txt
                        if detail:
                            d_text = detail.get_text(" ", strip=True)
                            d_dl = find_deadline_in_text(d_text)
                            dh1 = detail.find("h1")
                            if dh1 and len(dh1.get_text(strip=True)) > 8:
                                d_title = dh1.get_text(strip=True)
                            dps = detail.find_all("p")
                            if dps:
                                d_desc = " ".join(p.get_text(strip=True) for p in dps[:4])[:600]

                        results.append(make_scholarship(
                            title=d_title,
                            source_url=full,
                            source_site=SITE_NAME,
                            organization="U.S. Department of State / EducationUSA",
                            description=d_desc,
                            degree_levels_raw=degree_raw,
                            deadline_raw=d_dl,
                            amount=None,
                            host_countries=["USA"],
                            tags=["EducationUSA", "USA", "State Department", "scholarship"],
                        ))

                        if len(results) >= self.max_pages * 4:
                            return results

        return results
