"""Campus France — scrapes real scholarship listings from bursaries page."""
from __future__ import annotations
from typing import List
from scrapers.base import BaseScraper
from scrapers.normalizer import NormalizedScholarship, make_scholarship, find_deadline_in_text

SITE_NAME = "Campus France"
BASE_URL = "https://www.campusfrance.org"
LISTING_URL = f"{BASE_URL}/en/bursaries-foreign-students"

# Confirmed scholarship pages from the listing page
KNOWN_PROGRAMS = [
    ("/en/france-excellence-eiffel-scholarship-program",
     "France Excellence – Eiffel Scholarship Program"),
    ("/en/france-excellence-europa-scholarship-program",
     "France Excellence – Europa Scholarship Program"),
    ("/en/make-our-planet-great-again-en",
     "Make Our Planet Great Again (MOPGA) Research Grant"),
    ("/en/phc",
     "Hubert Curien Partnerships (PHC) – Scholarship Program"),
]

SCHOLARSHIP_PATH_KEYWORDS = (
    "scholarship", "bursari", "grant", "fund", "bourse",
    "eiffel", "mopga", "phc", "europa", "erasmus", "fellowship",
)


class CampusFranceScraper(BaseScraper):
    name = "campusfrance"
    base_url = BASE_URL
    delay = 1.5

    def scrape(self) -> List[NormalizedScholarship]:
        results = []
        seen = set()

        soup = self.get_soup(LISTING_URL)
        scraped = []
        if soup:
            for a in soup.find_all("a", href=True):
                href = a["href"]
                txt = a.get_text(strip=True)
                # Strip common noise prefixes/suffixes added by CMS rendering
                txt = txt.replace("ArticleImage", "").replace("Discover", "").strip()
                if (
                    href.startswith("/en/")
                    and txt and len(txt) > 10
                    and any(k in href.lower() or k in txt.lower() for k in SCHOLARSHIP_PATH_KEYWORDS)
                    and href not in seen
                    and "node/" not in href
                    and "organising" not in href
                    and "rights-and-obligations" not in href
                    and "tuition-fees" not in href
                    and "budget" not in href
                    and "bursaries-foreign-students" not in href
                    and txt.lower() not in (
                        "scholarships programmes", "grants and financial aid",
                        "scholarships for french students or students living in france",
                        "finance your studies",
                    )
                ):
                    full = BASE_URL + href
                    if full not in seen:
                        seen.add(full)
                        scraped.append((full, txt))

        # Add known programs not found dynamically
        for path, title in KNOWN_PROGRAMS:
            full = BASE_URL + path
            if full not in seen:
                seen.add(full)
                scraped.append((full, title))

        for url, title in scraped[:self.max_pages * 3]:
            description, deadline_raw = None, None
            detail = self.get_soup(url)
            if detail:
                text = detail.get_text(" ", strip=True)
                deadline_raw = find_deadline_in_text(text)
                paras = detail.find_all("p")
                if paras:
                    description = " ".join(p.get_text(strip=True) for p in paras[:4])[:600]

            title_l = title.lower()
            if any(k in title_l for k in ("phd", "doctoral", "doctorate", "post-doc")):
                degree_raw = "phd postdoctoral"
            elif any(k in title_l for k in ("master", "graduate", "postgraduate")):
                degree_raw = "masters"
            else:
                degree_raw = "masters phd"

            results.append(make_scholarship(
                title=title,
                source_url=url,
                source_site=SITE_NAME,
                organization="Campus France / French Ministry of Europe and Foreign Affairs",
                description=description,
                degree_levels_raw=degree_raw,
                deadline_raw=deadline_raw,
                amount=None,
                host_countries=["France"],
                tags=["Campus France", "France", "scholarship"],
            ))

        return results
