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
import asyncio
import json
import logging
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from fastapi import FastAPI, HTTPException, Query, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from backend.database import get_conn, row_to_dict, DB_PATH
from scrapers.run_all import init_db

logger = logging.getLogger(__name__)

# Initialize DB on import so endpoints always have a valid schema
_conn = get_conn()
init_db(_conn)
_conn.close()
del _conn

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
# Scrape job state (in-memory, single worker)
# ---------------------------------------------------------------------------
_scrape_state = {"running": False, "started_at": None, "finished_at": None, "count": 0, "error": None}


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

# --- Job Scraping Endpoints ---
from scrapers.jobs.run_all_jobs import run_all_jobs

# Scrape job state (in-memory, single worker) for jobs
_job_scrape_state = {"running": False, "started_at": None, "finished_at": None, "count": 0, "error": None}

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
    _job_scrape_state = {"running": True, "started_at": datetime.utcnow().isoformat(), "finished_at": None, "count": 0, "error": None}
    try:
        run_all_jobs()
        _job_scrape_state.update({"running": False, "finished_at": datetime.utcnow().isoformat(), "count": 0})
    except Exception as e:
        _job_scrape_state.update({"running": False, "finished_at": datetime.utcnow().isoformat(), "error": str(e)})

# --- General Job Listing & Direct-Link Sources ---
from scrapers.jobs.direct_links import DIRECT_LINK_SOURCES

@app.get("/api/jobs")
def list_jobs(
    search: Optional[str] = Query(None),
    company: Optional[str] = Query(None),
    location: Optional[str] = Query(None),
    contract_type: Optional[str] = Query(None),
    source: Optional[str] = Query(None),
    sort: str = Query("posted_at", description="posted_at|ingested_at|salary_min|salary_max"),
    order: str = Query("desc"),
    limit: int = Query(24, le=100),
    offset: int = Query(0),
):
    conn = get_conn()
    conditions = ["(expires_at IS NULL OR expires_at >= date('now'))"]
    params = []
    if search:
        conditions.append("(LOWER(title) LIKE ? OR LOWER(description) LIKE ? OR LOWER(company) LIKE ?)")
        term = f"%{search.lower()}%"
        params += [term, term, term]
    if company:
        conditions.append("LOWER(company) = ?")
        params.append(company.lower())
    if location:
        conditions.append("LOWER(location) LIKE ?")
        params.append(f"%{location.lower()}%")
    if contract_type:
        conditions.append("LOWER(contract_type) LIKE ?")
        params.append(f"%{contract_type.lower()}%")
    if source:
        conditions.append("LOWER(source) = ?")
        params.append(source.lower())
    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    sort_col = sort if sort in ("posted_at", "ingested_at", "salary_min", "salary_max") else "posted_at"
    order_dir = "DESC" if order.lower() == "desc" else "ASC"
    order_clause = f"ORDER BY CASE WHEN {sort_col} IS NULL THEN 1 ELSE 0 END, {sort_col} {order_dir}"
    count_row = conn.execute(f"SELECT COUNT(*) as cnt FROM jobs {where}", params).fetchone()
    total = count_row["cnt"] if count_row else 0
    rows = conn.execute(
        f"SELECT * FROM jobs {where} {order_clause} LIMIT ? OFFSET ?",
        params + [limit, offset],
    ).fetchall()
    conn.close()
    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "items": [dict(r) for r in rows],
    }

@app.get("/api/jobs/direct-links")
def get_direct_link_jobs():
    return {"direct_links": DIRECT_LINK_SOURCES}


@app.get("/api/jobs/sources/status")
def jobs_sources_status():
    try:
        conn = get_conn()
        rows = conn.execute(
            "SELECT source, COUNT(*) as cnt, MAX(ingested_at) as last_ingested FROM jobs GROUP BY source"
        ).fetchall()
        conn.close()
        return [{"source": r["source"], "count": r["cnt"], "last_ingested": r["last_ingested"]} for r in rows]
    except Exception:
        return []


@app.get("/api/jobs/suggest")
def suggest_jobs(
    field: Optional[str] = Query(None),
    countries: Optional[str] = Query(None, description="Comma-separated list of target countries"),
    limit: int = Query(6, le=20),
):
    import json as _json

    try:
        conn = get_conn()
        rows = conn.execute(
            "SELECT * FROM jobs ORDER BY CASE WHEN posted_at IS NULL THEN 1 ELSE 0 END, posted_at DESC LIMIT 300"
        ).fetchall()
        conn.close()
    except Exception:
        return {"suggestions": []}

    field_keywords = [w.lower() for w in (field or "").split() if len(w) > 2]
    country_list = [c.strip().lower() for c in (countries or "").split(",") if c.strip()]

    scored = []
    for row in rows:
        job = dict(row)
        try:
            tags = _json.loads(job.get("tags") or "[]")
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

        score = 0
        for kw in field_keywords:
            if kw in combined:
                score += 2
        for country in country_list:
            if country in location:
                score += 3

        if score > 0:
            scored.append((score, job))

    scored.sort(key=lambda x: x[0], reverse=True)
    return {"suggestions": [j for _, j in scored[:limit]]}

@app.get("/")
def index():
    html = FRONTEND_DIR / "index.html"
    if html.exists():
        return FileResponse(str(html))
    return {"message": "Scholarship Aggregator API — visit /docs"}


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
    conn = get_conn()
    conditions = []
    params = []

    if search:
        conditions.append("(LOWER(title) LIKE ? OR LOWER(description) LIKE ? OR LOWER(organization) LIKE ?)")
        term = f"%{search.lower()}%"
        params += [term, term, term]

    if degree_level:
        conditions.append("degree_levels LIKE ?")
        params.append(f'%"{degree_level}"%')

    if source_site:
        conditions.append("LOWER(source_site) = ?")
        params.append(source_site.lower())

    if eligible_nationality:
        conditions.append("eligible_nationalities LIKE ?")
        params.append(f"%{eligible_nationality}%")

    if host_country:
        conditions.append("host_countries LIKE ?")
        params.append(f"%{host_country}%")

    if deadline_before:
        conditions.append("deadline <= ?")
        params.append(deadline_before)

    if deadline_after:
        conditions.append("(deadline >= ? OR deadline IS NULL)")
        params.append(deadline_after)

    if has_amount:
        conditions.append("amount IS NOT NULL AND amount != ''")

    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""

    sort_col = sort if sort in ("scraped_at", "deadline", "title", "amount_usd") else "scraped_at"
    order_dir = "DESC" if order.lower() == "desc" else "ASC"

    # Null-safe sort: NULLs last
    order_clause = f"ORDER BY CASE WHEN {sort_col} IS NULL THEN 1 ELSE 0 END, {sort_col} {order_dir}"

    count_row = conn.execute(f"SELECT COUNT(*) as cnt FROM scholarships {where}", params).fetchone()
    total = count_row["cnt"] if count_row else 0

    rows = conn.execute(
        f"SELECT * FROM scholarships {where} {order_clause} LIMIT ? OFFSET ?",
        params + [limit, offset],
    ).fetchall()
    conn.close()

    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "items": [row_to_dict(r) for r in rows],
    }


@app.get("/api/scholarships/{scholarship_id}")
def get_scholarship(scholarship_id: str):
    conn = get_conn()
    row = conn.execute("SELECT * FROM scholarships WHERE id = ?", [scholarship_id]).fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="Not found")
    return row_to_dict(row)


@app.get("/api/stats")
def get_stats():
    conn = get_conn()
    total = conn.execute("SELECT COUNT(*) as cnt FROM scholarships").fetchone()["cnt"]
    sites = conn.execute(
        "SELECT source_site, COUNT(*) as cnt FROM scholarships GROUP BY source_site ORDER BY cnt DESC"
    ).fetchall()
    degrees = conn.execute(
        "SELECT degree_levels, COUNT(*) as cnt FROM scholarships GROUP BY degree_levels ORDER BY cnt DESC LIMIT 10"
    ).fetchall()
    with_deadline = conn.execute("SELECT COUNT(*) as cnt FROM scholarships WHERE deadline IS NOT NULL").fetchone()["cnt"]
    with_amount = conn.execute("SELECT COUNT(*) as cnt FROM scholarships WHERE amount IS NOT NULL AND amount != ''").fetchone()["cnt"]
    latest = conn.execute("SELECT scraped_at FROM scholarships ORDER BY scraped_at DESC LIMIT 1").fetchone()
    conn.close()

    return {
        "total": total,
        "with_deadline": with_deadline,
        "with_amount": with_amount,
        "last_scraped": latest["scraped_at"] if latest else None,
        "by_site": [{"site": r["source_site"], "count": r["cnt"]} for r in sites],
        "by_degree": [{"degree": r["degree_levels"], "count": r["cnt"]} for r in degrees],
    }


@app.get("/api/sites")
def get_sites():
    conn = get_conn()
    rows = conn.execute(
        "SELECT source_site, COUNT(*) as cnt FROM scholarships GROUP BY source_site ORDER BY source_site"
    ).fetchall()
    conn.close()
    return [{"name": r["source_site"], "count": r["cnt"]} for r in rows]


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
    _scrape_state = {"running": True, "started_at": datetime.utcnow().isoformat(), "finished_at": None, "count": 0, "error": None}
    try:
        project_root = Path(__file__).parent.parent
        cmd = [sys.executable, "-m", "scrapers.run_all", "--max-pages", str(max_pages)]
        if owl:
            cmd.append("--owl")
        result = subprocess.run(cmd, cwd=str(project_root), capture_output=True, text=True, timeout=3600)
        # Parse count from output
        import re
        m = re.search(r"(\d+) scholarships saved", result.stdout + result.stderr)
        count = int(m.group(1)) if m else 0
        _scrape_state.update({"running": False, "finished_at": datetime.utcnow().isoformat(), "count": count})
    except Exception as e:
        _scrape_state.update({"running": False, "finished_at": datetime.utcnow().isoformat(), "error": str(e)})
