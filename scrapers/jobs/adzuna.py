"""
Ingest UK visa-sponsoring job openings from the Adzuna API (free public API).

Unlike the UK Sponsor Register (a directory of licensed *employers*), these are
real vacancies with apply links. We query Adzuna UK for visa-sponsorship roles
and flag each job's visa status from its own text.

Adzuna's UK feed includes some overseas roles posted by UK recruiters
("...Opportunities in Australia", "Registered Nurse - Melbourne", "Jobs in
Canada"). These are tagged UK by Adzuna but clearly belong to another country,
so we drop any whose title/location names a non-UK country or distinctive
foreign city.
"""
import logging
import os
import re
import requests
from datetime import datetime

from scrapers.normalizer import NormalizedJob, detect_visa_sponsorship
from scrapers.jobs.http_util import polite_get
from backend.database import upsert_jobs

logger = logging.getLogger(__name__)

API_URL = "https://api.adzuna.com/v1/api/jobs/gb/search"
APP_ID = os.getenv("ADZUNA_APP_ID")
APP_KEY = os.getenv("ADZUNA_APP_KEY")
MAX_PAGES = 5
RESULTS_PER_PAGE = 50
QUERY = "visa sponsorship"

# Non-UK signals. Only unambiguous country names and distinctive foreign cities
# are listed — deliberately excluding names shared with UK places (Perth/Scotland,
# Victoria/London, London/Ontario) to avoid dropping genuine UK jobs.
_NON_UK_RE = re.compile(
    r"\b(?:australia|australian|canada|canadian|india|indian|new\s+zealand|"
    r"u\.?s\.?a|united\s+states|america|uae|dubai|abu\s+dhabi|qatar|doha|"
    r"saudi|riyadh|jeddah|singapore|nigeria|kenya|south\s+africa|malaysia|"
    r"hong\s+kong|china|japan|philippines|pakistan|oman|bahrain|kuwait|"
    r"melbourne|sydney|brisbane|adelaide|tasmania|canberra|"
    r"toronto|vancouver|mumbai|bengaluru|bangalore|hyderabad|chennai|"
    r"auckland|wellington)\b",
    re.I,
)


def fetch_adzuna_jobs():
    if not (APP_ID and APP_KEY):
        logger.warning("Adzuna: ADZUNA_APP_ID / ADZUNA_APP_KEY not set — skipping")
        return []

    jobs = []
    dropped = 0
    now = datetime.utcnow().isoformat()

    for page in range(1, MAX_PAGES + 1):
        try:
            resp = polite_get(
                f"{API_URL}/{page}",
                params={
                    "app_id": APP_ID,
                    "app_key": APP_KEY,
                    "results_per_page": RESULTS_PER_PAGE,
                    "what": QUERY,
                    "content-type": "application/json",
                },
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            logger.error(f"Adzuna page {page} failed: {e}")
            break

        items = data.get("results", [])
        if not items:
            break

        for item in items:
            job_id = item.get("id")
            if not job_id:
                continue

            title = re.sub(r"<[^>]+>", "", item.get("title") or "").strip()
            company = (item.get("company") or {}).get("display_name") or ""
            location = (item.get("location") or {}).get("display_name") or "United Kingdom"

            # Drop overseas roles that leak into the UK feed.
            if _NON_UK_RE.search(f"{title} {location}"):
                dropped += 1
                continue

            description = item.get("description") or ""
            apply_url = item.get("redirect_url") or ""
            salary_min = item.get("salary_min")
            salary_max = item.get("salary_max")
            category = (item.get("category") or {}).get("label")

            ctype = ", ".join(
                t.replace("_", " ") for t in (item.get("contract_type"), item.get("contract_time")) if t
            ) or None

            tags = [t for t in [category] if t]

            visa = detect_visa_sponsorship(
                title=title, description=description, tags=tags, source="adzuna"
            )

            jobs.append(NormalizedJob(
                id=f"adzuna_{job_id}",
                title=title,
                company=company,
                location=location,
                contract_type=ctype,
                salary_min=salary_min,
                salary_max=salary_max,
                currency="GBP" if (salary_min or salary_max) else None,
                description=description,
                tags=tags,
                source="adzuna",
                apply_url=apply_url,
                posted_at=item.get("created") or None,
                ingested_at=now,
                logo_url=None,
                visa_sponsored=visa,
                extra_data=None,
            ))

        if len(items) < RESULTS_PER_PAGE:
            break

    logger.info(f"Adzuna: fetched {len(jobs)} UK jobs ({dropped} overseas roles dropped)")
    return jobs


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    jobs = fetch_adzuna_jobs()
    upsert_jobs(jobs)
    print(f"Ingested {len(jobs)} jobs from Adzuna.")
