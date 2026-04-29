"""
Ingest jobs from NHS Jobs (public HTML, no auth required).
"""
import logging
import re
import requests
from bs4 import BeautifulSoup
from datetime import datetime

from scrapers.normalizer import NormalizedJob
from backend.database import get_conn, upsert_jobs, init_jobs_table

logger = logging.getLogger(__name__)

BASE_URL = "https://www.jobs.nhs.uk/candidate/search/results"
JOB_BASE = "https://www.jobs.nhs.uk"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
MAX_PAGES = 20   # 200 jobs max (10 per page)


def _parse_salary(text):
    """Extract min/max from strings like '£31,500 to £41,000 a year'."""
    if not text:
        return None, None, None
    cleaned = text.replace(",", "").replace("£", "").replace("$", "")
    numbers = re.findall(r"\d+(?:\.\d+)?", cleaned)
    vals = [float(n) for n in numbers if float(n) > 100]
    if not vals:
        return None, None, None
    is_hourly = "hour" in text.lower()
    mult = 2080 if is_hourly else 1
    low = round(vals[0] * mult) if len(vals) >= 1 else None
    high = round(vals[1] * mult) if len(vals) >= 2 else None
    return low, high, "GBP"


def fetch_nhs_jobs():
    jobs = []
    now = datetime.utcnow().isoformat()
    seen_ids = set()

    for page in range(1, MAX_PAGES + 1):
        try:
            resp = requests.get(
                BASE_URL,
                params={"language": "en", "page": page},
                headers=HEADERS,
                timeout=15,
            )
            resp.raise_for_status()
        except Exception as e:
            logger.error(f"NHS Jobs page {page} failed: {e}")
            break

        soup = BeautifulSoup(resp.text, "lxml")
        items = soup.select('[data-test="search-result"]')
        if not items:
            break

        for item in items:
            title_el    = item.select_one('[data-test="search-result-job-title"]')
            org_el      = item.select_one("h3.nhsuk-u-font-weight-bold")
            location_el = item.select_one(".location-font-size")
            salary_el   = item.select_one('[data-test="search-result-salary"] strong')
            date_el     = item.select_one('[data-test="search-result-publicationDate"] strong')
            closing_el  = item.select_one('[data-test="search-result-closingDate"] strong')

            title = title_el.get_text(strip=True) if title_el else "NHS Position"
            href  = title_el["href"] if title_el and title_el.has_attr("href") else ""

            # Company is the first text node of h3; location is in the nested div
            company  = None
            location = None
            if org_el:
                loc_div = org_el.select_one(".location-font-size")
                if loc_div:
                    location = loc_div.get_text(strip=True)
                    loc_div.decompose()
                company = org_el.get_text(strip=True)

            # Derive job_id from href  (e.g. /candidate/jobadvert/B0214-25-0023)
            job_id = href.split("/")[-1].split("?")[0] if href else None
            if not job_id or job_id in seen_ids:
                continue
            seen_ids.add(job_id)

            salary_text = salary_el.get_text(strip=True) if salary_el else ""
            salary_min, salary_max, currency = _parse_salary(salary_text)

            apply_url = JOB_BASE + href if href else JOB_BASE

            posted_at = None
            if date_el:
                try:
                    posted_at = datetime.strptime(date_el.get_text(strip=True), "%d %B %Y").isoformat()
                except Exception:
                    pass

            expires_at = None
            if closing_el:
                try:
                    expires_at = datetime.strptime(closing_el.get_text(strip=True), "%d %B %Y").strftime("%Y-%m-%d")
                except Exception:
                    pass

            jobs.append(NormalizedJob(
                id=f"nhs_{job_id}",
                title=title,
                company=company,
                location=location or "United Kingdom",
                contract_type="Full-time",
                salary_min=salary_min,
                salary_max=salary_max,
                currency=currency,
                description=f"{title} role at {company or 'NHS'}. Open to international candidates with valid UK work authorisation.",
                tags=["NHS", "United Kingdom", "Healthcare"],
                source="nhs_jobs",
                apply_url=apply_url,
                posted_at=posted_at,
                ingested_at=now,
                expires_at=expires_at,
                logo_url=None,
                extra_data=None,
            ))

        logger.info(f"NHS Jobs page {page}: {len(items)} items")
        if len(items) < 10:
            break

    logger.info(f"NHS Jobs: fetched {len(jobs)} jobs total")
    return jobs


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    conn = get_conn()
    init_jobs_table(conn)
    jobs = fetch_nhs_jobs()
    upsert_jobs(conn, jobs)
    print(f"Ingested {len(jobs)} jobs from NHS Jobs.")
    conn.close()
