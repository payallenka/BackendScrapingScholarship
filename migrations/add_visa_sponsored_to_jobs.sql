-- Adds a per-job visa_sponsored flag to the jobs table.
-- Run this in the Supabase SQL editor before deploying the visa-detection change.
-- Existing rows default to false; they get accurate values on the next scrape.

alter table jobs
  add column if not exists visa_sponsored boolean not null default false;

-- Optional: speeds up the /api/jobs?visa_sponsored=true filter.
create index if not exists idx_jobs_visa_sponsored
  on jobs (visa_sponsored)
  where visa_sponsored = true;
