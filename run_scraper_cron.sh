#!/bin/bash
cd /home/zbook/Desktop/practice/scraping
source venv/bin/activate
python -m scrapers.run_all >> /home/zbook/Desktop/practice/scraping/scraper_cron.log 2>&1
python -m scrapers.jobs.run_all_jobs >> /home/zbook/Desktop/practice/scraping/scraper_cron.log 2>&1
