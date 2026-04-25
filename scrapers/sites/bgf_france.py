"""French Government Scholarship BGF — scrapes from diplomatie.gouv.fr and Campus France."""
from __future__ import annotations
from typing import List
from scrapers.base import BaseScraper
from scrapers.normalizer import NormalizedScholarship, make_scholarship, find_deadline_in_text

SITE_NAME = "French Gov Scholarship (BGF)"
BASE_URL = "https://www.diplomatie.gouv.fr"
SCHOLARSHIPS_URL = (
    f"{BASE_URL}/en/coming-to-france/studying-in-france/finance-your-studies-scholarships/"
)
CAMPUSFRANCE_BASE = "https://www.campusfrance.org"

# Additional French government scholarship pages (distinct from CampusFrance scraper)
EXTRA_PROGRAMS = [
    (
        "https://aefe.gouv.fr/en/aefe/implementing-ministry-europe-and-foreign-affairs/france-excellence-major-scholarship-program",
        "France Excellence Major Scholarship Program (AEFE)",
        "masters",
    ),
    (
        "https://www.campusbourses.campusfrance.org/fria/bourse",
        "Campus Bourses – French Government Scholarship Catalog",
        "undergraduate masters phd",
    ),
]

SCHOLARSHIP_KEYWORDS = (
    "scholarship", "bourse", "grant", "fellowship", "eiffel", "mopga",
    "phc", "europa", "finance", "fund",
)


class BGFFranceScraper(BaseScraper):
    name = "bgf_france"
    base_url = BASE_URL
    delay = 1.5

    def scrape(self) -> List[NormalizedScholarship]:
        results = []
        seen = set()

        # --- diplomatie.gouv.fr main scholarships page ---
        soup = self.get_soup(SCHOLARSHIPS_URL)
        if soup:
            full_text = soup.get_text(" ", strip=True)
            deadline_raw = find_deadline_in_text(full_text)
            h1 = soup.find("h1")
            title = h1.get_text(strip=True) if h1 else "French Government Scholarships (BGF)"
            paras = soup.find_all("p")
            description = " ".join(p.get_text(strip=True) for p in paras[:4])[:600] if paras else None

            results.append(make_scholarship(
                title=title or "French Government Scholarships (BGF)",
                source_url=SCHOLARSHIPS_URL,
                source_site=SITE_NAME,
                organization="French Ministry for Europe and Foreign Affairs",
                description=description,
                degree_levels_raw="undergraduate masters phd",
                deadline_raw=deadline_raw,
                amount="Monthly stipend + tuition waiver + health insurance",
                host_countries=["France"],
                tags=["BGF", "French government", "France", "bourse", "embassy"],
            ))
            seen.add(SCHOLARSHIPS_URL)

            # Follow scholarship sub-links on the same domain
            for a in soup.find_all("a", href=True):
                href = a["href"]
                txt = a.get_text(strip=True)
                if (
                    txt and len(txt) > 10
                    and any(k in (href + txt).lower() for k in SCHOLARSHIP_KEYWORDS)
                    and href not in seen
                    and ("diplomatie.gouv.fr" in href or href.startswith("/en/"))
                    and "diplomate" not in href
                    and "diplomat" not in href.lower()
                ):
                    full = href if href.startswith("http") else BASE_URL + href
                    if full in seen or full == SCHOLARSHIPS_URL:
                        continue
                    seen.add(full)

                    detail = self.get_soup(full)
                    d_desc, d_dl = None, deadline_raw
                    if detail:
                        text = detail.get_text(" ", strip=True)
                        d_dl = find_deadline_in_text(text) or deadline_raw
                        ps = detail.find_all("p")
                        if ps:
                            d_desc = " ".join(p.get_text(strip=True) for p in ps[:4])[:600]

                    results.append(make_scholarship(
                        title=txt,
                        source_url=full,
                        source_site=SITE_NAME,
                        organization="French Ministry for Europe and Foreign Affairs",
                        description=d_desc,
                        degree_levels_raw="masters phd",
                        deadline_raw=d_dl,
                        amount="Fully Funded",
                        host_countries=["France"],
                        tags=["BGF", "French government", "France", "bourse"],
                    ))

                    if len(results) >= self.max_pages * 2:
                        break

        # --- Campus France program pages ---
        for url, fallback_title, degree_raw in EXTRA_PROGRAMS:
            if url in seen:
                continue
            seen.add(url)

            detail = self.get_soup(url)
            d_desc, d_dl = None, None
            d_title = fallback_title
            if detail:
                text = detail.get_text(" ", strip=True)
                d_dl = find_deadline_in_text(text)
                h1 = detail.find("h1")
                if h1 and len(h1.get_text(strip=True)) > 8:
                    d_title = h1.get_text(strip=True)
                ps = detail.find_all("p")
                if ps:
                    d_desc = " ".join(p.get_text(strip=True) for p in ps[:4])[:600]

            results.append(make_scholarship(
                title=d_title,
                source_url=url,
                source_site=SITE_NAME,
                organization="French Government / Campus France",
                description=d_desc,
                degree_levels_raw=degree_raw,
                deadline_raw=d_dl,
                amount="Fully Funded",
                host_countries=["France"],
                tags=["BGF", "French government", "France", "Campus France", "Eiffel"],
            ))

        return results
