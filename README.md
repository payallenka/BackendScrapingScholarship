# ScholarshipHub

A full-stack scholarship aggregator built for **African and international students**. Scrapes 10 authoritative global scholarship sources, normalises all data into a unified schema, stores it in SQLite, and uses **Groq + Llama 3.3 70B** to generate a personalised top-10 shortlist from the user's Supabase profile — no form to fill.

---

## Table of Contents

1. [High-Level Design](#high-level-design)
2. [System Flow — end to end](#system-flow)
3. [Low-Level Design](#low-level-design)
   - [Scraping Layer](#1-scraping-layer)
   - [Normalisation Layer](#2-normalisation-layer)
   - [Storage Layer](#3-storage-layer)
   - [Backend API Layer](#4-backend-api-layer)
   - [AI Matching Engine](#5-ai-matching-engine)
   - [Frontend Layer](#6-frontend-layer)
4. [Find My Match — full flow](#find-my-match--full-flow)
5. [Normalised Data Schema](#normalised-data-schema)
6. [API Reference](#api-reference)
7. [Quick Start](#quick-start)
8. [Sources](#sources)
9. [Project Structure](#project-structure)
10. [Adding a New Scraper](#adding-a-new-scraper)

---

## High-Level Design

```
┌─────────────────────────────────────────────────────────────────────┐
│                          SCRAPING LAYER                              │
│  10 real-site scrapers — dynamic HTML + known-program fallbacks      │
│  Cron: */15 * * * *  →  run_scraper_cron.sh                         │
└────────────────────────────┬────────────────────────────────────────┘
                             │  List[NormalizedScholarship]
                             ▼
┌─────────────────────────────────────────────────────────────────────┐
│                       NORMALISATION LAYER                            │
│  normalizer.py — unified schema, date parsing, funding inference,    │
│  degree level mapping, eligibility detection, org extraction         │
└────────────────────────────┬────────────────────────────────────────┘
                             │  INSERT OR REPLACE (upsert by UUID)
                             ▼
┌─────────────────────────────────────────────────────────────────────┐
│                        STORAGE LAYER                                 │
│  SQLite  (backend/scholarships.db)                                   │
│  ID = UUID v5(source_url) — same URL = same record, always refreshed │
└────────────────────────────┬────────────────────────────────────────┘
                             │  SELECT / query
                             ▼
┌─────────────────────────────────────────────────────────────────────┐
│                       BACKEND API LAYER                              │
│  FastAPI (backend/main.py) — browse, filter, search, match, scrape   │
└──────────────────────┬──────────────────────┬────────────────────────┘
                       │  /api/*              │  POST /api/match
                       ▼                      ▼
         ┌──────────────────────┐  ┌──────────────────────────────────┐
         │    FRONTEND          │  │     AI MATCHING ENGINE            │
         │  React + Supabase    │  │  matcher.py                       │
         │                      │  │  1. Read user_roles from Supabase │
         │  Browse All tab:     │  │  2. Budget math + funding tier    │
         │    filter/search/    │  │  3. SQL pre-filter by degree,     │
         │    paginate          │  │     nationality, host country,    │
         │                      │  │     funding need                  │
         │  Find My Match tab:  │  │  4. Boost target-country matches  │
         │    auto-loads from   │  │  5. Build prompt with hard rules  │
         │    Supabase profile  │  │  6. Groq llama-3.3-70b (temp 0.2)│
         │    → shows results   │  │  7. Return ranked top 10 + JSON   │
         └──────────────────────┘  └──────────────────────────────────┘
```

---

## System Flow

### Scraping → Storage

```
run_scraper_cron.sh  (cron: every 15 minutes)
    │
    └── python -m scrapers.run_all
            │
            ├── ThreadPoolExecutor (4 workers, parallel)
            │       │
            │       ├── scraper_cls(max_pages=N).run()
            │       │       └── BaseScraper._get(url)
            │       │           ├── Retry adapter (3×, backoff, 429/5xx)
            │       │           ├── 1.5s + jitter rate limit per request
            │       │           └── get_soup() → BeautifulSoup (lxml)
            │       │
            │       └── List[NormalizedScholarship] returned
            │
            └── upsert_scholarships(conn, results)
                    └── INSERT OR REPLACE INTO scholarships (19 columns)
                        id = UUID v5(source_url)  ← same URL = same record
```

### Find My Match — User Request → Results

```
User opens "Find My Match" tab (no form)
    │
    ├── supabase.from("user_roles").select(...)
    │       Fields read:
    │         name, degree_level, gpa, language_score
    │         languages          → ["English", "French"]
    │         budget             → "$5,000" → parsed to float 5000.0
    │         target_countries   → ["Canada", "UK"]
    │         application_report → { form: { nationality, academicGoals } }
    │
    ├── Budget math (frontend):
    │       rawBudget → parseFloat(str.replace(/[^\d.]/g,"")) → budget_usd
    │
    ├── POST /api/match  { name, nationality, target_level, field,
    │                      languages, budget_usd, background, extra }
    ▼
FastAPI /api/match
    │
    ├── _parse_budget(budget_usd) → funding_need tier:
    │       < $3,000  → "full"    (only fully funded scholarships)
    │       $3k–$15k  → "partial" (full or partial)
    │       > $15k    → "flexible"
    │
    ├── get_candidates(profile, limit=60)  — SQL pre-filter:
    │       WHERE deadline >= today
    │         AND degree_levels LIKE '%"masters"%'
    │         AND (eligible_nationalities = '[]'
    │              OR eligible_nationalities LIKE '%Nigerian%'
    │              OR eligible_nationalities LIKE '%African%'
    │              OR eligible_nationalities LIKE '%Commonwealth%')
    │         AND (funding_type = 'full')     ← only if budget < $3k
    │       ORDER BY
    │         deadline ASC (soonest first),
    │         funding_type (full > partial > unknown),
    │         amount IS NOT NULL,
    │         scraped_at DESC
    │       → then boost host-country matches to front
    │
    ├── _build_user_msg(profile, candidates)
    │       Student profile block includes:
    │         - Nationality, degree level, field of study
    │         - Languages spoken (["English","French"])
    │         - Budget + funding need tier + plain-English explanation
    │         - GPA, language score, target countries
    │       Scholarship list: each entry includes host country + eligibility
    │
    ├── System prompt HARD RULES (applied by LLM before ranking):
    │       1. Nationality must be eligible
    │       2. Degree level must match
    │       3. Language: if host country uses non-English language,
    │          student must speak it (unless scholarship teaches in English)
    │       4. Budget: student must get enough coverage for their funding need
    │
    ├── Groq API: llama-3.3-70b-versatile
    │       temperature: 0.2 | max_tokens: 2500 | response_format: json_object
    │
    ├── Response: { summary, matches: [{ rank, index, reason,
    │                                    highlights, funding_coverage }] }
    │
    └── Attach full scholarship object to each match → return
    │
    ▼
Frontend renders:
  - Profile chip bar (nationality, level, field, languages, budget tier)
  - AI Advisor summary card (gradient dark background)
  - Ranked match cards with:
      · Funding banner (Fully Funded / Partial / amount) at top
      · ★ TOP PICK badge on rank 1
      · "Why this match" in italic quote box
      · Highlights as ✓ chips
      · Deadline with urgency colouring (red < 60 days, amber < 90 days)
      · Inline Apply link
```

---

## Low-Level Design

### 1. Scraping Layer

**Files:** `scrapers/base.py`, `scrapers/sites/*.py`

**Cron schedule:** `*/15 * * * *` — runs `run_scraper_cron.sh` every 15 minutes. `INSERT OR REPLACE` ensures data is always fresh; same URLs produce the same UUID so no duplicates accumulate.

**Libraries:**
| Library | Purpose |
|---------|---------|
| `requests` | HTTP client for all site fetches |
| `requests.adapters.Retry` | Auto-retry on 429, 500–504 (3×, exponential backoff) |
| `BeautifulSoup` + `lxml` | HTML parsing |
| `httpx` | Async HTTP used by the AI matcher |

**`BaseScraper` mechanics:**
- Every scraper inherits `BaseScraper(max_pages: int)`
- `_get(url)` enforces **1.5s + random jitter** between requests
- Persistent `requests.Session` with browser-like headers per scraper
- `get_soup(url)` → parses HTML with `lxml`

**Scraping strategy per site:**
| Strategy | Description |
|----------|-------------|
| Dynamic HTML + known fallbacks | Primary: fetch listing/program pages and follow links matching scholarship keywords. Fallback: known program URLs hardcoded for sites that block or load content via JS |
| Hardcoded (blocked) | Chevening (timeout), AfDB (403) — description/deadline still fetched from main page |

---

### 2. Normalisation Layer

**File:** `scrapers/normalizer.py`

Every scraper calls `make_scholarship(title, source_url, source_site, **kwargs)`:

#### ID generation
```python
id = str(uuid.uuid5(uuid.NAMESPACE_URL, source_url))
```
Same URL always produces the same UUID — `INSERT OR REPLACE` refreshes the record in place.

#### Funding type inference — 3-pass
| Pass | Source | Logic |
|------|--------|-------|
| 1 | `amount` field | `"fully funded"`, `"covers all"` → `"full"`. `"partial"`, `"up to"` → `"partial"`. Currency `$10k+` → `"full"` |
| 2 | Title | Same keyword scan on title |
| 3 | Description | `infer_funding_from_description()` keyword scan |

#### Degree level mapping
Raw text → keyword scan against `_DEGREE_MAP`:
```python
"masters": ["master's", "msc", "m.sc", "mba", ...]
"phd":     ["ph.d", "phd", "doctorate", "doctoral", ...]
```

#### Deadline parsing — 4-stage pipeline
1. Strip label prefixes (`"Deadline:"`, `"Apply by:"`)
2. Handle ambiguous text (`"varies"`, `"rolling"`)
3. `dateutil.parser.parse(text, dayfirst=True)` → `YYYY-MM-DD`
4. Fallback regex: `DD Month YYYY`, `Month DD, YYYY`, `YYYY-MM-DD`

---

### 3. Storage Layer

**File:** `backend/scholarships.db` (SQLite)

```sql
CREATE TABLE scholarships (
    id               TEXT PRIMARY KEY,    -- UUID v5(source_url)
    title            TEXT NOT NULL,
    organization     TEXT,
    description      TEXT,
    amount           TEXT,                -- "Fully Funded", "$10,000/yr"
    amount_usd       REAL,                -- normalised USD float for sorting
    funding_type     TEXT,                -- "full" | "partial" | null
    deadline         TEXT,                -- ISO YYYY-MM-DD
    deadline_raw     TEXT,                -- original human text
    degree_levels    TEXT,                -- JSON: ["masters","phd"]
    fields_of_study  TEXT,                -- JSON array
    eligible_nationalities TEXT,          -- JSON: ["African","Commonwealth citizens"]
    host_countries   TEXT,                -- JSON: ["UK","Canada"]
    source_url       TEXT NOT NULL,
    source_site      TEXT NOT NULL,
    tags             TEXT,                -- JSON array
    scraped_at       TEXT NOT NULL,
    is_open          INTEGER,
    image_url        TEXT
);
```

**Upsert:** `INSERT OR REPLACE` on `id`. Re-running the cron refreshes existing records (new deadline, description updates) without creating duplicates.

---

### 4. Backend API Layer

**File:** `backend/main.py` — FastAPI + uvicorn

| Endpoint | Method | What it does |
|----------|--------|--------------|
| `/api/scholarships` | GET | Paginated list with full filter support |
| `/api/scholarships/{id}` | GET | Single record |
| `/api/stats` | GET | Counts by site, degree, funding, deadline |
| `/api/sites` | GET | Source list with counts |
| `/api/scrape` | POST | Spawns `run_all.py` in a background thread |
| `/api/scrape/status` | GET | `{ running: bool }` |
| `/api/match` | POST | AI-powered matching — see section below |

---

### 5. AI Matching Engine

**File:** `backend/matcher.py`

**Model:** `llama-3.3-70b-versatile` via Groq (OpenAI-compatible, `temperature: 0.2`)

#### UserProfile fields
```python
class UserProfile(BaseModel):
    name: str
    nationality: str
    current_level: str        # "bachelor" | "masters" | "phd" | "high_school"
    target_level: str         # "undergraduate" | "masters" | "phd"
    field: str                # e.g. "Computer Science"
    languages: List[str]      # e.g. ["English", "French"]
    budget_usd: float | None  # parsed from user's budget string
    background: str | None    # "GPA: 3.8, Language score: 7.5"
    extra: str | None         # "Preferred countries: Canada, UK"
```

#### Budget math
```python
def _funding_need(budget_usd):
    if budget_usd < 3_000:  return "full"     # must be fully funded
    if budget_usd < 15_000: return "partial"  # full or partial OK
    return "flexible"                          # has funds, ranking bonus only
```

#### SQL pre-filter (before LLM)
```sql
WHERE (deadline IS NULL OR deadline >= today)
  AND (degree_levels LIKE '%"masters"%' OR degree_levels LIKE '%"any"%')
  AND (eligible_nationalities = '[]'
       OR eligible_nationalities LIKE '%Nigerian%'   -- user nationality
       OR eligible_nationalities LIKE '%African%'
       OR eligible_nationalities LIKE '%Commonwealth%')
  AND (funding_type = 'full')   -- only when budget_usd < $3,000
ORDER BY
  deadline ASC,
  funding_type (full→0, partial→1, unknown→2),
  amount IS NOT NULL,
  scraped_at DESC
LIMIT 60
```

After SQL: host-country matches are moved to the front of the candidate list before sending to the LLM.

#### LLM hard rules (enforced via system prompt)
1. **Nationality** — student's nationality must appear in `eligible_nationalities` (or list is empty = open to all)
2. **Degree level** — must match `target_level`
3. **Language** — if scholarship is hosted in a non-English country (France, Germany, etc.), student must speak that language unless the programme explicitly teaches in English
4. **Budget** — if student needs full funding, partial-only scholarships are disqualified

#### Response structure
```json
{
  "summary": "Roma is an African student looking for master's-level study in Canada...",
  "matches": [
    {
      "rank": 1,
      "index": 4,
      "reason": "This scholarship is a strong fit because...",
      "highlights": ["Open to all nationalities", "Hosted in Canada", "Master's level"],
      "funding_coverage": "full"
    }
  ]
}
```

`index` (1-based) maps to `candidates[index-1]`. Full scholarship object is attached before returning.

---

### 6. Frontend Layer

**File:** `elite/src/pages/ScholarshipsPage.jsx` — React + Tailwind

Two tabs:

**Browse All** — paginated grid with filters: degree level, host country, source site, keyword search.

**Find My Match** — no form. On tab open:
1. Checks `localStorage` (`sch_match`) for a cached result **synchronously** — if found, renders immediately with no API call and no loading spinner.
2. On cache miss: reads `user_roles` from Supabase (`name`, `degree_level`, `gpa`, `language_score`, `languages`, `budget`, `target_countries`, `application_report`), parses the profile, calls `POST /api/match`, then stores the result in `localStorage`.
3. The active tab (`Browse All` / `Find My Match`) is persisted to `sessionStorage` (`sch_tab`) — page refresh lands back on the same tab.
4. The **Refresh** button in the sidebar clears `localStorage` and forces a fresh Groq analysis.
5. Renders results in a split sidebar + card grid layout:
   - **Left sidebar (sticky)** — profile stat pills (nationality, level, field, languages, budget tier), AI Advisor dark-gradient summary card, funded/partial count breakdown
   - **Match cards (2-col grid)** — ranked 1–10, each with:
     - Funding banner (emerald = Fully Funded, amber = Partial)
     - ★ TOP PICK badge on rank 1
     - "Why this match" in italic quote box
     - Highlights as `✓` chips
     - Deadline with urgency colouring (red < 60 days, amber < 90 days)
     - Inline Apply link

**Caching strategy:**

| Storage | Key | Content | Cleared when |
|---------|-----|---------|--------------|
| `localStorage` | `sch_match` | `{ result, name }` | User clicks Refresh |
| `sessionStorage` | `sch_tab` | `"browse"` / `"match"` | Browser tab closed |

Match state (`matchResult`, `matchLoading`, etc.) is hoisted to the parent `ScholarshipsPage` component so switching between the two tabs never unmounts the result or re-triggers the API.

---

## Find My Match — Full Flow

```
User opens Find My Match tab
    │
    ▼ localStorage check (synchronous)
    ├── "sch_match" key present?
    │       YES → render cached result immediately, no spinner, no API call ──────┐
    │       NO  → proceed to Supabase fetch + Groq call                           │
    │                                                                             │
    ▼ Supabase user_roles read                                                   │
    ├── name            → display name                                           │
    ├── degree_level    → current level → infer target (bachelor→masters, etc.)  │
    ├── languages       → ["English", "French"]  ← language gate for host countries
    ├── budget          → "$5,000" → 5000.0 USD  ← determines funding tier       │
    ├── target_countries → ["Canada"]             ← host-country boost in SQL    │
    ├── gpa             → "3.8"                  ← passed as background context  │
    ├── language_score  → "7.5"                  ← passed as background context  │
    └── application_report.form:                                                 │
            nationality   → "Nigerian"                                            │
            academicGoals → "Public Health"                                       │
    │                                                                             │
    ▼ Budget tier calculation                                                    │
    $0–$2,999  → SQL: only funding_type = 'full'  (can't afford anything less)  │
    $3k–$14,999 → SQL: no funding filter, LLM prompt notes partial is acceptable │
    $15k+      → No filter, full funding is a bonus not a requirement            │
    │                                                                             │
    ▼ SQL pre-filter (matcher.py:get_candidates)                                 │
    60 candidates, filtered by: deadline, degree, nationality, funding need      │
    Host-country matches boosted to front                                         │
    │                                                                             │
    ▼ LLM (Groq llama-3.3-70b, temp 0.2)                                        │
    Hard rules eliminate ineligible scholarships                                  │
    Soft ranking: field relevance → target country → funding quality → deadline  │
    Returns: summary + top 10 with rank, reason, highlights, funding_coverage    │
    │                                                                             │
    ▼ Store to localStorage("sch_match")                                         │
    │                                                                             │
    ▼ ◄────────────────────────────────────────────────────────────────────────┘
    Frontend renders: sticky sidebar (profile chips + AI summary + counts)
                    + 2-col grid of ranked match cards with funding banner + apply link

    [Refresh button] → clears localStorage → re-runs from Supabase fetch
```

---

## Normalised Data Schema

| Field | Type | Description |
|-------|------|-------------|
| `id` | UUID string | `uuid5(source_url)` — stable, deduplicates on re-scrape |
| `title` | string | Scholarship name (HTML entities decoded) |
| `organization` | string? | Awarding institution |
| `description` | string? | Summary (max ~600 chars, HTML stripped) |
| `amount` | string? | `"Fully Funded"`, `"$10,000"`, `"€5,000/year"` |
| `amount_usd` | float? | Normalised USD for sorting |
| `funding_type` | `"full"` / `"partial"` / null | Inferred from amount + description |
| `deadline` | `YYYY-MM-DD`? | Parsed ISO date |
| `deadline_raw` | string? | Original human-readable text |
| `degree_levels` | string[] | `["undergraduate"]`, `["masters","phd"]` |
| `fields_of_study` | string[] | Subject areas |
| `eligible_nationalities` | string[] | `["African"]`, `["Commonwealth citizens"]`, `[]` = open |
| `host_countries` | string[] | Where you study |
| `source_url` | string | Direct link to apply |
| `source_site` | string | Which site it came from |
| `tags` | string[] | Extra labels |
| `scraped_at` | ISO datetime | When fetched |
| `is_open` | bool? | Still accepting applications |

---

## API Reference

```
GET  /api/scholarships          List scholarships (filters + pagination)
GET  /api/scholarships/{id}     Single scholarship detail
GET  /api/stats                 Counts by site, degree, funding, deadline
GET  /api/sites                 Source list with counts
POST /api/scrape                Trigger background scrape (?max_pages=N)
GET  /api/scrape/status         { running: bool }
POST /api/match                 AI match — body: UserProfile JSON
```

**`POST /api/match` body:**
```json
{
  "name": "Roma",
  "nationality": "Nigerian",
  "current_level": "bachelor",
  "target_level": "masters",
  "field": "Public Health",
  "languages": ["English"],
  "budget_usd": 2000,
  "background": "GPA: 3.8, Language score: 7.5",
  "extra": "Preferred countries: Canada, UK"
}
```

**`/api/scholarships` query parameters:**

| Param | Example | Description |
|-------|---------|-------------|
| `search` | `public health` | Full-text on title, description, org |
| `degree_level` | `masters` | Filter by level |
| `source_site` | `Fulbright Program` | Filter by source |
| `eligible_nationality` | `African` | Filter by nationality |
| `host_country` | `UK` | Filter by study location |
| `deadline_after` | `2026-01-01` | On or after |
| `deadline_before` | `2026-12-31` | On or before |
| `has_amount` | `true` | Only with known award value |
| `sort` | `deadline` | `scraped_at`, `deadline`, `title`, `amount_usd` |
| `limit` | `24` | Per page (max 100) |
| `offset` | `0` | Pagination offset |

---

## Quick Start

### 1. Install dependencies

```bash
python3 -m venv venv
venv/bin/pip install -r backend/requirements.txt
venv/bin/pip install -r scrapers/requirements.txt
```

### 2. Set environment variables

```bash
cp .env.example .env
# Add:
#   GROQ_API_KEY=your_groq_key   ← required for Find My Match
```

### 3. Start the backend

```bash
PYTHONPATH=. venv/bin/uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
```

### 4. Run the scrapers

```bash
# Run all 10 scrapers
PYTHONPATH=. venv/bin/python3 -m scrapers.run_all --max-pages 5

# Specific sites only
PYTHONPATH=. venv/bin/python3 -m scrapers.run_all --sites fulbright commonwealth_scholarship

# Check cron log
tail -f scraper_cron.log

# Check DB
sqlite3 backend/scholarships.db "SELECT source_site, COUNT(*) FROM scholarships GROUP BY source_site;"
```

---

## Sources

### Active scrapers (10)

| Site | Method | Focus |
|------|--------|-------|
| Fulbright Program | HTML — real program pages | USA govt scholarships, FLTA, Visiting Scholar |
| Mastercard Foundation Scholars | HTML — main page + known partner universities | Africa — UG/Masters |
| EducationUSA | HTML — finance-your-studies pages + Humphrey Fellowship | USA study funding |
| Chevening | Hardcoded (site times out) | UK govt — Masters |
| Commonwealth Scholarship | HTML — listing page h2 links | UK — Masters / PhD / Fellowships |
| EduCanada | HTML — international listing + known programs | Canada govt scholarships |
| Campus France | HTML — bursaries page + known programs | France — Eiffel, Europa, MOPGA, PHC |
| French Gov Scholarship (BGF) | HTML — AEFE + diplomatie.gouv.fr | France govt — embassy scholarships |
| AfDB Scholarships | Hardcoded (403 blocked) | Africa — JSP, Research Fellowship |
| Mo Ibrahim Foundation | HTML — /fellowships + /scholarships pages | Africa — Leadership, Birmingham, Chatham |

### Why only 10 sources?
These are the 10 most authoritative, well-funded, and internationally recognised scholarship programmes. They produce ~48 high-quality records per scrape cycle — quality over quantity. Generic aggregator sites that scrape the same sources would add duplicates with lower data quality.

---

## Project Structure

```
scraping/
├── .env.example
├── run_scraper_cron.sh             # Cron entry: */15 * * * *
├── scraper_cron.log                # Auto-written cron output
├── README.md
├── backend/
│   ├── main.py                     # FastAPI — all routes
│   ├── database.py                 # SQLite connection + row_to_dict
│   ├── matcher.py                  # AI matching — budget math, SQL filter, Groq call
│   ├── scholarships.db             # Auto-created on first scrape
│   └── requirements.txt
├── scrapers/
│   ├── base.py                     # BaseScraper — session, retry, rate-limit
│   ├── normalizer.py               # make_scholarship() + all normalisation
│   ├── run_all.py                  # ThreadPoolExecutor + INSERT OR REPLACE
│   ├── requirements.txt
│   └── sites/
│       ├── __init__.py             # ALL_SCRAPERS list (10 scrapers)
│       ├── fulbright.py
│       ├── mastercard_foundation.py
│       ├── educationusa.py
│       ├── chevening.py
│       ├── commonwealth_scholarship.py
│       ├── educanada.py
│       ├── campusfrance.py
│       ├── bgf_france.py
│       ├── afdb_scholarships.py
│       └── mo_ibrahim.py
└── elite/                          # React frontend (Vite + Tailwind)
    └── src/
        └── pages/
            └── ScholarshipsPage.jsx  # Browse All + Find My Match tabs
```

---

## Adding a New Scraper

1. Create `scrapers/sites/mysite.py`:

```python
from scrapers.base import BaseScraper
from scrapers.normalizer import make_scholarship, find_deadline_in_text

class MySiteScraper(BaseScraper):
    name = "mysite"
    base_url = "https://mysite.com"

    def scrape(self):
        results = []
        soup = self.get_soup(f"{self.base_url}/scholarships")
        if not soup:
            return results
        for h2 in soup.find_all("h2"):
            a = h2.find("a", href=True)
            if not a:
                continue
            url = a["href"] if a["href"].startswith("http") else self.base_url + a["href"]
            detail = self.get_soup(url)
            text = detail.get_text(" ", strip=True) if detail else ""
            results.append(make_scholarship(
                title=a.get_text(strip=True),
                source_url=url,
                source_site="MySite",
                organization="My Organisation",
                deadline_raw=find_deadline_in_text(text),
                degree_levels_raw="masters phd",
                amount="Fully Funded",
                host_countries=["UK"],
            ))
        return results
```

2. Register in `scrapers/sites/__init__.py`:

```python
from scrapers.sites.mysite import MySiteScraper
ALL_SCRAPERS = [..., MySiteScraper]
```

3. Run it:

```bash
PYTHONPATH=. venv/bin/python3 -m scrapers.run_all --sites mysite
```
