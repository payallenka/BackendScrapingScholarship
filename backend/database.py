import json
import os

from dotenv import load_dotenv
from supabase import create_client, Client

load_dotenv()


def get_supabase() -> Client:
    return create_client(
        os.environ["SUPABASE_URL"],
        os.environ["SUPABASE_SERVICE_ROLE_KEY"],
    )


def row_to_dict(row: dict) -> dict:
    for field in ("degree_levels", "fields_of_study", "eligible_nationalities", "host_countries", "tags"):
        val = row.get(field)
        if val:
            try:
                row[field] = json.loads(val) if isinstance(val, str) else val
            except Exception:
                row[field] = []
        else:
            row[field] = []
    if row.get("is_open") is not None:
        row["is_open"] = bool(row["is_open"])
    row.setdefault("funding_type", None)
    return row


def upsert_jobs(jobs):
    if not jobs:
        return
    sb = get_supabase()
    rows = [
        {
            "id": j.id,
            "title": j.title,
            "company": j.company,
            "location": j.location,
            "contract_type": j.contract_type,
            "salary_min": j.salary_min,
            "salary_max": j.salary_max,
            "currency": j.currency,
            "description": j.description,
            "tags": json.dumps(j.tags),
            "source": j.source,
            "apply_url": j.apply_url,
            "posted_at": j.posted_at,
            "ingested_at": j.ingested_at,
            "expires_at": getattr(j, "expires_at", None),
            "logo_url": j.logo_url,
            "extra_data": json.dumps(j.extra_data) if j.extra_data else None,
        }
        for j in jobs
    ]
    sb.table("jobs").upsert(rows, on_conflict="id").execute()

    # Remove stale jobs from this source not in the latest scrape batch
    source = jobs[0].source
    ids = [j.id for j in jobs]
    sb.table("jobs").delete().eq("source", source).not_.in_("id", ids).execute()
