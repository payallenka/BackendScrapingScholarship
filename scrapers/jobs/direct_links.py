"""
Static config for direct-link job sources (no ingestion, just links for frontend display).
"""
DIRECT_LINK_SOURCES = [
    {
        "id": "canada_job_bank",
        "title": "Canada Job Bank (LMIA)",
        "description": "Browse all Canadian jobs open to foreign applicants (LMIA).",
        "url": "https://www.jobbank.gc.ca/jobsearch/jobsearch?flg=E&source=7",
        "logo_url": None
    },
    {
        "id": "world_bank_jobs",
        "title": "World Bank Careers",
        "description": "Explore global opportunities at the World Bank.",
        "url": "https://www.worldbank.org/ext/en/careers",
        "logo_url": None
    },
    {
        "id": "nhs_jobs",
        "title": "NHS Jobs (UK Health Sector)",
        "description": "Search for jobs in the UK health sector (NHS).",
        "url": "https://www.jobs.nhs.uk/candidate/search/results",
        "logo_url": None
    }
]
