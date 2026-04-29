"""
Run all job ingestion scripts and store results in jobs table.
Sources: RemoteOK, Arbeitnow, UK Sponsor Register, Canada Job Bank, NHS Jobs
"""
import logging
from backend.database import get_conn, init_jobs_table
from scrapers.jobs.remoteok import fetch_remoteok_jobs
from scrapers.jobs.arbeitnow import fetch_arbeitnow_jobs
from scrapers.jobs.uk_sponsor_register import fetch_uk_sponsor_jobs
from scrapers.jobs.canada_job_bank import fetch_canada_job_bank_jobs
from scrapers.jobs.nhs_jobs import fetch_nhs_jobs
from scrapers.jobs.world_bank import fetch_world_bank_jobs

def run_all_jobs():
    conn = get_conn()
    init_jobs_table(conn)
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
                from backend.database import upsert_jobs
                upsert_jobs(conn, jobs)
                total += len(jobs)
                logging.info(f"{name}: saved {len(jobs)} jobs (total: {total})")
        except Exception as e:
            logging.error(f"{name} failed: {e}")
    conn.close()
    logging.info(f"Done! {total} jobs saved.")

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_all_jobs()
