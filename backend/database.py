import json
import os
import sqlite3
from pathlib import Path

DB_PATH = Path(os.getenv("DB_PATH", str(Path(__file__).parent / "scholarships.db")))


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def row_to_dict(row: sqlite3.Row) -> dict:
    d = dict(row)
    for field in ("degree_levels", "fields_of_study", "eligible_nationalities", "host_countries", "tags"):
        if d.get(field):
            try:
                d[field] = json.loads(d[field])
            except Exception:
                d[field] = []
        else:
            d[field] = []
    if d.get("is_open") is not None:
        d["is_open"] = bool(d["is_open"])
    # funding_type may not exist in old rows
    d.setdefault("funding_type", None)
    return d


# --- Jobs Table Support (non-intrusive) ---
def init_jobs_table(conn: sqlite3.Connection):
    conn.execute('''
        CREATE TABLE IF NOT EXISTS jobs (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            company TEXT,
            location TEXT,
            contract_type TEXT,
            salary_min REAL,
            salary_max REAL,
            currency TEXT,
            description TEXT,
            tags TEXT,
            source TEXT NOT NULL,
            apply_url TEXT NOT NULL,
            posted_at TEXT,
            ingested_at TEXT NOT NULL,
            expires_at TEXT,
            logo_url TEXT,
            extra_data TEXT
        )
    ''')
    # Migration: add expires_at to existing databases
    try:
        conn.execute("ALTER TABLE jobs ADD COLUMN expires_at TEXT")
    except Exception:
        pass  # column already exists
    conn.execute('CREATE INDEX IF NOT EXISTS idx_jobs_source ON jobs(source)')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_jobs_posted_at ON jobs(posted_at)')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_jobs_expires_at ON jobs(expires_at)')
    conn.commit()

def upsert_jobs(conn: sqlite3.Connection, jobs):
    if not jobs:
        return
    rows = []
    for j in jobs:
        rows.append((
            j.id, j.title, j.company, j.location, j.contract_type,
            j.salary_min, j.salary_max, j.currency, j.description,
            json.dumps(j.tags), j.source, j.apply_url, j.posted_at,
            j.ingested_at, getattr(j, 'expires_at', None),
            j.logo_url, json.dumps(j.extra_data) if j.extra_data else None,
        ))
    conn.executemany('''
        INSERT OR REPLACE INTO jobs
        (id, title, company, location, contract_type, salary_min, salary_max, currency,
         description, tags, source, apply_url, posted_at, ingested_at, expires_at, logo_url, extra_data)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    ''', rows)

    # Remove jobs from this source that were not in the latest scrape batch
    source = jobs[0].source
    conn.execute("CREATE TEMPORARY TABLE IF NOT EXISTS _upsert_ids (id TEXT PRIMARY KEY)")
    conn.execute("DELETE FROM _upsert_ids")
    conn.executemany("INSERT OR IGNORE INTO _upsert_ids(id) VALUES (?)", [(j.id,) for j in jobs])
    conn.execute(
        "DELETE FROM jobs WHERE source = ? AND id NOT IN (SELECT id FROM _upsert_ids)",
        (source,),
    )
    conn.execute("DROP TABLE IF EXISTS _upsert_ids")
    conn.commit()
