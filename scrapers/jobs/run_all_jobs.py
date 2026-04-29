"""
Run all job ingestion scripts and store results in Supabase.
Sources: RemoteOK, Arbeitnow, UK Sponsor Register, Canada Job Bank, NHS Jobs, World Bank
"""
import logging

from backend.database import upsert_jobs
from scrapers.jobs.remoteok import fetch_remoteok_jobs
from scrapers.jobs.arbeitnow import fetch_arbeitnow_jobs
from scrapers.jobs.uk_sponsor_register import fetch_uk_sponsor_jobs
from scrapers.jobs.canada_job_bank import fetch_canada_job_bank_jobs
from scrapers.jobs.nhs_jobs import fetch_nhs_jobs
from scrapers.jobs.world_bank import fetch_world_bank_jobs


def run_all_jobs(on_source_done=None) -> int:
    total = 0
    for fetch_func, name in [
        (fetch_remoteok_jobs,        "RemoteOK"),
        (fetch_arbeitnow_jobs,       "Arbeitnow"),
        (fetch_uk_sponsor_jobs,      "UK Sponsor Register"),
        (fetch_canada_job_bank_jobs, "Canada Job Bank"),
        (fetch_nhs_jobs,             "NHS Jobs"),
        (fetch_world_bank_jobs,      "World Bank"),
    ]:
        try:
            jobs = fetch_func()
            if jobs:
                upsert_jobs(jobs)
                total += len(jobs)
                logging.info(f"{name}: saved {len(jobs)} jobs (running total: {total})")
                if on_source_done:
                    on_source_done(name, len(jobs), total)
            else:
                logging.info(f"{name}: 0 jobs returned")
        except Exception as e:
            logging.error(f"{name} failed: {e}")
    logging.info(f"Done! {total} jobs saved.")
    return total


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_all_jobs()
