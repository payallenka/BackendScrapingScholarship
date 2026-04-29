"""
Ingest UK Licensed Sponsor Register from GOV.UK and store in jobs table.
Dynamically discovers the current CSV URL from the GOV.UK publications page.
"""
import csv
import logging
import requests
from bs4 import BeautifulSoup
from datetime import datetime
from io import StringIO

from scrapers.normalizer import NormalizedJob
from backend.database import upsert_jobs

logger = logging.getLogger(__name__)

GOV_UK_PAGE = "https://www.gov.uk/government/publications/register-of-licensed-sponsors-workers"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; EliteScholars/1.0)"}
MAX_ROWS = 10_000

USEFUL_ROUTES = {
    "Skilled Worker",
    "Global Business Mobility: Senior or Specialist Worker",
    "Global Business Mobility: Graduate Trainee",
    "Global Business Mobility: UK Expansion Worker",
    "Scale-up",
}


def _discover_csv_url() -> str | None:
    """Scrape the GOV.UK page to find the current CSV download URL."""
    try:
        resp = requests.get(GOV_UK_PAGE, headers=HEADERS, timeout=20)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "lxml")
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if "assets.publishing.service.gov.uk" in href and href.endswith(".csv"):
                return href
    except Exception as e:
        logger.error(f"Failed to discover UK sponsor CSV URL: {e}")
    return None


def fetch_uk_sponsor_jobs():
    csv_url = _discover_csv_url()
    if not csv_url:
        logger.warning("Could not find UK Sponsor Register CSV URL — skipping.")
        return []

    logger.info(f"Fetching UK Sponsor Register CSV from {csv_url}")
    try:
        resp = requests.get(csv_url, headers=HEADERS, timeout=60)
        resp.raise_for_status()
    except Exception as e:
        logger.error(f"Failed to fetch UK Sponsor Register CSV: {e}")
        return []

    csvfile = StringIO(resp.text)
    reader = csv.DictReader(csvfile)
    jobs = []
    now = datetime.utcnow().isoformat()
    seen_ids = set()

    for row in reader:
        if len(jobs) >= MAX_ROWS:
            break

        company_name = (row.get("Organisation Name") or "").strip()
        town = (row.get("Town/City") or "").strip()
        county = (row.get("County") or "").strip()
        type_rating = (row.get("Type & Rating") or "").strip()
        route = (row.get("Route") or "").strip()

        if not company_name:
            continue
        if route and route not in USEFUL_ROUTES:
            continue

        job_id = f"uk_sponsor_{company_name.lower().replace(' ', '_')[:60]}"
        if job_id in seen_ids:
            continue
        seen_ids.add(job_id)

        location_parts = [p for p in [town, county, "United Kingdom"] if p]
        location = ", ".join(location_parts)

        tags = [t for t in [route, type_rating] if t]
        description = (
            f"{company_name} is a UK-licensed visa sponsor"
            + (f" ({route})" if route else "")
            + f" located in {town or 'the UK'}."
            + " They are approved to sponsor skilled worker visas."
        )

        jobs.append(NormalizedJob(
            id=job_id,
            title="Visa-Sponsored Positions Available",
            company=company_name,
            location=location,
            contract_type="Full-time",
            salary_min=None,
            salary_max=None,
            currency=None,
            description=description,
            tags=tags,
            source="uk_sponsor_register",
            apply_url=f"https://www.google.com/search?q={requests.utils.quote(company_name + ' jobs visa sponsorship UK')}",
            posted_at=None,
            ingested_at=now,
            logo_url=None,
            extra_data=None,
        ))

    logger.info(f"UK Sponsor Register: parsed {len(jobs)} sponsors")
    return jobs


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    jobs = fetch_uk_sponsor_jobs()
    upsert_jobs(jobs)
    print(f"Ingested {len(jobs)} jobs from UK Sponsor Register.")
