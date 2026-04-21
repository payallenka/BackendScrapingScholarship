import json
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / "scholarships.db"


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
