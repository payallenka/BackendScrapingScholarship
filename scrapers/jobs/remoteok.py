"""
Ingest jobs from RemoteOK public API and store in jobs table.
"""
import requests
from datetime import datetime
from scrapers.normalizer import NormalizedJob
from backend.database import get_conn, upsert_jobs, init_jobs_table

REMOTEOK_API_URL = "https://remoteok.com/api"

def fetch_remoteok_jobs():
    resp = requests.get(REMOTEOK_API_URL)
    data = resp.json()
    jobs = []
    now = datetime.utcnow().isoformat()
    for item in data:
        # RemoteOK returns metadata as the first item
        if not isinstance(item, dict) or not item.get("id") or not item.get("position"):
            continue
        tags = item.get("tags") or []
        salary_min = item.get("salary_min")
        salary_max = item.get("salary_max")
        jobs.append(NormalizedJob(
            id=str(item["id"]),
            title=item["position"],
            company=item.get("company"),
            location=item.get("location") or "Remote",
            contract_type=", ".join(tags) if tags else None,
            salary_min=float(salary_min) if salary_min else None,
            salary_max=float(salary_max) if salary_max else None,
            currency="USD",
            description=item.get("description"),
            tags=tags,
            source="remoteok",
            apply_url=item.get("url"),
            posted_at=item.get("date"),
            ingested_at=now,
            logo_url=item.get("logo"),
            extra_data=None,
        ))
    return jobs

if __name__ == "__main__":
    conn = get_conn()
    init_jobs_table(conn)
    jobs = fetch_remoteok_jobs()
    upsert_jobs(conn, jobs)
    print(f"Ingested {len(jobs)} jobs from RemoteOK.")
    conn.close()
