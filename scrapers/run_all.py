"""
Run all scrapers, normalize results, and persist to SQLite.

Usage:
    python -m scrapers.run_all                  # run all scrapers
    python -m scrapers.run_all --sites scholars4dev opportunitiesforafricans
    python -m scrapers.run_all --owl            # include ScholarshipOwl API
    python -m scrapers.run_all --max-pages 5    # limit pages per scraper
"""
from __future__ import annotations
import argparse
import json
import logging
import os
import sqlite3
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import List

from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("run_all")

DB_PATH = Path(__file__).parent.parent / "backend" / "scholarships.db"


def init_db(conn: sqlite3.Connection):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS scholarships (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            organization TEXT,
            description TEXT,
            amount TEXT,
            amount_usd REAL,
            funding_type TEXT,
            deadline TEXT,
            deadline_raw TEXT,
            degree_levels TEXT,
            fields_of_study TEXT,
            eligible_nationalities TEXT,
            host_countries TEXT,
            source_url TEXT NOT NULL,
            source_site TEXT NOT NULL,
            tags TEXT,
            scraped_at TEXT NOT NULL,
            is_open INTEGER,
            image_url TEXT
        )
    """)
    # Add funding_type column to existing databases that predate this field
    try:
        conn.execute("ALTER TABLE scholarships ADD COLUMN funding_type TEXT")
    except Exception:
        pass
    conn.execute("CREATE INDEX IF NOT EXISTS idx_source_site ON scholarships(source_site)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_deadline ON scholarships(deadline)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_scraped_at ON scholarships(scraped_at)")
    conn.commit()


def upsert_scholarships(conn: sqlite3.Connection, scholarships):
    rows = []
    for s in scholarships:
        rows.append((
            s.id, s.title, s.organization, s.description,
            s.amount, s.amount_usd, s.funding_type, s.deadline, s.deadline_raw,
            json.dumps(s.degree_levels), json.dumps(s.fields_of_study),
            json.dumps(s.eligible_nationalities), json.dumps(s.host_countries),
            s.source_url, s.source_site, json.dumps(s.tags),
            s.scraped_at, int(s.is_open) if s.is_open is not None else None,
            s.image_url,
        ))
    conn.executemany("""
        INSERT OR REPLACE INTO scholarships
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, rows)
    conn.commit()


def run_scraper(scraper_cls, max_pages: int):
    try:
        scraper = scraper_cls(max_pages=max_pages)
        return scraper.run()
    except Exception as e:
        logger.error(f"Failed to run {scraper_cls.__name__}: {e}")
        return []


def main():
    parser = argparse.ArgumentParser(description="Run all scholarship scrapers")
    parser.add_argument("--sites", nargs="*", help="Specific scraper names to run")
    parser.add_argument("--owl", action="store_true", help="Include ScholarshipOwl API")
    parser.add_argument("--max-pages", type=int, default=10)
    parser.add_argument("--workers", type=int, default=4, help="Parallel workers")
    args = parser.parse_args()

    from scrapers.sites import ALL_SCRAPERS

    scrapers_to_run = ALL_SCRAPERS
    if args.sites:
        scrapers_to_run = [s for s in ALL_SCRAPERS if s(max_pages=1).name in args.sites]

    if args.owl:
        from scrapers.owl_api import ScholarshipOwlAPI
        scrapers_to_run = list(scrapers_to_run) + [ScholarshipOwlAPI]

    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    init_db(conn)

    total = 0
    start = time.time()

    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {executor.submit(run_scraper, cls, args.max_pages): cls for cls in scrapers_to_run}
        for future in as_completed(futures):
            cls = futures[future]
            try:
                results = future.result()
                if results:
                    upsert_scholarships(conn, results)
                    total += len(results)
                    logger.info(f"{cls.__name__}: saved {len(results)} scholarships (total: {total})")
            except Exception as e:
                logger.error(f"{cls.__name__} failed: {e}")

    conn.close()
    elapsed = time.time() - start
    logger.info(f"\nDone! {total} scholarships saved to {DB_PATH} in {elapsed:.1f}s")


if __name__ == "__main__":
    main()
