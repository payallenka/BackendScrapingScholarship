"""
Run all scrapers, normalize results, and persist to Supabase.

Usage:
    python -m scrapers.run_all                  # run all scrapers
    python -m scrapers.run_all --sites scholars4dev opportunitiesforafricans
    python -m scrapers.run_all --max-pages 5    # limit pages per scraper
"""
from __future__ import annotations
import argparse
import json
import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta

from dotenv import load_dotenv
from supabase import create_client

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("run_all")


def init_db():
    # Tables are managed in Supabase — nothing to do locally
    pass


def _get_supabase():
    return create_client(
        os.environ["SUPABASE_URL"],
        os.environ["SUPABASE_SERVICE_ROLE_KEY"],
    )


def upsert_scholarships(scholarships):
    if not scholarships:
        return
    sb = _get_supabase()
    rows = [
        {
            "id": s.id,
            "title": s.title,
            "organization": s.organization,
            "description": s.description,
            "amount": s.amount,
            "amount_usd": s.amount_usd,
            "funding_type": s.funding_type,
            "deadline": s.deadline,
            "deadline_raw": s.deadline_raw,
            "degree_levels": json.dumps(s.degree_levels),
            "fields_of_study": json.dumps(s.fields_of_study),
            "eligible_nationalities": json.dumps(s.eligible_nationalities),
            "host_countries": json.dumps(s.host_countries),
            "source_url": s.source_url,
            "source_site": s.source_site,
            "tags": json.dumps(s.tags),
            "scraped_at": s.scraped_at,
            "is_open": int(s.is_open) if s.is_open is not None else None,
            "image_url": s.image_url,
        }
        for s in scholarships
    ]
    sb.table("scholarships").upsert(rows, on_conflict="id").execute()


def purge_expired_scholarships(grace_days: int = 30) -> int:
    """Delete scholarships whose deadline passed more than grace_days ago.

    Undated scholarships (deadline NULL) are never purged — many sources never
    publish a deadline. Returns the number of rows deleted.
    """
    sb = _get_supabase()
    cutoff = (date.today() - timedelta(days=grace_days)).isoformat()
    deleted = 0
    try:
        resp = sb.table("scholarships").delete().lt("deadline", cutoff).execute()
        deleted += len(resp.data or [])
        logger.info(f"Purged {len(resp.data or [])} expired scholarships (deadline < {cutoff})")
    except Exception as e:
        logger.error(f"Failed to purge expired scholarships: {e}")
    # Also remove ones explicitly detected as closed for applications.
    try:
        resp = sb.table("scholarships").delete().eq("is_open", 0).execute()
        closed = len(resp.data or [])
        if closed:
            logger.info(f"Purged {closed} closed scholarships (is_open=0)")
        deleted += closed
    except Exception as e:
        logger.error(f"Failed to purge closed scholarships: {e}")
    return deleted


def purge_stale_scholarships(run_start_iso: str, scraped_count: int) -> int:
    """Delete scholarships not refreshed during the latest full scrape.

    A scholarship still listed on its source site is re-upserted with a fresh
    scraped_at, so any row left with scraped_at < run start is no longer present
    upstream (stale) and is removed. Guarded by scraped_count so a run where most
    scrapers failed (e.g. sites down) does not wipe the table.
    """
    sb = _get_supabase()
    existing = sb.table("scholarships").select("id", count="exact", head=True).execute().count or 0
    if scraped_count < 20 or scraped_count < existing * 0.5:
        logger.warning(
            f"Skipping stale purge: only {scraped_count} scraped vs {existing} existing (run looks partial)"
        )
        return 0
    try:
        resp = sb.table("scholarships").delete().lt("scraped_at", run_start_iso).execute()
        deleted = len(resp.data or [])
        logger.info(f"Purged {deleted} stale scholarships (scraped_at < {run_start_iso})")
        return deleted
    except Exception as e:
        logger.error(f"Failed to purge stale scholarships: {e}")
        return 0


def run_scraper(scraper_cls, max_pages: int):
    try:
        scraper = scraper_cls(max_pages=max_pages)
        return scraper.run()
    except Exception as e:
        logger.error(f"Failed to run {scraper_cls.__name__}: {e}")
        return []


def run_all_scrapers(max_pages: int = 10, workers: int = 4, on_source_done=None) -> int:
    """Run all scrapers in-process. Returns total count saved."""
    from scrapers.sites import ALL_SCRAPERS
    total = 0
    start = time.time()
    run_start_iso = datetime.utcnow().isoformat()
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(run_scraper, cls, max_pages): cls for cls in ALL_SCRAPERS}
        for future in as_completed(futures):
            cls = futures[future]
            try:
                results = future.result()
                if results:
                    upsert_scholarships(results)
                    total += len(results)
                    logger.info(f"{cls.__name__}: saved {len(results)} scholarships (running total: {total})")
                    if on_source_done:
                        on_source_done(cls.__name__, len(results), total)
                else:
                    logger.info(f"{cls.__name__}: 0 scholarships returned")
            except Exception as e:
                logger.error(f"{cls.__name__} failed: {e}")
    purge_stale_scholarships(run_start_iso, total)
    purge_expired_scholarships()
    elapsed = time.time() - start
    logger.info(f"Done! {total} scholarships saved in {elapsed:.1f}s")
    return total


def main():
    parser = argparse.ArgumentParser(description="Run all scholarship scrapers")
    parser.add_argument("--sites", nargs="*", help="Specific scraper names to run")
    parser.add_argument("--max-pages", type=int, default=10)
    parser.add_argument("--workers", type=int, default=4, help="Parallel workers")
    args = parser.parse_args()

    from scrapers.sites import ALL_SCRAPERS

    scrapers_to_run = ALL_SCRAPERS
    if args.sites:
        scrapers_to_run = [s for s in ALL_SCRAPERS if s(max_pages=1).name in args.sites]

    total = 0
    start = time.time()
    run_start_iso = datetime.utcnow().isoformat()

    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {executor.submit(run_scraper, cls, args.max_pages): cls for cls in scrapers_to_run}
        for future in as_completed(futures):
            cls = futures[future]
            try:
                results = future.result()
                if results:
                    upsert_scholarships(results)
                    total += len(results)
                    logger.info(f"{cls.__name__}: saved {len(results)} scholarships (total: {total})")
            except Exception as e:
                logger.error(f"{cls.__name__} failed: {e}")

    purge_stale_scholarships(run_start_iso, total)
    purge_expired_scholarships()
    elapsed = time.time() - start
    logger.info(f"\nDone! {total} scholarships saved in {elapsed:.1f}s")


if __name__ == "__main__":
    main()
