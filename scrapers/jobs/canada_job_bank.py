"""
Ingest jobs from Canada Job Bank (public HTML, no auth required).
Uses session-based pagination via the job_search_loader.xhtml endpoint.
"""
import logging
import re
import requests
from bs4 import BeautifulSoup
from datetime import datetime

from scrapers.normalizer import NormalizedJob
from backend.database import get_conn, upsert_jobs, init_jobs_table

logger = logging.getLogger(__name__)

SEARCH_URL  = "https://www.jobbank.gc.ca/jobsearch/jobsearch"
LOADER_URL  = "https://www.jobbank.gc.ca/jobsearch/job_search_loader.xhtml"
JOB_BASE    = "https://www.jobbank.gc.ca"
HEADERS     = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
MAX_PAGES   = 8   # 25 jobs/page → 200 jobs max


def _parse_salary(text):
    if not text:
        return None, None, None
    numbers = re.findall(r"[\d,]+(?:\.\d+)?", text.replace(",", ""))
    vals = [float(n) for n in numbers if n]
    if not vals:
        return None, None, None
    is_hourly = "hour" in text.lower()
    mult = 2080 if is_hourly else 1
    low  = round(vals[0] * mult) if len(vals) >= 1 else None
    high = round(vals[1] * mult) if len(vals) >= 2 else None
    return low, high, "CAD"


def _parse_articles(soup, now, seen_ids):
    jobs = []
    for article in soup.find_all("article", class_="action-buttons"):
        job_id = article.get("id", "").replace("article-", "").strip()
        if not job_id or job_id in seen_ids:
            continue
        seen_ids.add(job_id)

        title_el    = article.select_one(".noctitle")
        company_el  = article.select_one(".business")
        location_el = article.select_one(".location")
        date_el     = article.select_one(".date")
        salary_el   = article.select_one(".salary")
        link_el     = article.select_one("a.resultJobItem")

        title    = title_el.get_text(strip=True)    if title_el    else "Job Opening"
        company  = company_el.get_text(strip=True)  if company_el  else None
        location = re.sub(r"^Location\s*", "", location_el.get_text(strip=True)).strip() if location_el else "Canada"

        salary_text = salary_el.get_text(strip=True) if salary_el else ""
        salary_min, salary_max, currency = _parse_salary(salary_text)

        href      = link_el["href"].split(";")[0] if link_el else ""
        apply_url = JOB_BASE + href if href else JOB_BASE

        posted_at = None
        if date_el:
            try:
                posted_at = datetime.strptime(date_el.get_text(strip=True), "%B %d, %Y").isoformat()
            except Exception:
                pass

        jobs.append(NormalizedJob(
            id=f"canada_{job_id}",
            title=title,
            company=company,
            location=location or "Canada",
            contract_type="Full-time",
            salary_min=salary_min,
            salary_max=salary_max,
            currency=currency,
            description=f"{title} position at {company or 'a Canadian employer'}. Posted on Canada Job Bank.",
            tags=["Canada", "LMIA"],
            source="canada_job_bank",
            apply_url=apply_url,
            posted_at=posted_at,
            ingested_at=now,
            logo_url=None,
            extra_data=None,
        ))
    return jobs


def fetch_canada_job_bank_jobs():
    now = datetime.utcnow().isoformat()
    seen_ids = set()
    jobs = []

    session = requests.Session()
    session.headers.update(HEADERS)

    # Initial search — establishes the session & first 25 results (not used, loader gives page 1)
    try:
        session.get(
            SEARCH_URL,
            params={"searchstring": "", "locationstring": "", "sort": "D",
                    "action": "search", "flg": "E", "source": "7"},
            timeout=15,
        )
    except Exception as e:
        logger.error(f"Canada Job Bank initial request failed: {e}")
        return []

    for page in range(MAX_PAGES):
        try:
            resp = session.get(LOADER_URL, timeout=15)
            resp.raise_for_status()
        except Exception as e:
            logger.error(f"Canada Job Bank page {page + 1} failed: {e}")
            break

        soup     = BeautifulSoup(resp.text, "lxml")
        new_jobs = _parse_articles(soup, now, seen_ids)
        jobs.extend(new_jobs)
        logger.info(f"Canada Job Bank page {page + 1}: {len(new_jobs)} new jobs (total {len(jobs)})")

        if not new_jobs:
            break

    logger.info(f"Canada Job Bank: fetched {len(jobs)} jobs total")
    return jobs


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    conn = get_conn()
    init_jobs_table(conn)
    jobs = fetch_canada_job_bank_jobs()
    upsert_jobs(conn, jobs)
    print(f"Ingested {len(jobs)} jobs from Canada Job Bank.")
    conn.close()
