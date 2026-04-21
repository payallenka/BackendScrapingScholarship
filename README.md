# ScholarshipHub

A full-stack scholarship aggregator that scrapes 22 global scholarship databases, normalizes all data into a unified schema, and serves it through a searchable frontend.

---

## How it works

```
22 scrapers  →  SQLite DB  →  FastAPI backend  →  Frontend UI
```

1. **Scrapers** (`scrapers/`) fetch scholarship listings from each source site using either the site's WordPress REST API, a JSON API, or HTML parsing with BeautifulSoup. JS-heavy sites use Playwright.
2. **Normalizer** (`scrapers/normalizer.py`) cleans and standardizes every record into a common schema — decoding HTML entities, parsing dates, inferring funding type, extracting organization names, and detecting eligibility.
3. **Backend** (`backend/main.py`) is a FastAPI app that queries the SQLite database and exposes REST endpoints with filtering, search, sorting, and pagination.
4. **Frontend** (`frontend/`) is a vanilla JS single-page app served directly by the FastAPI backend. Cards show the six key fields: title, organization, level, funding, eligibility, and deadline.
5. **ScholarshipOwl API** (`scrapers/owl_api.py`) fetches structured scholarship data from the ScholarshipOwl business API when an API key is provided.

---

## Quick start

### 1. Create virtual environment and install dependencies

```bash
cd /home/zbook/Desktop/practice/scraping
python3 -m venv venv
venv/bin/pip install -r backend/requirements.txt
venv/bin/pip install -r scrapers/requirements.txt
```

### 2. Start the backend server

```bash
PYTHONPATH=. venv/bin/uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
```

Or use the convenience script:

```bash
./start.sh
```

The app is now available at **http://localhost:8000**

| URL | Purpose |
|-----|---------|
| http://localhost:8000 | Frontend UI |
| http://localhost:8000/docs | Interactive API docs (Swagger) |
| http://localhost:8000/api/scholarships | Scholarship list endpoint |
| http://localhost:8000/api/stats | Aggregate statistics |

### 3. Run the scrapers

In a second terminal:

```bash
# Quick scrape — 2 pages per site (~1–2 min, ~600 scholarships)
PYTHONPATH=. venv/bin/python3 -m scrapers.run_all --max-pages 2

# Full scrape — 10 pages per site (~15–30 min, ~3,000+ scholarships)
PYTHONPATH=. venv/bin/python3 -m scrapers.run_all --max-pages 10

# Scrape specific sites only
PYTHONPATH=. venv/bin/python3 -m scrapers.run_all --sites scholars4dev opportunitydesk

# Include ScholarshipOwl API (requires API key in .env)
PYTHONPATH=. venv/bin/python3 -m scrapers.run_all --max-pages 10 --owl

# Trigger scrape from the UI without a terminal
# Click "Run Scraper" button in the top-right of the frontend
```

### 4. (Optional) ScholarshipOwl API

Copy `.env.example` to `.env` and add your API key:

```bash
cp .env.example .env
# Edit .env and set:  OWL_API_KEY=your_key_here
```

---

## Sites being scraped

### ✅ Working (14 sources)

| Site | URL | Method | Focus |
|------|-----|--------|-------|
| **Scholars4Dev** | scholars4dev.com | WordPress REST API | International / Development |
| **Opportunities for Africans** | opportunitiesforafricans.com | WordPress REST API | Africa — UG / Masters / PG |
| **Opportunity Desk** | opportunitydesk.org | WordPress REST API | Global opportunities |
| **Opportunities Corners** | opportunitiescorners.com | WordPress REST API | Global |
| **Global South Opportunities** | globalsouthopportunities.com | WordPress REST API | Global South / Developing |
| **YouthOp** | youthop.com | WordPress REST API | Postgraduate |
| **ScholarshipRegion** | scholarshipregion.com/getfund-scholarship | WordPress REST API | General |
| **After School Africa** | afterschoolafrica.com | Playwright / HTML | Africa |
| **EU Education Portal** | education.ec.europa.eu | HTML | Europe / Erasmus |
| **IIE** | iie.org | HTML | US govt programs |
| **IEFA** | iefa.org | HTML | International |
| **InternationalScholarships.com** | internationalscholarships.com | HTML | General |
| **InternationalStudent.com** | internationalstudent.com | HTML | International students |
| **Stipendium Hungaricum** | stipendiumhungaricum.hu | HTML | Hungary govt scholarship |

### ⚠️ Blocked by anti-bot measures (8 sources)

These sites return 403 Forbidden, require JavaScript rendering with a proxy, or have API URLs that changed. Scrapers are implemented but return 0 results in standard mode.

| Site | URL | Issue |
|------|-----|-------|
| **Bold.org** | bold.org | API endpoint changed (404); needs Playwright |
| **MastersPortal** | mastersportal.com | 403 — blocks automated access |
| **TopUniversities** | topuniversities.com | 403 — blocks automated access |
| **ScholarshipTab** | scholarshiptab.com | 403 — blocks automated access |
| **DAAD** | daad.de | JS-rendered — needs Playwright with proxy |
| **WeMakeScholars** | wemakescholars.com | Selector mismatch — structure changed |
| **GoAbroad** | goabroad.com | Selector mismatch — structure changed |
| **British Council India** | britishcouncil.in | Connection timeout |

### 🔑 API integration

| Source | Notes |
|--------|-------|
| **ScholarshipOwl** | Business API — requires `OWL_API_KEY` in `.env`. Endpoint: `GET /api/scholarship`. Full JSON:API response with award amount, deadline, requirements. |

---

## Normalized data schema

Every scholarship from every source is stored in this unified format:

| Field | Type | Description |
|-------|------|-------------|
| `id` | UUID | Unique identifier |
| `title` | string | Scholarship name (HTML entities decoded) |
| `organization` | string? | Awarding institution (extracted from "at [Uni]" patterns or acronyms) |
| `description` | string? | Summary text (max 800 chars) |
| `amount` | string? | Award value e.g. `"$10,000"`, `"Fully Funded"` |
| `amount_usd` | float? | USD numeric equivalent for sorting |
| `funding_type` | `"full"` / `"partial"` / null | Inferred from amount + description keywords |
| `deadline` | `YYYY-MM-DD`? | Parsed ISO date |
| `deadline_raw` | string? | Human-readable deadline text (cleaned) |
| `degree_levels` | string[] | `undergraduate`, `masters`, `phd`, `postdoctoral`, `any` |
| `fields_of_study` | string[] | Subject areas |
| `eligible_nationalities` | string[] | e.g. `["African"]`, `["Developing Countries"]` |
| `host_countries` | string[] | Where you study |
| `source_url` | string | Direct link to the scholarship |
| `source_site` | string | Which site it came from |
| `tags` | string[] | Extra labels |
| `scraped_at` | ISO datetime | When it was fetched |
| `is_open` | bool? | Whether still accepting applications |

---

## API endpoints

```
GET  /api/scholarships          List scholarships (filters + pagination)
GET  /api/scholarships/{id}     Single scholarship detail
GET  /api/stats                 Totals by site, degree level, etc.
GET  /api/sites                 List of sources with counts
POST /api/scrape                Trigger background scrape
GET  /api/scrape/status         Check if scrape is running
```

**Query parameters for `/api/scholarships`:**

| Param | Example | Description |
|-------|---------|-------------|
| `search` | `africa masters` | Full-text search on title, description, org |
| `degree_level` | `masters` | Filter by level |
| `source_site` | `Scholars4Dev` | Filter by source |
| `eligible_nationality` | `African` | Filter by nationality |
| `host_country` | `Germany` | Filter by study location |
| `deadline_after` | `2026-01-01` | Deadlines on or after this date |
| `deadline_before` | `2026-12-31` | Deadlines on or before this date |
| `has_amount` | `true` | Only show scholarships with a known award value |
| `sort` | `deadline` | Sort by: `scraped_at`, `deadline`, `title`, `amount_usd` |
| `order` | `asc` | `asc` or `desc` |
| `limit` | `24` | Results per page (max 100) |
| `offset` | `0` | Pagination offset |

---

## Project structure

```
scraping/
├── start.sh                    # One-command startup script
├── .env.example                # Environment variable template
├── scrapers/
│   ├── base.py                 # Base scraper (session, retry, rate-limit)
│   ├── normalizer.py           # Unified schema + all normalization logic
│   ├── owl_api.py              # ScholarshipOwl API client
│   ├── run_all.py              # CLI runner — runs all scrapers, saves to DB
│   ├── requirements.txt
│   └── sites/
│       ├── scholars4dev.py
│       ├── opportunitiesforafricans.py
│       ├── opportunitydesk.py
│       ├── afterschoolafrica.py
│       ├── bold_org.py
│       ├── mastersportal.py
│       ├── internationalscholarships.py
│       ├── iefa.py
│       ├── wemakescholars.py
│       ├── goabroad.py
│       ├── youthop.py
│       ├── topuniversities.py
│       ├── scholarshiptab.py
│       ├── scholarshipregion.py
│       ├── scholars4dev_extra.py   # globalsouthopportunities.com
│       ├── daad.py
│       ├── iie.py
│       ├── internationalstudent.py
│       ├── opportunitiescorners.py
│       ├── britishcouncil.py
│       ├── eu_education.py
│       └── stipendiumhungaricum.py
├── backend/
│   ├── main.py                 # FastAPI app + all API routes
│   ├── database.py             # SQLite connection + row deserializer
│   ├── scholarships.db         # Generated — created on first run
│   └── requirements.txt
└── frontend/
    ├── index.html              # Single-page app shell
    ├── app.js                  # All UI logic (fetch, render, filter, modal)
    └── styles.css              # Dark theme, responsive grid
```

---

## Adding a new scraper

1. Create `scrapers/sites/mysite.py` extending `BaseScraper`:

```python
from scrapers.base import BaseScraper
from scrapers.normalizer import make_scholarship

class MySiteScraper(BaseScraper):
    name = "mysite"
    base_url = "https://mysite.com"

    def scrape(self):
        soup = self.get_soup("https://mysite.com/scholarships")
        results = []
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

2. Register it in `scrapers/sites/__init__.py`:

```python
from scrapers.sites.mysite import MySiteScraper
ALL_SCRAPERS = [..., MySiteScraper]
```

3. Run it:

```bash
PYTHONPATH=. venv/bin/python3 -m scrapers.run_all --sites mysite
```
