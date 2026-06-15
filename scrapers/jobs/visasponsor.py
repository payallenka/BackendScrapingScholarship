"""
Ingest visa-sponsored job openings from visasponsor.jobs (US / UK / Canada).

The site's /api/jobs?country=<c> route is server-rendered HTML (not JSON), so we
parse the job cards. Every listing on this site is a visa-sponsorship role.
"""
import logging
import re
from datetime import datetime
from urllib.parse import urljoin

from scrapers.normalizer import NormalizedJob
from scrapers.jobs.http_util import polite_get
from backend.database import upsert_jobs

logger = logging.getLogger(__name__)

BASE_URL = "https://visasponsor.jobs"
COUNTRIES = ["United-States", "United-Kingdom", "Canada"]
MAX_PAGES = 15            # pages per country (~30 jobs/page)
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    ),
}
_JOB_HREF_RE = re.compile(r"^/api/jobs/([0-9a-f]+)/", re.I)
_DATE_RE = re.compile(r"(\d{2})-(\d{2})-(\d{4})")


def _parse_card(a, now):
    href = a.get("href", "")
    m = _JOB_HREF_RE.match(href)
    if not m:
        return None
    job_id = m.group(1)

    title_el = a.select_one(".fs-5.fw-medium") or a.select_one(".fs-5")
    title = title_el.get_text(" ", strip=True) if title_el else ""
    if not title:
        return None

    company_el = a.select_one(".employer-name")
    company = company_el.get_text(" ", strip=True) if company_el else ""

    loc_el = a.select_one(".col-11")
    location = loc_el.get_text(" ", strip=True) if loc_el else ""
    location = re.sub(r"\s+", " ", location).strip().strip(",")

    tags = []
    for t in a.select(".tag, .job-classification .sub-font"):
        tt = t.get_text(" ", strip=True)
        if tt and tt not in tags:
            tags.append(tt)

    posted_at = None
    date_el = a.select_one(".mt-auto")
    if date_el:
        dm = _DATE_RE.search(date_el.get_text(" ", strip=True))
        if dm:
            posted_at = f"{dm.group(3)}-{dm.group(2)}-{dm.group(1)}"  # dd-mm-yyyy -> ISO

    return NormalizedJob(
        id=f"visasponsor_{job_id}",
        title=title,
        company=company or None,
        location=location or None,
        contract_type=None,
        salary_min=None,
        salary_max=None,
        currency=None,
        description=None,
        tags=tags,
        source="visasponsor",
        apply_url=urljoin(BASE_URL, href),
        posted_at=posted_at,
        ingested_at=now,
        logo_url=None,
        visa_sponsored=True,   # the entire site is visa-sponsorship jobs
        extra_data=None,
    )


def fetch_visasponsor_jobs():
    from bs4 import BeautifulSoup
    jobs = []
    now = datetime.utcnow().isoformat()

    for country in COUNTRIES:
        for page in range(1, MAX_PAGES + 1):
            url = f"{BASE_URL}/api/jobs?country={country}&page={page}"
            try:
                resp = polite_get(url)
                resp.raise_for_status()
            except Exception as e:
                logger.error(f"visasponsor [{country}] page {page} failed: {e}")
                break

            soup = BeautifulSoup(resp.text, "lxml")
            cards = soup.select('a[href^="/api/jobs/"]')
            cards = [c for c in cards if _JOB_HREF_RE.match(c.get("href", ""))]
            if not cards:
                break

            for a in cards:
                job = _parse_card(a, now)
                if job:
                    jobs.append(job)

            if len(cards) < 30:   # last page
                break

    logger.info(f"visasponsor: fetched {len(jobs)} jobs")
    return jobs


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    jobs = fetch_visasponsor_jobs()
    upsert_jobs(jobs)
    print(f"Ingested {len(jobs)} jobs from visasponsor.jobs.")
