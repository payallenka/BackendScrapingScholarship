"""EduCanada — scrapes real international scholarship listings."""
from __future__ import annotations
from typing import List
from scrapers.base import BaseScraper
from scrapers.normalizer import NormalizedScholarship, make_scholarship, find_deadline_in_text

SITE_NAME = "EduCanada"
BASE_URL = "https://www.educanada.ca"
INTL_URL = f"{BASE_URL}/scholarships-bourses/non_can/index.aspx?lang=eng"

# Known scholarship detail pages confirmed from the listing page
KNOWN_PROGRAMS = [
    ("/scholarships-bourses/can/institutions/elap-pfla.aspx?lang=eng",
     "Emerging Leaders in the Americas Program (ELAP)"),
    ("/scholarships-bourses/can/institutions/study-in-canada-sep-etudes-au-canada-pct.aspx?lang=eng",
     "Study in Canada Scholarships"),
    ("/scholarships-bourses/can/institutions/seed-bpeed.aspx?lang=eng",
     "Scholarships and Educational Exchanges for Development – Phase 2 (SEED-2)"),
    ("/scholarships-bourses/non_can/ccsep-peucc.aspx?lang=eng",
     "Canada-China Scholars' Exchange Program"),
    ("/scholarships-bourses/non_can/bcdi2030.aspx?lang=eng",
     "Canadian International Development Scholarships 2030 (BCDI2030)"),
    ("/scholarships-bourses/non_can/institutions/oas-oea.aspx?lang=eng",
     "Organization of American States Academic Scholarships Program"),
]


class EduCanadaScraper(BaseScraper):
    name = "educanada"
    base_url = BASE_URL
    delay = 1.5

    def scrape(self) -> List[NormalizedScholarship]:
        results = []
        seen = set()

        # First collect links from the listing page dynamically
        soup = self.get_soup(INTL_URL)
        scraped_links = []
        if soup:
            for a in soup.find_all("a", href=True):
                href = a["href"]
                txt = a.get_text(strip=True)
                if (
                    href not in seen
                    and txt and len(txt) > 10
                    and txt.lower() not in ("frequently asked questions", "faq", "contact us", "home")
                    and ("scholar" in href.lower() or "fellow" in href.lower()
                         or "elap" in href.lower() or "bcdi" in href.lower()
                         or "oas-oea" in href.lower() or "seed" in href.lower()
                         or "ccsep" in href.lower())
                    and "news" not in href.lower()
                    and "index" not in href.lower()
                    and "search" not in href.lower()
                    and "faq" not in href.lower()
                ):
                    full = href if href.startswith("http") else BASE_URL + href
                    if full not in seen:
                        seen.add(full)
                        scraped_links.append((full, txt))

        # Fall back to known programs for any not found dynamically
        for path, title in KNOWN_PROGRAMS:
            full = BASE_URL + path
            if full not in seen:
                seen.add(full)
                scraped_links.append((full, title))

        for url, title in scraped_links[:self.max_pages * 3]:
            description, deadline_raw = None, None
            detail = self.get_soup(url)
            if detail:
                text = detail.get_text(" ", strip=True)
                deadline_raw = find_deadline_in_text(text)
                paras = detail.find_all("p")
                if paras:
                    description = " ".join(p.get_text(strip=True) for p in paras[:4])[:600]

            title_l = title.lower()
            if any(k in title_l for k in ("phd", "doctoral", "doctorate")):
                degree_raw = "phd"
            elif any(k in title_l for k in ("master", "graduate")):
                degree_raw = "masters"
            elif "undergraduate" in title_l:
                degree_raw = "undergraduate"
            else:
                degree_raw = "undergraduate masters phd"

            results.append(make_scholarship(
                title=title,
                source_url=url,
                source_site=SITE_NAME,
                organization="Government of Canada / EduCanada",
                description=description,
                degree_levels_raw=degree_raw,
                deadline_raw=deadline_raw,
                amount=None,
                host_countries=["Canada"],
                tags=["EduCanada", "Canada", "government", "international"],
            ))

        return results
