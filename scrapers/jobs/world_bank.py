"""
Ingest jobs from World Bank Group Careers (CSOD ATS, session-based API).
Establishes a browser-like session to get a JWT token, then calls the
internal search + detail endpoints.
"""
import logging
import re
import requests
from bs4 import BeautifulSoup
from datetime import datetime

from scrapers.normalizer import NormalizedJob
from backend.database import get_conn, upsert_jobs, init_jobs_table

logger = logging.getLogger(__name__)

HOME_URL   = "https://worldbankgroup.csod.com/ux/ats/careersite/1/home?c=worldbankgroup"
SEARCH_URL = "https://worldbankgroup.csod.com/services/x/career-site/v1/search"
DETAIL_URL = "https://worldbankgroup.csod.com/services/x/job-requisition/v2/requisitions/{id}/jobDetails?cultureId=1"
APPLY_URL  = "https://worldbankgroup.csod.com/ux/ats/careersite/1/home/requisition/{id}"
PAGE_SIZE  = 50


def _get_session_and_token():
    """Load the career site home page to get session cookies + JWT token."""
    s = requests.Session()
    s.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"})
    resp = s.get(HOME_URL, timeout=20)
    resp.raise_for_status()
    m = re.search(r'"token":"([^"]+)"', resp.text)
    if not m:
        raise RuntimeError("Could not extract CSOD token from World Bank careers page")
    token = m.group(1)
    s.headers.update({
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Origin": "https://worldbankgroup.csod.com",
        "Referer": "https://worldbankgroup.csod.com/",
    })
    return s


def _search_page(session, page_number):
    body = {
        "careerSiteId": 1,
        "careerSitePageId": 1,
        "pageNumber": page_number,
        "pageSize": PAGE_SIZE,
        "cultureId": 1,
        "cultureName": "en-US",
        "searchText": "",
        "states": [],
        "countryCodes": [],
        "cities": [],
    }
    resp = session.post(SEARCH_URL, json=body, timeout=20)
    resp.raise_for_status()
    data = resp.json().get("data", {})
    return data.get("requisitions", []), data.get("totalCount", 0)


def _get_description(session, req_id):
    try:
        resp = session.get(DETAIL_URL.format(id=req_id), timeout=15)
        if resp.ok:
            detail = resp.json().get("data", {})
            raw_html = detail.get("externalDescription", "") or ""
            return _strip_html(raw_html)
    except Exception as e:
        logger.debug(f"World Bank detail fetch failed for {req_id}: {e}")
    return ""


def _strip_html(html):
    if not html:
        return ""
    return re.sub(r"\s{2,}", " ",
        re.sub(r"<[^>]+>", " ",
        html.replace("&nbsp;", " ").replace("&amp;", "&")
            .replace("&lt;", "<").replace("&gt;", ">")
            .replace("&quot;", '"').replace("&#39;", "'")
    )).strip()


def fetch_world_bank_jobs():
    try:
        session = _get_session_and_token()
    except Exception as e:
        logger.error(f"World Bank session setup failed: {e}")
        return []

    now = datetime.utcnow().isoformat()
    jobs = []

    try:
        requisitions, total = _search_page(session, 1)
        logger.info(f"World Bank: {total} total jobs")
    except Exception as e:
        logger.error(f"World Bank search failed: {e}")
        return []

    # Fetch remaining pages
    page = 2
    while len(requisitions) < total and len(requisitions) < 500:
        try:
            more, _ = _search_page(session, page)
            if not more:
                break
            requisitions.extend(more)
            page += 1
        except Exception as e:
            logger.error(f"World Bank page {page} failed: {e}")
            break

    for req in requisitions:
        req_id   = req.get("requisitionId")
        title    = req.get("displayJobTitle", "Position Available")
        posted   = req.get("postingEffectiveDate", "")
        locs     = req.get("locations", [])
        location = ", ".join(filter(None, [
            locs[0].get("city", ""),
            locs[0].get("state") or "",
            locs[0].get("country", ""),
        ])) if locs else "Washington, DC"

        description = _get_description(session, req_id)

        posted_at = None
        if posted:
            try:
                posted_at = datetime.strptime(posted, "%m/%d/%Y").isoformat()
            except Exception:
                pass

        jobs.append(NormalizedJob(
            id=f"worldbank_{req_id}",
            title=title,
            company="World Bank Group",
            location=location,
            contract_type=None,
            salary_min=None,
            salary_max=None,
            currency=None,
            description=description or f"{title} at the World Bank Group. International development role.",
            tags=["World Bank", "International Development", "Global"],
            source="world_bank",
            apply_url=APPLY_URL.format(id=req_id),
            posted_at=posted_at,
            ingested_at=now,
            logo_url=None,
            extra_data=None,
        ))

    logger.info(f"World Bank: fetched {len(jobs)} jobs")
    return jobs


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    conn = get_conn()
    init_jobs_table(conn)
    jobs = fetch_world_bank_jobs()
    upsert_jobs(conn, jobs)
    print(f"Ingested {len(jobs)} jobs from World Bank.")
    conn.close()
