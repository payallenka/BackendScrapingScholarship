# ScholarshipHub

A full-stack scholarship aggregator built for **African students**. Scrapes 22 global scholarship databases, normalises all data into a unified schema, stores it in SQLite, and uses **Groq + Llama 3.3 70B** to generate a personalised top-10 shortlist for each student.

---

## Table of Contents

1. [High-Level Design (HLD)](#high-level-design)
2. [System Flow — end to end](#system-flow)
3. [Low-Level Design (LLD)](#low-level-design)
   - [Scraping Layer](#1-scraping-layer)
   - [Normalisation Layer](#2-normalisation-layer)
   - [Storage Layer](#3-storage-layer)
   - [Backend API Layer](#4-backend-api-layer)
   - [AI Matching & Report Generation](#5-ai-matching--report-generation)
   - [Frontend Layer](#6-frontend-layer)
4. [Groq Matching — how it works](#groq-matching--how-it-works)
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
│  22 site-specific scrapers (WordPress API / HTML / Playwright)       │
└────────────────────────────┬────────────────────────────────────────┘
                             │  List[NormalizedScholarship]
                             ▼
┌─────────────────────────────────────────────────────────────────────┐
│                       NORMALISATION LAYER                            │
│  normalizer.py — unified schema, date parsing, funding inference,    │
│  degree level mapping, eligibility detection, org extraction         │
└────────────────────────────┬────────────────────────────────────────┘
                             │  INSERT OR REPLACE
                             ▼
┌─────────────────────────────────────────────────────────────────────┐
│                        STORAGE LAYER                                 │
│  SQLite  (backend/scholarships.db)                                   │
│  Single table: scholarships — indexed on source_site, deadline,      │
│  scraped_at. Array fields stored as JSON strings.                    │
└────────────────────────────┬────────────────────────────────────────┘
                             │  SELECT / query
                             ▼
┌─────────────────────────────────────────────────────────────────────┐
│                       BACKEND API LAYER                              │
│  FastAPI (backend/main.py) — REST endpoints for browse, filter,      │
│  search, paginate, stats, trigger scrape, and AI match               │
└───────────────┬─────────────────────────────┬───────────────────────┘
                │  /api/* JSON                │  POST /api/match
                ▼                             ▼
┌───────────────────────┐       ┌─────────────────────────────────────┐
│    FRONTEND LAYER     │       │       AI MATCHING LAYER              │
│  Vanilla JS SPA       │       │  matcher.py                          │
│  Browse / filter /    │       │  1. SQL-filter top 100 candidates    │
│  search scholarships  │       │  2. Format into compact prompt       │
│  Match Me form →      │       │  3. POST to Groq API                 │
│  inline results panel │       │     (Llama 3.3 70B, temp 0.2)       │
└───────────────────────┘       │  4. Parse JSON → attach full objects │
                                │  5. Return ranked top-10 + reasons   │
                                └─────────────────────────────────────┘
```

---

## System Flow

### Scraping → Storage

```
run_all.py (CLI or /api/scrape trigger)
    │
    ├── ThreadPoolExecutor (4 workers, parallel)
    │       │
    │       ├── scraper_cls(max_pages=N).run()
    │       │       └── BaseScraper._get(url)       ← rate-limited (1.5s + jitter)
    │       │           ├── Retry adapter (3×, backoff, 429/5xx)
    │       │           ├── get_soup()  → BeautifulSoup (lxml)
    │       │           └── get_json()  → requests.Response.json()
    │       │
    │       └── List[NormalizedScholarship] returned per scraper
    │
    └── upsert_scholarships(conn, results)
            └── INSERT OR REPLACE INTO scholarships (19 columns)
                Array fields serialised: json.dumps(list)
```

### User Match Request → AI Report

```
Browser (Match Me form)
    │  POST /api/match  { name, nationality, target_level, field, ... }
    ▼
FastAPI /api/match endpoint
    │
    ├── matcher.get_candidates(profile, limit=100)
    │       └── SQL: WHERE deadline >= today AND degree_levels LIKE '%"masters"%'
    │           ORDER BY deadline ASC, has_amount, scraped_at DESC
    │           (if < 5 results → broaden to target_level = "any")
    │
    ├── matcher._build_user_msg(profile, candidates)
    │       └── Formats student profile + numbered scholarship list (180-char desc each)
    │
    ├── httpx.AsyncClient.post(GROQ_URL)
    │       model:       llama-3.3-70b-versatile
    │       temperature: 0.2  (low = consistent, factual ranking)
    │       max_tokens:  2500
    │       format:      json_object  (forces valid JSON output)
    │       system:      expert scholarship advisor persona + output schema
    │       user:        student profile + scholarship list
    │
    ├── Parse JSON response → { summary, matches: [{rank, index, reason, highlights}] }
    │
    └── Attach full scholarship object (from candidates[index-1]) to each match
        Return: { summary, matches, profile, total_candidates }
    │
    ▼
Frontend renders results in right panel (no popup)
```

---

## Low-Level Design

### 1. Scraping Layer

**File:** `scrapers/base.py`, `scrapers/sites/*.py`

**Libraries:**
| Library | Purpose |
|---------|---------|
| `requests` | HTTP client for all standard site fetches |
| `requests.adapters.Retry` | Auto-retry on 429, 500, 502, 503, 504 (3 attempts, exponential backoff) |
| `BeautifulSoup` + `lxml` | HTML parsing for sites that serve rendered HTML |
| `Playwright` | Headless browser for JS-heavy sites (e.g. AfterSchoolAfrica) |
| `httpx` | Async HTTP client used by the AI matcher |

**`BaseScraper` mechanics:**
- Every scraper inherits `BaseScraper(max_pages: int)`
- `_get(url)` enforces a **1.5s + random jitter** delay between requests to avoid rate-limiting
- A persistent `requests.Session` with browser-like headers (`User-Agent`, `Accept-Language`) is reused per scraper
- `get_soup(url)` → parses HTML with `lxml` (fastest parser)
- `get_json(url)` → parses JSON API responses

**Scraping strategies used across sites:**
| Strategy | Sites | How |
|----------|-------|-----|
| WordPress REST API | scholars4dev, opportunitiesforafricans, opportunitydesk, youthop, scholarshipregion, opportunitiescorners, globalsouthopportunities | `GET /wp-json/wp/v2/posts?per_page=20&page=N` — structured JSON, no HTML parsing needed |
| HTML scraping | iefa, internationalscholarships, iie, eu_education, stipendiumhungaricum, internationalstudent | `BeautifulSoup` selectors on rendered HTML |
| Playwright | afterschoolafrica | Headless Chromium — waits for JS to render before extracting |

**Parallelism:** `run_all.py` uses `ThreadPoolExecutor(max_workers=4)` — scrapers run concurrently, each saving results as they complete.

---

### 2. Normalisation Layer

**File:** `scrapers/normalizer.py`

**Library:** `python-dateutil` (robust date parsing)

Every scraper calls `make_scholarship(title, source_url, source_site, **kwargs)` which runs the following pipeline:

#### Title cleaning
```
html.unescape(title).strip()
```
Decodes HTML entities (`&amp;` → `&`, `&#8217;` → `'`) that WordPress APIs commonly embed.

#### Organisation extraction
1. Use scraper-supplied value if present and valid
2. Reject if: starts with a digit/roundup word, < 3 chars, or is just the start of the title
3. Fall back to regex on title:
   - Pattern: `"Scholarship at <Org Name>"` → extracts org after `" at "`
   - Pattern: `"DAAD Scholarship"` → extracts leading ACRONYM

#### Funding type inference — 3-pass approach
| Pass | Source | Logic |
|------|--------|-------|
| 1 | `amount` field | Keywords: `"fully funded"`, `"covers all"`, `"tuition and living"` → `"full"`. Keywords: `"partial"`, `"up to"`, `"varies"` → `"partial"`. Currency regex `$10,000` → `"full"` if > $20k, else `"partial"` |
| 2 | Title | Same regex on title text |
| 3 | Description | `infer_funding_from_description()` — same keyword scan on description body |

Currency conversion rates: `€×1.08`, `£×1.27`, `CHF×1.12`, `CAD×0.74`, `AUD×0.65` → all amounts normalised to USD float for sorting.

#### Degree level mapping
Raw text from scraper → keyword scan against `_DEGREE_MAP`:
```python
"masters": ["master's", "masters", " msc", "m.sc", " ma ", " mba", ...]
"phd":     ["ph.d", " phd", "doctorate", "doctoral", "dphil", ...]
```
Roundup posts (`"35+ scholarships for 2026"`) → mapped to `["any"]` to avoid false negatives.

#### Deadline parsing — 4-stage pipeline
1. Strip label prefixes: `"Deadline:"`, `"Apply by:"`, `"Closing date:"` etc.
2. Strip filler: `"is"`, `"are"`, `"falls on"`, `"set for"`
3. Handle ambiguous text: `"coincides with"`, `"varies"` → extract first concrete date via regex
4. `dateutil.parser.parse(text, dayfirst=True)` → ISO `YYYY-MM-DD`; rejected if year < 2020

Fallback regex patterns tried in order:
- `DD Month YYYY` (e.g. `15 May 2026`)
- `Month DD, YYYY` (e.g. `May 15, 2026`)
- `YYYY-MM-DD`
- `DD/MM/YYYY`

#### Eligibility detection
Keyword scan on description + tags:
- `"african students"`, `"for africans"`, `"sub-saharan"` → `["African"]`
- `"developing countries"`, `"lmic"`, `"global south"` → `["Developing Countries"]`

---

### 3. Storage Layer

**File:** `backend/scholarships.db` (SQLite), `scrapers/run_all.py`, `backend/database.py`

**Why SQLite?** Zero-config, single-file, sufficient for 10k–50k scholarship rows with indexed queries.

**Schema:**
```sql
CREATE TABLE scholarships (
    id               TEXT PRIMARY KEY,    -- UUID v4
    title            TEXT NOT NULL,
    organization     TEXT,
    description      TEXT,
    amount           TEXT,                -- display string e.g. "Fully Funded"
    amount_usd       REAL,                -- numeric USD for sorting
    funding_type     TEXT,                -- "full" | "partial" | null
    deadline         TEXT,                -- ISO date YYYY-MM-DD
    deadline_raw     TEXT,                -- original human-readable text
    degree_levels    TEXT,                -- JSON array: ["masters","phd"]
    fields_of_study  TEXT,                -- JSON array
    eligible_nationalities TEXT,          -- JSON array: ["African"]
    host_countries   TEXT,                -- JSON array
    source_url       TEXT NOT NULL,
    source_site      TEXT NOT NULL,
    tags             TEXT,                -- JSON array
    scraped_at       TEXT NOT NULL,       -- ISO datetime
    is_open          INTEGER,             -- 0 | 1 | NULL
    image_url        TEXT
);

CREATE INDEX idx_source_site ON scholarships(source_site);
CREATE INDEX idx_deadline     ON scholarships(deadline);
CREATE INDEX idx_scraped_at   ON scholarships(scraped_at);
```

**Array fields** (degree_levels, eligible_nationalities, etc.) are stored as JSON strings (`json.dumps(list)`) and deserialised back to Python lists by `row_to_dict()` in `database.py` when fetched.

**Upsert strategy:** `INSERT OR REPLACE` on `id` (UUID primary key). Re-running scrapers replaces existing records rather than creating duplicates.

---

### 4. Backend API Layer

**File:** `backend/main.py`

**Library:** `FastAPI` + `uvicorn`

FastAPI serves both the REST API and the static frontend files from the same process.

| Endpoint | Method | What it does |
|----------|--------|--------------|
| `/api/scholarships` | GET | Paginated list with full filter support |
| `/api/scholarships/{id}` | GET | Single record |
| `/api/stats` | GET | Counts by site, degree level, funding type, deadline coverage |
| `/api/sites` | GET | List of sources with scholarship counts |
| `/api/scrape` | POST | Spawns `run_all.py` in a background thread |
| `/api/scrape/status` | GET | Returns `{ running: bool }` |
| `/api/match` | POST | AI-powered matching — see section below |
| `/` | GET | Serves `frontend/index.html` |
| `/static/*` | GET | Serves `frontend/app.js`, `frontend/styles.css` |

**Filtering logic for `/api/scholarships`:**

Dynamic SQL is built from query parameters:
- `search` → `LIKE` on title, description, organization (case-insensitive)
- `degree_level` → `degree_levels LIKE '%"masters"%'`
- `eligible_nationality` → `eligible_nationalities LIKE '%African%'`
- `host_country` → `host_countries LIKE '%Germany%'`
- `deadline_after` / `deadline_before` → range on ISO date field
- `has_amount=true` → `amount IS NOT NULL`

---

### 5. AI Matching & Report Generation

**File:** `backend/matcher.py`

**Library:** `httpx` (async HTTP), `pydantic` (profile validation)

**Model:** `llama-3.3-70b-versatile` via Groq API (OpenAI-compatible endpoint)

#### Step 1 — Candidate filtering (SQL)

```sql
SELECT * FROM scholarships
WHERE (deadline IS NULL OR deadline >= <today>)
  AND (degree_levels LIKE '%"masters"%' OR degree_levels LIKE '%"any"%')
ORDER BY
  CASE WHEN deadline IS NULL THEN 1 ELSE 0 END,
  deadline ASC,
  CASE WHEN amount IS NOT NULL THEN 0 ELSE 1 END,
  scraped_at DESC
LIMIT 100
```

Prioritisation order:
1. Scholarships with known deadlines come before those without
2. Among those with deadlines — soonest first (most urgent / viable)
3. Scholarships with a known award amount ranked higher (better data quality signal)
4. Tie-break: most recently scraped

If fewer than 5 results match the target degree, the filter broadens to `target_level = "any"` to ensure enough candidates are sent to the model.

#### Step 2 — Prompt construction

Each candidate is formatted as:
```
[12] Masters in Public Health at University of Leeds
     Provider: University of Leeds
     Level: masters | Funding: Fully Funded | Eligibility: African
     Deadline: 2026-06-01
     Info: The programme covers tuition, living allowance, and flights for…
```

The student profile is prepended:
```
## Student Profile
Name: Amara
Nationality: Ghanaian
Current education: Bachelor's Degree (completed)
Wants to pursue: masters
Field of study: Public Health
Background: 3.8 GPA, community health worker
Other preferences: Preferred study destination: United Kingdom
```

#### Step 3 — Groq API call

```python
{
  "model": "llama-3.3-70b-versatile",
  "temperature": 0.2,        # low temp = deterministic, factual ranking
  "max_tokens": 2500,
  "response_format": { "type": "json_object" },  # forces valid JSON
  "messages": [
    { "role": "system", "content": SYSTEM_PROMPT },
    { "role": "user",   "content": <profile + scholarship list> }
  ]
}
```

**Temperature 0.2** is deliberately low — we want consistent, reproducible rankings rather than creative variation.

#### Step 4 — Ranking criteria (enforced via system prompt)

The model is instructed to prioritise in this order:
1. **Nationality eligibility** — student must be listed as eligible (African / Developing Countries / Open to All)
2. **Degree level match** — e.g. student wants Masters → must be a Masters scholarship
3. **Field of study relevance** — how closely the scholarship's subject area matches
4. **Funding quality** — Fully Funded > Partial > Unknown
5. **Deadline viability** — open and soon-closing deadlines ranked higher

#### Step 5 — Response structure

Groq returns:
```json
{
  "summary": "Based on Amara's profile as a Ghanaian student...",
  "matches": [
    {
      "rank": 1,
      "index": 12,
      "reason": "This scholarship is a strong fit because...",
      "highlights": ["Fully funded", "Open to African students", "Public Health focus"]
    }
  ]
}
```

`index` (1-based) maps back to the `candidates` list. The full scholarship object from `candidates[index-1]` is attached to each match before returning to the frontend.

---

### 6. Frontend Layer

**File:** `frontend/index.html`, `frontend/app.js`, `frontend/styles.css`

**No framework** — vanilla JS, plain CSS, no build step.

Two tabs:
- **Browse All** — paginated grid of all scholarships with sidebar filters (degree level, source, sort)
- **Match Me** — form collecting student profile, submits to `/api/match`, renders results in sticky right panel

The right panel renders results inline (no popup):
1. Loading spinner shown immediately while Groq call is in-flight
2. On success → sticky header with "↩ New Search" button + scrollable card list
3. On error → reverts to "How it works" panel

---

## Groq Matching — How It Works

```
Student fills form
    ↓
nationality + target_degree + field + background + preferences
    ↓
SQL pre-filter: deadline not expired + degree match → top 100 candidates
    (sorted: soonest deadline → has amount → most recent)
    ↓
Prompt built: student profile header + 100 numbered scholarship entries
    (each entry: title, provider, level, funding, eligibility, deadline, 180-char description)
    ↓
Groq API: llama-3.3-70b-versatile
    system: "expert scholarship advisor — rank by eligibility, level, field, funding, deadline"
    temperature: 0.2 (deterministic)
    response_format: json_object (guaranteed parseable)
    ↓
Model returns: summary paragraph + top 10 ranked matches
    each with: rank, index (pointer to candidate), reason (2-3 sentences), highlights (3 bullets)
    ↓
Backend resolves index → full scholarship object from candidates list
    ↓
Frontend renders ranked cards in right panel
    each card: title, org, funding tag, deadline tag, degree tag, reason text, bullet highlights, apply link
```

---

## Normalised Data Schema

Every scholarship from every source is stored in this unified format:

| Field | Type | Description |
|-------|------|-------------|
| `id` | UUID string | Unique identifier (UUID v4, generated at scrape time) |
| `title` | string | Scholarship name (HTML entities decoded) |
| `organization` | string? | Awarding institution — extracted from `"at [Uni]"` patterns or leading acronyms |
| `description` | string? | Summary (max ~800 chars, HTML stripped) |
| `amount` | string? | Display value: `"Fully Funded"`, `"$10,000"`, `"€5,000 per year"` |
| `amount_usd` | float? | Normalised USD equivalent for sorting (using fixed FX rates) |
| `funding_type` | `"full"` / `"partial"` / null | Inferred from amount + description keywords |
| `deadline` | `YYYY-MM-DD`? | Parsed ISO date |
| `deadline_raw` | string? | Cleaned human-readable deadline text |
| `degree_levels` | string[] | `undergraduate`, `masters`, `phd`, `postdoctoral`, `any` |
| `fields_of_study` | string[] | Subject areas |
| `eligible_nationalities` | string[] | e.g. `["African"]`, `["Developing Countries"]` |
| `host_countries` | string[] | Where you study |
| `source_url` | string | Direct link to apply |
| `source_site` | string | Which site it came from |
| `tags` | string[] | Extra labels from the source |
| `scraped_at` | ISO datetime | When it was fetched |
| `is_open` | bool? | Whether still accepting applications |

---

## API Reference

```
GET  /api/scholarships          List scholarships (filters + pagination)
GET  /api/scholarships/{id}     Single scholarship detail
GET  /api/stats                 Counts by site, degree, funding, deadline coverage
GET  /api/sites                 Source list with counts
POST /api/scrape                Trigger background scrape (?max_pages=N)
GET  /api/scrape/status         { running: bool }
POST /api/match                 AI match — body: UserProfile JSON
```

**`/api/scholarships` query parameters:**

| Param | Example | Description |
|-------|---------|-------------|
| `search` | `public health africa` | Full-text search on title, description, org |
| `degree_level` | `masters` | Filter by level |
| `source_site` | `Scholars4Dev` | Filter by source |
| `eligible_nationality` | `African` | Filter by nationality |
| `host_country` | `Germany` | Filter by study location |
| `deadline_after` | `2026-01-01` | On or after |
| `deadline_before` | `2026-12-31` | On or before |
| `has_amount` | `true` | Only with known award value |
| `sort` | `deadline` | `scraped_at`, `deadline`, `title`, `amount_usd` |
| `order` | `asc` | `asc` or `desc` |
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
# Add to .env:
#   GROQ_API_KEY=your_groq_key      ← required for Match Me
```

Get a free Groq API key at [console.groq.com](https://console.groq.com).

### 3. Start the backend

```bash
PYTHONPATH=. venv/bin/uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
```

Open **http://localhost:8000**

### 4. Run the scrapers

```bash
# Quick (~2 min, ~600 scholarships)
PYTHONPATH=. venv/bin/python3 -m scrapers.run_all --max-pages 2

# Full (~30 min, ~3,000+ scholarships)
PYTHONPATH=. venv/bin/python3 -m scrapers.run_all --max-pages 10

# Specific sites only
PYTHONPATH=. venv/bin/python3 -m scrapers.run_all --sites scholars4dev opportunitiesforafricans

# Or click "Run Scraper" in the top-right of the UI
```

---

## Sources

### Working (14 sources)

| Site | Method | Focus |
|------|--------|-------|
| Scholars4Dev | WordPress REST API | International / Development |
| Opportunities for Africans | WordPress REST API | Africa — UG / Masters / PG |
| Opportunity Desk | WordPress REST API | Global opportunities |
| Opportunities Corners | WordPress REST API | Global |
| Global South Opportunities | WordPress REST API | Global South / Developing |
| YouthOp | WordPress REST API | Postgraduate |
| ScholarshipRegion | WordPress REST API | General |
| After School Africa | Playwright / HTML | Africa |
| EU Education Portal | HTML | Europe / Erasmus |
| IIE | HTML | US govt programs |
| IEFA | HTML | International |
| InternationalScholarships.com | HTML | General |
| InternationalStudent.com | HTML | International students |
| Stipendium Hungaricum | HTML | Hungary govt scholarship |

### Blocked / broken (8 sources)

| Site | Issue |
|------|-------|
| Bold.org | API endpoint changed (404) |
| MastersPortal | 403 — blocks automated access |
| TopUniversities | 403 — blocks automated access |
| ScholarshipTab | 403 — blocks automated access |
| DAAD | JS-rendered — needs Playwright + proxy |
| WeMakeScholars | Selector mismatch — structure changed |
| GoAbroad | Selector mismatch — structure changed |
| British Council India | Connection timeout |

### API (Deprecated)

> [!NOTE]
> We are not using the ScholarshipOwl JSON:API as of now, so related integrations have been removed.

---

## Project Structure

```
scraping/
├── .env.example                    # GROQ_API_KEY
├── backend/
│   ├── main.py                     # FastAPI app — all routes + static serving
│   ├── database.py                 # SQLite connection + row_to_dict (JSON array deserialise)
│   ├── matcher.py                  # Groq AI matching — candidate fetch + prompt + call
│   ├── scholarships.db             # Auto-created on first scrape
│   └── requirements.txt            # fastapi, uvicorn, httpx, pydantic, python-dotenv
├── scrapers/
│   ├── base.py                     # BaseScraper — session, retry, rate-limit, get_soup/get_json
│   ├── normalizer.py               # make_scholarship() + all normalisation helpers
│   ├── run_all.py                  # CLI runner — ThreadPoolExecutor + SQLite upsert
│   ├── requirements.txt            # requests, beautifulsoup4, lxml, playwright, python-dateutil
│   └── sites/
│       ├── __init__.py             # ALL_SCRAPERS list
│       ├── scholars4dev.py
│       ├── opportunitiesforafricans.py
│       ├── opportunitydesk.py
│       └── ... (18 more)
└── frontend/
    ├── index.html                  # SPA shell — Browse + Match Me tabs
    ├── app.js                      # All UI logic — fetch, render, filter, AI report panel
    └── styles.css                  # Dark theme, responsive grid, sticky result panel
```

---

## Adding a New Scraper

1. Create `scrapers/sites/mysite.py`:

```python
from scrapers.base import BaseScraper
from scrapers.normalizer import make_scholarship

class MySiteScraper(BaseScraper):
    name = "mysite"
    base_url = "https://mysite.com"

    def scrape(self):
        results = []
        for page in range(1, self.max_pages + 1):
            soup = self.get_soup(f"{self.base_url}/scholarships?page={page}")
            if not soup:
                break
            for item in soup.select(".scholarship-card"):
                results.append(make_scholarship(
                    title=item.select_one("h2").text,
                    source_url=item.select_one("a")["href"],
                    source_site="MySite",
                    deadline_raw=item.select_one(".deadline").text,
                    amount=item.select_one(".award").text,
                    degree_levels_raw=item.select_one(".level").text,
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
