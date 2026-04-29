"""
Ingest visa-sponsored jobs from Arbeitnow (free public API, no auth required).
"""
import logging
import requests
from datetime import datetime

from scrapers.normalizer import NormalizedJob
from backend.database import upsert_jobs

logger = logging.getLogger(__name__)

API_URL = "https://www.arbeitnow.com/api/job-board-api"
MAX_PAGES = 5


def fetch_arbeitnow_jobs():
    jobs = []
    now = datetime.utcnow().isoformat()

    for page in range(1, MAX_PAGES + 1):
        try:
            resp = requests.get(
                API_URL,
                params={"visa_sponsorship": "true", "page": page},
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            logger.error(f"Arbeitnow page {page} failed: {e}")
            break

        items = data.get("data", [])
        if not items:
            break

        for item in items:
            slug = item.get("slug") or ""
            title = item.get("title") or ""
            company = item.get("company_name") or ""
            location = item.get("location") or "Remote"
            description = item.get("description") or ""
            tags = item.get("tags") or []
            job_types = item.get("job_types") or []
            apply_url = item.get("url") or ""
            logo_url = item.get("company_logo_url") or item.get("company_logo") or None
            created_at = item.get("created_at")

            posted_at = None
            if created_at:
                try:
                    posted_at = datetime.utcfromtimestamp(int(created_at)).isoformat()
                except Exception:
                    posted_at = None

            contract_type = ", ".join(job_types) if job_types else None

            jobs.append(NormalizedJob(
                id=f"arbeitnow_{slug}",
                title=title,
                company=company,
                location=location,
                contract_type=contract_type,
                salary_min=None,
                salary_max=None,
                currency=None,
                description=description,
                tags=tags,
                source="arbeitnow",
                apply_url=apply_url,
                posted_at=posted_at,
                ingested_at=now,
                logo_url=logo_url,
                extra_data=None,
            ))

        if not data.get("links", {}).get("next"):
            break

    logger.info(f"Arbeitnow: fetched {len(jobs)} visa-sponsored jobs")
    return jobs


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    jobs = fetch_arbeitnow_jobs()
    upsert_jobs(jobs)
    print(f"Ingested {len(jobs)} jobs from Arbeitnow.")
