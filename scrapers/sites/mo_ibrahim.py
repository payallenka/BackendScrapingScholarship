"""Mo Ibrahim Foundation — scrapes real fellowship and scholarship pages."""
from __future__ import annotations
from typing import List
from scrapers.base import BaseScraper
from scrapers.normalizer import NormalizedScholarship, make_scholarship, find_deadline_in_text

SITE_NAME = "Mo Ibrahim Foundation"
BASE_URL = "https://mo.ibrahim.foundation"

PAGES = [
    (f"{BASE_URL}/fellowships", "The Ibrahim Leadership Fellowships", "fellowship masters phd"),
    (f"{BASE_URL}/scholarships", "Ibrahim Scholarships", "masters fellowship"),
]

SCHOLARSHIP_SECTIONS = {
    "university of birmingham": (
        "University of Birmingham – Mo Ibrahim MSc Scholarship",
        "masters",
    ),
    "chatham house": (
        "Chatham House – Mo Ibrahim Academy Fellowship",
        "fellowship",
    ),
}


class MoIbrahimScraper(BaseScraper):
    name = "mo_ibrahim"
    base_url = BASE_URL
    delay = 2.0

    def scrape(self) -> List[NormalizedScholarship]:
        results = []
        seen = set()

        for url, fallback_title, degree_raw in PAGES:
            soup = self.get_soup(url)
            if not soup:
                continue

            full_text = soup.get_text(" ", strip=True)
            deadline_raw = find_deadline_in_text(full_text)

            h1 = soup.find("h1")
            title = h1.get_text(strip=True) if h1 else fallback_title

            paras = soup.find_all("p")
            description = " ".join(p.get_text(strip=True) for p in paras[:4])[:600] if paras else None

            if url not in seen:
                seen.add(url)
                results.append(make_scholarship(
                    title=title,
                    source_url=url,
                    source_site=SITE_NAME,
                    organization="Mo Ibrahim Foundation",
                    description=description,
                    degree_levels_raw=degree_raw,
                    deadline_raw=deadline_raw,
                    amount="Fully Funded",
                    eligible_nationalities=["African"],
                    host_countries=["UK"],
                    tags=["Mo Ibrahim", "Africa", "leadership", "governance", "fellowship"],
                ))

            # On the /scholarships page, extract sub-scholarships by h3 sections
            if "/scholarships" in url:
                for h3 in soup.find_all("h3"):
                    h3_text = h3.get_text(strip=True).lower()
                    for keyword, (sub_title, sub_degree) in SCHOLARSHIP_SECTIONS.items():
                        if keyword in h3_text and sub_title not in seen:
                            seen.add(sub_title)
                            # Collect paragraphs following this h3
                            sub_paras = []
                            for sib in h3.find_next_siblings():
                                if sib.name in ("h3", "h2", "h1"):
                                    break
                                if sib.name == "p":
                                    sub_paras.append(sib.get_text(strip=True))
                            sub_desc = " ".join(sub_paras[:3])[:600] or None

                            results.append(make_scholarship(
                                title=sub_title,
                                source_url=url,
                                source_site=SITE_NAME,
                                organization="Mo Ibrahim Foundation",
                                description=sub_desc,
                                degree_levels_raw=sub_degree,
                                deadline_raw=deadline_raw,
                                amount="Fully Funded",
                                eligible_nationalities=["African"],
                                host_countries=["UK"],
                                tags=["Mo Ibrahim", "Africa", "governance", "scholarship"],
                            ))

        return results
