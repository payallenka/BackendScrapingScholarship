"""French Government Scholarship BGF — scrapes from diplomatie.gouv.fr and Campus France."""
from __future__ import annotations
from typing import List
from scrapers.base import BaseScraper
from scrapers.normalizer import NormalizedScholarship, make_scholarship, find_deadline_in_text

SITE_NAME = "French Gov Scholarship (BGF)"
BASE_URL = "https://www.diplomatie.gouv.fr"
# Try several entry points — the old deep path connection-refuses; the
# foreign-policy scholarships page currently works. First one that loads wins.
SCHOLARSHIPS_URLS = [
    f"{BASE_URL}/en/french-foreign-policy/attractiveness-and-france-s-influence/scholarships/",
    f"{BASE_URL}/en/coming-to-france/studying-in-france/finance-your-studies-scholarships/",
    f"{BASE_URL}/en/",
]
CAMPUSFRANCE_BASE = "https://www.campusfrance.org"

# Extra hardcoded programme pages. The previous two (AEFE, Campus Bourses) are
# dead (404 / SSL-broken) and were removed; the main scholarships page above is
# the reliable source now.
EXTRA_PROGRAMS = []

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

        # --- diplomatie.gouv.fr main scholarships page (try entry points in order) ---
        soup, scholarships_url = None, SCHOLARSHIPS_URLS[0]
        for candidate in SCHOLARSHIPS_URLS:
            soup = self.get_soup(candidate)
            if soup:
                scholarships_url = candidate
                break
        if soup:
            deadline_raw = self.crawl_deadline(soup, scholarships_url)
            # diplomatie.gouv.fr's <h1> is the generic site header ("The Ministry
            # in action"), so use a fixed, meaningful programme title.
            title = "French Government Scholarship (BGF)"
            paras = soup.find_all("p")
            description = " ".join(p.get_text(strip=True) for p in paras[:4])[:600] if paras else None

            results.append(make_scholarship(
                title=title,
                source_url=scholarships_url,
                source_site=SITE_NAME,
                organization="French Ministry for Europe and Foreign Affairs",
                description=description,
                degree_levels_raw="undergraduate masters phd",
                deadline_raw=deadline_raw,
                amount="Monthly stipend + tuition waiver + health insurance",
                host_countries=["France"],
                tags=["BGF", "French government", "France", "bourse", "embassy"],
            ))
            seen.add(scholarships_url)

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
                    if full in seen or full == scholarships_url:
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
            if not detail:
                # Page unreachable (404 / SSL / timeout) — skip rather than emit a
                # scholarship that links to a dead page.
                continue

            text = detail.get_text(" ", strip=True)
            d_dl = find_deadline_in_text(text)
            d_title = fallback_title
            h1 = detail.find("h1")
            if h1 and len(h1.get_text(strip=True)) > 8:
                d_title = h1.get_text(strip=True)
            ps = detail.find_all("p")
            d_desc = " ".join(p.get_text(strip=True) for p in ps[:4])[:600] if ps else None

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
