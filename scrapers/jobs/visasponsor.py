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
# Hosts that are visasponsor's own pages / socials, not the real job listing.
_NOT_APPLY = ("visasponsor", "facebook.", "linkedin.", "twitter.", "instagram.",
              "docs.google.", "helpsite.", "youtube.")

_CURRENCY_CODE_RE = re.compile(r"\b(GBP|USD|CAD|EUR|AUD|NZD)\b", re.I)
_NUMBER_RE = re.compile(r"\d+(?:\.\d+)?")
_SYMBOL_CURRENCY = {"£": "GBP", "€": "EUR"}
# "$" alone is ambiguous (US vs CA), so fall back to the country we crawled under.
_COUNTRY_CURRENCY = {"United-States": "USD", "United-Kingdom": "GBP", "Canada": "CAD"}
# Scale a rate to a yearly figure. 2080 = 40h/week x 52 weeks, matching the
# convention already used by canada_job_bank and nhs_jobs.
_PERIOD_MULT = (("hour", 2080), ("day", 260), ("week", 52), ("month", 12),
                ("year", 1), ("annum", 1))
# Trailing ATS tracking marker, e.g. "#J-18808-Ljbffr".
_ATS_MARKER_RE = re.compile(r"#J-\d+-\w+")


def _extract_apply_url(detail_soup):
    """Pull the real 'APPLY NOW' destination off a visasponsor detail page.

    The apply button always carries the class `application-button`; its href is
    the real listing (often LinkedIn Jobs, Glassdoor, an ATS, or the employer
    site). We take that href as long as it points off visasponsor itself."""
    btn = detail_soup.select_one("a.application-button[href]")
    if btn:
        href = btn["href"].strip()
        if href.startswith("http") and "visasponsor" not in href.lower():
            return href
    # Fallback: any external anchor whose text mentions "apply".
    for a in detail_soup.find_all("a", href=True):
        href = a["href"]
        if href.startswith("http") and "visasponsor" not in href.lower() \
                and "apply" in a.get_text(" ", strip=True).lower():
            return href
    return None


def _parse_salary(text, country=None):
    """Parse a visasponsor salary line into (min, max, currency), annualized.

    The site has no single format; observed shapes are
        "GBP 40000.00 60000.00 YEAR"    "27 - 42 CAD /HOUR"
        "From $16.35 an hour"           "17.4 - 18.5 CAD /HOUR"
    so read the currency, the numbers and the period independently rather than
    matching a fixed layout. Rates are scaled to a yearly figure because the
    schema has no period column and the UI renders salary_min/max as a bare
    amount — storing "27" for an hourly role would read as a yearly wage.
    """
    if not text:
        return None, None, None

    m = _CURRENCY_CODE_RE.search(text)
    currency = m.group(1).upper() if m else None
    if not currency:
        currency = next((c for s, c in _SYMBOL_CURRENCY.items() if s in text), None)
    if not currency:
        currency = _COUNTRY_CURRENCY.get(country)

    lowered = text.lower()
    mult = next((m_ for word, m_ in _PERIOD_MULT if word in lowered), 1)

    # Drop the currency code first so a code like "CAD" can't contribute digits.
    vals = [float(n) for n in _NUMBER_RE.findall(_CURRENCY_CODE_RE.sub("", text).replace(",", ""))]
    vals = [round(v * mult) for v in vals if v > 0]
    if not vals:
        return None, None, None
    low = vals[0]
    high = vals[1] if len(vals) >= 2 else None
    if high is not None and high < low:
        low, high = high, low
    return low, high, currency


def _extract_salary_text(detail_soup):
    """Return the raw text of the detail page's Salary field, if it has one.

    Roughly half of listings omit salary entirely."""
    for blk in detail_soup.select("div.my-3"):
        label = blk.select_one("div.sub-font")
        value = blk.select_one("div.fw-medium.sub-font")
        if label and value and label.get_text(strip=True).lower() == "salary":
            return value.get_text(" ", strip=True)
    return None


def _extract_description(detail_soup):
    """Return the detail page's job description as plain text."""
    for col in detail_soup.select("div.col-12.col-lg-8.pe-lg-5"):
        head = col.select_one("div.fs-5.fw-bold.mb-2")
        if not head or "job description" not in head.get_text(" ", strip=True).lower():
            continue
        body = col.select_one("div.sub-font")
        if not body:
            continue
        text = _ATS_MARKER_RE.sub("", body.get_text(" ", strip=True))
        return re.sub(r"\s+", " ", text).strip() or None
    return None


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
    countries = {}          # job id -> country crawled under, to read "$" correctly
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
                    countries[job.id] = country

            if len(cards) < 30:   # last page
                break

    _enrich_from_detail_pages(jobs, countries, BeautifulSoup)
    logger.info(f"visasponsor: fetched {len(jobs)} jobs")
    return jobs


def _enrich_from_detail_pages(jobs, countries, BeautifulSoup):
    """Fill in each job's apply_url, description and salary from its detail page.

    The card grid carries only title/company/location/tags, so a card alone
    yields a listing with no description and no pay. The detail page has both,
    and we already have to fetch it to find the real 'APPLY NOW' destination —
    so parse everything out of that one visit.

    Jobs we have already enriched are reused from the DB, keeping a nightly run
    down to the genuinely new listings."""
    known = {}
    try:
        from backend.database import get_supabase
        rows = get_supabase().table("jobs").select(
            "id,apply_url,description,salary_min,salary_max,currency"
        ).eq("source", "visasponsor").execute().data or []
        # Only reuse a row we fully resolved before. A stored visasponsor.jobs
        # URL means a past run failed to find the real link, and a missing
        # description means the row predates detail-page enrichment — re-fetch
        # both. (A listing that genuinely has no description is re-fetched each
        # run; that's a handful of pages, not worth a sentinel column.)
        known = {r["id"]: r for r in rows
                 if r.get("apply_url") and "visasponsor.jobs" not in r["apply_url"]
                 and r.get("description")}
    except Exception as e:
        logger.warning(f"visasponsor: could not load known jobs: {e}")

    fetched = 0
    for j in jobs:
        prev = known.get(j.id)
        if prev:
            # Carry the stored values across: upsert_jobs writes every column,
            # so leaving these None would wipe what an earlier run resolved.
            j.apply_url   = prev["apply_url"]
            j.description = prev["description"]
            j.salary_min  = prev.get("salary_min")
            j.salary_max  = prev.get("salary_max")
            j.currency    = prev.get("currency")
            continue
        try:
            soup = BeautifulSoup(polite_get(j.apply_url).text, "lxml")
            j.description = _extract_description(soup)
            j.salary_min, j.salary_max, j.currency = _parse_salary(
                _extract_salary_text(soup), countries.get(j.id))
            direct = _extract_apply_url(soup)
            if direct:
                j.apply_url = direct          # else keep the detail page as fallback
            fetched += 1
        except Exception as e:
            logger.debug(f"visasponsor: detail page failed for {j.id}: {e}")
    logger.info(f"visasponsor: enriched from detail pages "
                f"({len(jobs) - fetched} reused, {fetched} fetched)")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    jobs = fetch_visasponsor_jobs()
    upsert_jobs(jobs)
    print(f"Ingested {len(jobs)} jobs from visasponsor.jobs.")
