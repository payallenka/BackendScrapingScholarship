import json
import logging
import os

from dotenv import load_dotenv
from supabase import create_client, Client

load_dotenv()
logger = logging.getLogger(__name__)


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
    # Collapse the same role posted across many cities into one listing — sources
    # like RemoteOK/Adzuna repeat a job per location, which floods the feed with
    # identical cards. Keep the first occurrence of each (company, title).
    deduped, seen = [], set()
    for j in jobs:
        key = ((j.company or "").strip().lower(), (j.title or "").strip().lower())
        if key in seen:
            continue
        seen.add(key)
        deduped.append(j)
    jobs = deduped

    sb = get_supabase()
    source = jobs[0].source
    # Baseline before this run, to detect a silently-degraded scrape (rate limit
    # / IP block / layout change) where success quietly drops without an error.
    prev_count = sb.table("jobs").select("id", count="exact", head=True).eq("source", source).execute().count or 0

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
            "visa_sponsored": bool(getattr(j, "visa_sponsored", False)),
            "extra_data": json.dumps(j.extra_data) if j.extra_data else None,
        }
        for j in jobs
    ]
    sb.table("jobs").upsert(rows, on_conflict="id").execute()

    # Remove stale jobs from this source not in the latest scrape batch. Each
    # scraper stamps every job in a run with the same ingested_at, and the upsert
    # above refreshes that timestamp on every current row — so anything left with
    # a different ingested_at is stale. Keying off the timestamp avoids putting
    # thousands of ids in the request URL.
    #
    # Degradation guard: if this run returned far fewer jobs than the source had
    # before (a quiet rate-limit/IP-block/layout break), DON'T purge — that would
    # silently delete good data. Log a warning instead so the drop is visible.
    batch_ts = jobs[0].ingested_at
    if prev_count >= 10 and len(rows) < prev_count * 0.5:
        logger.warning(
            "[%s] scraped %d jobs vs %d previously (<50%%) — skipping stale purge "
            "to avoid deleting good data (possible block/rate-limit/site change)",
            source, len(rows), prev_count,
        )
    else:
        sb.table("jobs").delete().eq("source", source).neq("ingested_at", batch_ts).execute()
