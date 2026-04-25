"""MasterCard Foundation Scholars Program — scrapes real program pages."""
from __future__ import annotations
from typing import List
from scrapers.base import BaseScraper
from scrapers.normalizer import NormalizedScholarship, make_scholarship, find_deadline_in_text

SITE_NAME = "MasterCard Foundation Scholars"
BASE_URL = "https://mastercardfdn.org"
SCHOLARS_URL = f"{BASE_URL}/en/what-we-do/our-programs/mastercard-foundation-scholars-program/"
WHERE_URL = f"{BASE_URL}/en/what-we-do/our-programs/mastercard-foundation-scholars-program/where-to-apply/"

# Known partner institutions (partner list loads via JS so we hardcode them)
KNOWN_PARTNERS = [
    ("https://www.africau.edu/", "Africa University", "undergraduate masters"),
    ("https://www.ait.ac.tz/", "African Institute of Technology (AIT)", "undergraduate masters"),
    ("https://www.ashesi.edu.gh/", "Ashesi University", "undergraduate"),
    ("https://www.strathmore.edu/", "Strathmore University", "undergraduate masters"),
    ("https://www.uct.ac.za/", "University of Cape Town", "undergraduate masters phd"),
    ("https://www.makerere.ac.ug/", "Makerere University", "undergraduate masters"),
    ("https://www.riara.ac.ke/", "Riara University", "undergraduate masters"),
    ("https://www.usiu.ac.ke/", "United States International University – Africa", "undergraduate masters"),
    ("https://www.mcmaster.ca/", "McMaster University", "masters phd"),
    ("https://www.arizona.edu/", "University of Arizona", "undergraduate masters"),
]

PARTNER_KEYWORDS = (
    "university", "college", "institute", "school", "académie",
)

DEGREE_KEYWORDS = {
    "phd": "phd",
    "doctoral": "phd",
    "doctorate": "phd",
    "master": "masters",
    "postgraduate": "masters",
    "graduate": "masters",
    "undergraduate": "undergraduate",
    "bachelor": "undergraduate",
}


class MasterCardFoundationScraper(BaseScraper):
    name = "mastercard_foundation"
    base_url = BASE_URL
    delay = 2.0

    def scrape(self) -> List[NormalizedScholarship]:
        results = []
        seen = set()

        # --- Main scholars page ---
        main_soup = self.get_soup(SCHOLARS_URL)
        global_deadline = None
        main_desc = None
        if main_soup:
            full_text = main_soup.get_text(" ", strip=True)
            global_deadline = find_deadline_in_text(full_text)
            paras = main_soup.find_all("p")
            if paras:
                main_desc = " ".join(p.get_text(strip=True) for p in paras[:4])[:600]

        results.append(make_scholarship(
            title="Mastercard Foundation Scholars Program",
            source_url=SCHOLARS_URL,
            source_site=SITE_NAME,
            organization="Mastercard Foundation",
            description=main_desc,
            degree_levels_raw="undergraduate masters",
            deadline_raw=global_deadline,
            amount="Fully Funded",
            eligible_nationalities=["African"],
            tags=["Mastercard Foundation", "Africa", "scholars", "fully funded"],
        ))
        seen.add(SCHOLARS_URL)

        # Partner institutions load dynamically via JS; fall back to known list
        for partner_url, partner_name, degree_raw in KNOWN_PARTNERS:
            if partner_url in seen:
                continue
            seen.add(partner_url)

            detail = self.get_soup(partner_url)
            desc, dl = None, global_deadline
            if detail:
                text = detail.get_text(" ", strip=True)
                dl = find_deadline_in_text(text) or global_deadline
                ps = detail.find_all("p")
                if ps:
                    desc = " ".join(p.get_text(strip=True) for p in ps[:4])[:600]

            results.append(make_scholarship(
                title=f"Mastercard Foundation Scholars – {partner_name}",
                source_url=partner_url,
                source_site=SITE_NAME,
                organization="Mastercard Foundation",
                description=desc,
                degree_levels_raw=degree_raw,
                deadline_raw=dl,
                amount="Fully Funded",
                eligible_nationalities=["African"],
                tags=["Mastercard Foundation", "Africa", "scholars", "fully funded"],
            ))

            if len(results) >= self.max_pages * 3:
                break

        return results
