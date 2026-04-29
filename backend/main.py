"""
FastAPI backend for the scholarship aggregator.

Endpoints:
  GET  /api/scholarships       — list with filters + pagination
  GET  /api/scholarships/{id}  — single scholarship
  GET  /api/stats              — aggregate stats
  GET  /api/sites              — list of source sites
  POST /api/scrape             — trigger background scrape
  GET  /api/scrape/status      — scrape job status
"""
from __future__ import annotations
import json
import logging
import os
import re
from datetime import date, datetime
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Query, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from backend.database import get_supabase, row_to_dict

logger = logging.getLogger(__name__)

app = FastAPI(title="Scholarship Aggregator API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

FRONTEND_DIR = Path(__file__).parent.parent / "frontend"
if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")

# ---------------------------------------------------------------------------
# Scrape state (in-memory)
# ---------------------------------------------------------------------------
_scrape_state = {"running": False, "started_at": None, "finished_at": None, "count": 0, "error": None, "sources": {}}
_job_scrape_state = {"running": False, "started_at": None, "finished_at": None, "count": 0, "error": None, "sources": {}}

# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

from scrapers.jobs.run_all_jobs import run_all_jobs
from scrapers.jobs.direct_links import DIRECT_LINK_SOURCES

# Country inference helpers for /api/jobs/suggest
_SOURCE_COUNTRY = {
    "canada_job_bank":     "canada",
    "nhs_jobs":            "united kingdom",
    "uk_sponsor_register": "united kingdom",
}
_CA_PROVINCE_RE = re.compile(
    r'\b(?:on|qc|bc|ab|mb|sk|ns|nb|pe|nl|nt|yt|nu)\b', re.IGNORECASE
)

def _job_countries(location: str, source: str) -> set:
    """Return a set of inferred country names (lowercase) for a job."""
    loc = location.lower()
    out = set()
    if "canada" in loc or _CA_PROVINCE_RE.search(loc):
        out.add("canada")
    if any(x in loc for x in ("united kingdom", "england", "scotland", "wales", "northern ireland")):
        out.add("united kingdom")
    if "germany" in loc or "deutschland" in loc:
        out.add("germany")
    if "australia" in loc:
        out.add("australia")
    if "remote" in loc:
        out.add("remote")
    src_country = _SOURCE_COUNTRY.get(source, "")
    if src_country:
        out.add(src_country)
    return out


# --- Job scrape triggers ---

@app.post("/api/jobs/scrape")
def trigger_jobs_scrape(background_tasks: BackgroundTasks):
    if _job_scrape_state["running"]:
        return {"status": "already_running", "started_at": _job_scrape_state["started_at"]}
    background_tasks.add_task(_run_jobs_scrape)
    return {"status": "started"}


@app.get("/api/jobs/scrape/status")
def jobs_scrape_status():
    return _job_scrape_state


def _run_jobs_scrape():
    global _job_scrape_state
    _job_scrape_state = {"running": True, "started_at": datetime.utcnow().isoformat(), "finished_at": None, "count": 0, "error": None, "sources": {}}

    def _on_source(name, count, total):
        _job_scrape_state["count"] = total
        _job_scrape_state["sources"][name] = count

    try:
        total = run_all_jobs(on_source_done=_on_source)
        _job_scrape_state.update({"running": False, "finished_at": datetime.utcnow().isoformat(), "count": total})
    except Exception as e:
        _job_scrape_state.update({"running": False, "finished_at": datetime.utcnow().isoformat(), "error": str(e)})


# --- Job listing ---

_EXPERIENCE_KEYWORDS = {
    "entry":   ["junior", "entry level", "graduate", "trainee", "intern", "assistant"],
    "mid":     ["mid-level", "intermediate", "associate", "experienced"],
    "senior":  ["senior", "sr.", "lead", "principal", "staff", "expert"],
    "manager": ["manager", "director", "head of", "chief", "vp ", "vice president"],
}


@app.get("/api/jobs")
def list_jobs(
    search: Optional[str] = Query(None),
    company: Optional[str] = Query(None),
    location: Optional[str] = Query(None),
    contract_type: Optional[str] = Query(None),
    source: Optional[str] = Query(None),
    category: Optional[str] = Query(None, description="Free-text category searched across title, description and tags"),
    experience: Optional[str] = Query(None, description="entry|mid|senior|manager"),
    posted_hours: Optional[int] = Query(None, description="Only jobs posted in the last N hours (e.g. 24)"),
    sort: str = Query("posted_at", description="posted_at|ingested_at|salary_min|salary_max"),
    order: str = Query("desc"),
    limit: int = Query(24, le=100),
    offset: int = Query(0),
):
    sb = get_supabase()
    sort_col = sort if sort in ("posted_at", "ingested_at", "salary_min", "salary_max") else "posted_at"
    desc = order.lower() == "desc"
    today = date.today().isoformat()

    query = sb.table("jobs").select("*", count="exact")
    query = query.or_(f"expires_at.is.null,expires_at.gte.{today}")

    if search:
        term = search.replace("*", "").replace("%", "")
        query = query.or_(f"title.ilike.*{term}*,description.ilike.*{term}*,company.ilike.*{term}*")
    if company:
        query = query.ilike("company", company)
    if location:
        query = query.ilike("location", f"%{location}%")
    if contract_type:
        query = query.ilike("contract_type", f"%{contract_type}%")
    if source:
        query = query.ilike("source", source)
    if posted_hours:
        from datetime import timedelta
        cutoff = (datetime.utcnow() - timedelta(hours=posted_hours)).isoformat()
        query = query.gte("posted_at", cutoff)
    if category:
        # Free-text: search broadly across title, description and tags
        term = category.replace("*", "").replace("%", "")
        query = query.or_(f"title.ilike.*{term}*,description.ilike.*{term}*,tags.ilike.*{term}*")
    if experience and experience in _EXPERIENCE_KEYWORDS:
        kws = _EXPERIENCE_KEYWORDS[experience]
        # Search both title and description for level keywords
        conditions = [f"title.ilike.*{kw}*,description.ilike.*{kw}*" for kw in kws]
        query = query.or_(",".join(conditions))

    query = query.order(sort_col, desc=desc, nullsfirst=False)
    query = query.range(offset, offset + limit - 1)

    response = query.execute()
    return {
        "total": response.count or 0,
        "limit": limit,
        "offset": offset,
        "items": response.data,
    }


@app.get("/api/jobs/direct-links")
def get_direct_link_jobs():
    return {"direct_links": DIRECT_LINK_SOURCES}


@app.get("/api/jobs/sources/status")
def jobs_sources_status():
    try:
        sb = get_supabase()
        response = sb.table("jobs").select("source,ingested_at").execute()
        counts: dict = {}
        latest: dict = {}
        for r in response.data:
            s = r["source"]
            counts[s] = counts.get(s, 0) + 1
            if not latest.get(s) or (r["ingested_at"] or "") > latest[s]:
                latest[s] = r["ingested_at"]
        return [{"source": s, "count": c, "last_ingested": latest.get(s)} for s, c in counts.items()]
    except Exception:
        return []


@app.get("/api/jobs/suggest")
def suggest_jobs(
    field: Optional[str] = Query(None),
    countries: Optional[str] = Query(None, description="Comma-separated list of target countries"),
    limit: int = Query(6, le=20),
):
    try:
        sb = get_supabase()
        response = (
            sb.table("jobs")
            .select("*")
            .order("posted_at", desc=True, nullsfirst=False)
            .limit(300)
            .execute()
        )
        rows = response.data
    except Exception:
        return {"suggestions": []}

    field_keywords = [w.lower() for w in (field or "").split() if len(w) > 2]
    country_list = [c.strip().lower() for c in (countries or "").split(",") if c.strip()]

    # No criteria → return most recent jobs
    if not field_keywords and not country_list:
        return {"suggestions": rows[:limit]}

    scored = []
    for job in rows:
        try:
            tags = json.loads(job.get("tags") or "[]")
        except Exception:
            tags = []
        tags_text = " ".join(str(t).lower() for t in tags)
        combined = " ".join(filter(None, [
            job.get("title", ""),
            job.get("description", "") or "",
            job.get("contract_type", "") or "",
            tags_text,
        ])).lower()
        location = (job.get("location") or "").lower()
        source = (job.get("source") or "").lower()
        job_ctries = _job_countries(location, source)

        score = 0
        for kw in field_keywords:
            if kw in combined:
                score += 2
        for country in country_list:
            if country in job_ctries:
                score += 3

        if score > 0:
            scored.append((score, job))

    scored.sort(key=lambda x: x[0], reverse=True)
    return {"suggestions": [j for _, j in scored[:limit]]}


# --- Static frontend ---

@app.get("/")
def index():
    html = FRONTEND_DIR / "index.html"
    if html.exists():
        return FileResponse(str(html))
    return {"message": "Scholarship Aggregator API — visit /docs"}


# --- Scholarship listing ---

@app.get("/api/scholarships")
def list_scholarships(
    search: Optional[str] = Query(None),
    degree_level: Optional[str] = Query(None, description="undergraduate|masters|phd|postgraduate|any"),
    source_site: Optional[str] = Query(None),
    eligible_nationality: Optional[str] = Query(None),
    host_country: Optional[str] = Query(None),
    deadline_before: Optional[str] = Query(None, description="YYYY-MM-DD"),
    deadline_after: Optional[str] = Query(None, description="YYYY-MM-DD"),
    has_amount: bool = Query(False),
    sort: str = Query("scraped_at", description="scraped_at|deadline|title"),
    order: str = Query("desc"),
    limit: int = Query(24, le=100),
    offset: int = Query(0),
):
    sb = get_supabase()
    sort_col = sort if sort in ("scraped_at", "deadline", "title", "amount_usd") else "scraped_at"
    desc = order.lower() == "desc"

    query = sb.table("scholarships").select("*", count="exact")

    if search:
        term = search.replace("*", "").replace("%", "")
        query = query.or_(f"title.ilike.*{term}*,description.ilike.*{term}*,organization.ilike.*{term}*")
    if degree_level:
        query = query.ilike("degree_levels", f'%"{degree_level}"%')
    if source_site:
        query = query.ilike("source_site", source_site)
    if eligible_nationality:
        query = query.ilike("eligible_nationalities", f"%{eligible_nationality}%")
    if host_country:
        query = query.ilike("host_countries", f"%{host_country}%")
    if deadline_before:
        query = query.lte("deadline", deadline_before)
    if deadline_after:
        query = query.or_(f"deadline.gte.{deadline_after},deadline.is.null")
    if has_amount:
        query = query.not_.is_("amount", "null").neq("amount", "")

    query = query.order(sort_col, desc=desc, nullsfirst=False)
    query = query.range(offset, offset + limit - 1)

    response = query.execute()
    return {
        "total": response.count or 0,
        "limit": limit,
        "offset": offset,
        "items": [row_to_dict(r) for r in response.data],
    }


@app.get("/api/scholarships/{scholarship_id}")
def get_scholarship(scholarship_id: str):
    sb = get_supabase()
    response = sb.table("scholarships").select("*").eq("id", scholarship_id).execute()
    if not response.data:
        raise HTTPException(status_code=404, detail="Not found")
    return row_to_dict(response.data[0])


@app.get("/api/stats")
def get_stats():
    sb = get_supabase()

    total_resp = sb.table("scholarships").select("*", count="exact").execute()
    total = total_resp.count or 0

    site_resp = sb.table("scholarships").select("source_site").execute()
    site_counts: dict = {}
    for r in site_resp.data:
        s = r["source_site"]
        site_counts[s] = site_counts.get(s, 0) + 1
    by_site = sorted(
        [{"site": s, "count": c} for s, c in site_counts.items()],
        key=lambda x: -x["count"],
    )

    degree_resp = sb.table("scholarships").select("degree_levels").execute()
    degree_counts: dict = {}
    for r in degree_resp.data:
        d = r.get("degree_levels")
        if d:
            degree_counts[d] = degree_counts.get(d, 0) + 1
    by_degree = sorted(
        [{"degree": d, "count": c} for d, c in degree_counts.items()],
        key=lambda x: -x["count"],
    )[:10]

    deadline_resp = sb.table("scholarships").select("*", count="exact").not_.is_("deadline", "null").execute()
    with_deadline = deadline_resp.count or 0

    amount_resp = (
        sb.table("scholarships")
        .select("*", count="exact")
        .not_.is_("amount", "null")
        .neq("amount", "")
        .execute()
    )
    with_amount = amount_resp.count or 0

    latest_resp = (
        sb.table("scholarships")
        .select("scraped_at")
        .order("scraped_at", desc=True)
        .limit(1)
        .execute()
    )
    last_scraped = latest_resp.data[0]["scraped_at"] if latest_resp.data else None

    return {
        "total": total,
        "with_deadline": with_deadline,
        "with_amount": with_amount,
        "last_scraped": last_scraped,
        "by_site": by_site,
        "by_degree": by_degree,
    }


@app.get("/api/sites")
def get_sites():
    sb = get_supabase()
    response = sb.table("scholarships").select("source_site").execute()
    counts: dict = {}
    for r in response.data:
        s = r["source_site"]
        counts[s] = counts.get(s, 0) + 1
    return [{"name": s, "count": c} for s, c in sorted(counts.items())]


@app.post("/api/match")
async def match_endpoint(profile: dict):
    from backend.matcher import match_scholarships, UserProfile
    try:
        p = UserProfile(**profile)
        result = await match_scholarships(p)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Match error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# --- Scholarship scrape triggers ---

@app.post("/api/scrape")
def trigger_scrape(background_tasks: BackgroundTasks, max_pages: int = Query(5), owl: bool = Query(False)):
    if _scrape_state["running"]:
        return {"status": "already_running", "started_at": _scrape_state["started_at"]}
    background_tasks.add_task(_run_scrape, max_pages=max_pages, owl=owl)
    return {"status": "started"}


@app.get("/api/scrape/status")
def scrape_status():
    return _scrape_state


def _run_scrape(max_pages: int = 5, owl: bool = False):
    global _scrape_state
    _scrape_state = {"running": True, "started_at": datetime.utcnow().isoformat(), "finished_at": None, "count": 0, "error": None, "sources": {}}

    def _on_source(name, count, total):
        _scrape_state["count"] = total
        _scrape_state["sources"][name] = count

    try:
        from scrapers.run_all import run_all_scrapers
        total = run_all_scrapers(max_pages=max_pages, on_source_done=_on_source)
        _scrape_state.update({"running": False, "finished_at": datetime.utcnow().isoformat(), "count": total})
    except Exception as e:
        _scrape_state.update({"running": False, "finished_at": datetime.utcnow().isoformat(), "error": str(e)})
