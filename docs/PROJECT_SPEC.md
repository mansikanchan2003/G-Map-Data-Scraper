# PROJECT_SPEC.md — Autonomous Google Maps Business Discovery Agent

> Version: 1.0.0 | Created: 2026-09-14 | Status: Architecture Complete

---

## 1. Business Purpose

Discover franchise-oriented and small-business leads for configured personas/categories
around configured target pin-code locations using Google Maps.

The system ingests two static Excel configuration files (never modified at runtime),
generates a LOCATION × CATEGORY job matrix (~8,468 jobs for current config),
discovers businesses via browser automation, extracts/validates/deduplicates them,
persists results, and exports to Google Sheets — all running autonomously on a daily schedule.

---

## 2. Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                        n8n (Orchestration)                          │
│  ┌─────────┐   ┌──────────┐   ┌──────────┐   ┌────────────────┐   │
│  │ Schedule │──▶│ Trigger  │──▶│ Batch    │──▶│ Google Sheets  │   │
│  │ (Cron)  │   │ FastAPI  │   │ Monitor  │   │ Export         │   │
│  └─────────┘   └──────────┘   └──────────┘   └────────────────┘   │
└──────────────────────┬──────────────────────────────────────────────┘
                       │ HTTP
┌──────────────────────▼──────────────────────────────────────────────┐
│                    FastAPI Backend (Python)                          │
│                                                                     │
│  ┌──────────────┐  ┌───────────────┐  ┌────────────────────────┐   │
│  │ Config       │  │ Job           │  │ Discovery              │   │
│  │ Loader       │  │ Manager       │  │ Engine                 │   │
│  │ (Excel→DB)  │  │ (CRUD/State)  │  │ (Playwright)           │   │
│  └──────┬───────┘  └───────┬───────┘  └────────┬───────────────┘   │
│         │                  │                    │                    │
│  ┌──────▼──────────────────▼────────────────────▼───────────────┐   │
│  │                   Service Layer                               │   │
│  │  ┌────────────┐ ┌──────────┐ ┌──────────┐ ┌──────────────┐  │   │
│  │  │ Validation │ │ Dedup    │ │ Geo      │ │ Normalizer   │  │   │
│  │  └────────────┘ └──────────┘ └──────────┘ └──────────────┘  │   │
│  └──────────────────────┬───────────────────────────────────────┘   │
│                         │                                           │
│  ┌──────────────────────▼───────────────────────────────────────┐   │
│  │              SQLite (via SQLAlchemy)                           │   │
│  │  locations │ categories │ jobs │ businesses │ run_log          │   │
│  └──────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────┘
```

### Architectural Style

**Modular monolith.** A single FastAPI process handles all concerns — config loading,
job management, discovery, persistence. No microservices, no message queues,
no AI-agent framework. n8n acts as the external scheduler/orchestrator only.

---

## 3. Data Flow

```
Excel Files (static config)
    │
    ▼
Config Loader ──▶ locations table + categories table
    │
    ▼
Job Generator ──▶ jobs table (LOCATION × CATEGORY cross product)
    │                  │
    │          ┌───────┘ (only PENDING / RETRY jobs)
    │          ▼
    │    Discovery Engine (Playwright)
    │          │
    │          ▼ raw listings
    │    Normalizer ──▶ cleaned fields
    │          │
    │          ▼
    │    Geo Validator ──▶ haversine distance check (≤ 20km)
    │          │
    │          ▼
    │    Deduplicator ──▶ phone+name composite key
    │          │
    │          ▼
    │    Persistence ──▶ businesses table
    │          │
    │          ▼
    │    Job State Update ──▶ COMPLETED / FAILED / PARTIAL
    │
    ▼
API Endpoints ──▶ Paginated queries (100/page default)
    │
    ▼
n8n ──▶ Google Sheets Export (batched append via Sheets API)
    │
    ▼ (future)
Frontend (React/TypeScript)
```

---

## 4. Source Configuration Analysis

### Locations File: `Geocoded_Ad_Targeting_Locations_FINAL.xlsx`

| Column    | Type    | Example         | Notes                        |
|-----------|---------|-----------------|------------------------------|
| PIN Code  | string  | `244221`        | May be `NOT FOUND`           |
| Latitude  | float   | `28.8922129`    | Geocoded coordinates         |
| Longitude | float   | `78.4744272`    | Geocoded coordinates         |

- **58 rows** (excluding header)
- Sheet name: `Sheet1` (MASTER_CONTEXT says "Geocoded Locations" — that is the logical name)
- Some PIN codes are `NOT FOUND` — these rows still have valid lat/long and must be processed
- No district/state/tehsil columns exist in this file — the MASTER_CONTEXT location model
  fields (district, state, tehsil, anchor_village_town) are aspirational enrichments

**Decision:** Load all 58 rows. Use lat/long as the primary geographic anchor.
PIN code is metadata only. District/state can be reverse-geocoded later or left null initially.

### Categories File: `G-Map Scraper Categories.xlsx`

| Column     | Type   | Example                     |
|------------|--------|-----------------------------|
| Categories | string | `Auto insurance agency`     |

- **146 rows** (excluding header)
- Sheet name: `Sheet1` (logical name: "Persona based Categories")
- Single column, no persona grouping in the file itself
- Categories span: insurance, banking, military, loans, legal, accounting, finance,
  education, marketing, IT services, government, hardware

**Decision:** Each row is one category. Persona grouping is not in the source file;
it can be added later as a separate enrichment table. For now, category is a flat list.

### Job Matrix

- **58 locations × 146 categories = 8,468 jobs**
- At ~15-25 listings per job: **~127K–212K business records** potential
- Processing all jobs at ~30 seconds each: **~70 hours of scraping time**
- This confirms the need for incremental processing, daily batching, and state tracking

---

## 5. Technology Decisions

### 5.1 Playwright vs Puppeteer

| Criterion                  | Puppeteer (Node.js)          | Playwright (Python)           | Decision     |
|----------------------------|------------------------------|-------------------------------|--------------|
| Language alignment         | JavaScript only              | Python (matches FastAPI)      | **Playwright** |
| API maturity               | Mature, Google-backed        | Mature, Microsoft-backed      | Tie          |
| Auto-wait                  | Manual waits needed          | Built-in auto-wait            | **Playwright** |
| Selector engine            | CSS only                     | CSS, text, role, xpath        | **Playwright** |
| Browser contexts           | Basic                        | Isolated browser contexts     | **Playwright** |
| Stealth                    | Requires puppeteer-extra      | playwright-stealth available  | Tie          |
| Existing code              | Old scraper uses Puppeteer   | N/A                           | Puppeteer    |
| Process model              | Same process                 | Same process (Python)         | **Playwright** |

**Decision: Playwright (Python).** Eliminates the Node.js subprocess spawning pattern
visible in the old n8n workflow. The entire backend is one Python process. Auto-wait
reduces flaky timing issues seen in the old scraper (`setTimeout(resolve, 3000)`).

The old Puppeteer scraper's patterns (scroll-until-stable, detail page extraction,
error isolation per listing) are valid and will be reimplemented in Playwright.

### 5.2 PostgreSQL vs SQLite

| Criterion                    | PostgreSQL                   | SQLite                        | Decision    |
|------------------------------|------------------------------|-------------------------------|-------------|
| Scale needed                 | Millions of rows             | ~200K rows max                | SQLite      |
| Concurrent writers           | Yes                          | WAL mode adequate             | SQLite      |
| Operational complexity       | Requires server, backups     | Single file, zero config      | **SQLite**  |
| Deployment                   | Docker/install required      | Built into Python             | **SQLite**  |
| Full-text search             | pg_trgm                      | FTS5                          | Tie         |
| JSON support                 | jsonb                        | json1 extension               | Tie         |
| Migration path               | N/A                          | SQLAlchemy makes switch easy  | N/A         |
| Current environment          | Not installed                | Available                     | **SQLite**  |

**Decision: SQLite with WAL mode.** The dataset is ~200K rows maximum.
There is exactly one writer (the FastAPI process). SQLAlchemy abstracts the database
engine, making a future PostgreSQL migration trivial if scale demands it.

### 5.3 Python / FastAPI

**Confirmed.** Already installed (FastAPI 0.141.1, Pydantic 2.13.4, SQLAlchemy 2.0.38,
uvicorn 0.52.4). The entire backend is Python. No justification for Node.js.

### 5.4 n8n

**Confirmed for orchestration only.** The existing n8n instance has proven Google Sheets
integration (OAuth2 credentials already configured). n8n will:

1. **Schedule** daily runs via Cron trigger
2. **Trigger** FastAPI batch endpoints via HTTP
3. **Export** results to Google Sheets via native Google Sheets node
4. **Monitor** run summaries and send alerts

n8n will NOT:
- Execute scraping directly (no more `Execute Command` → `node scraper.js`)
- Parse scraper output (no more regex extraction from stdout)
- Manage job state (FastAPI owns this)

### 5.5 React / TypeScript Frontend

**Deferred.** Not built in this phase. The architecture reserves a frontend layer that
will consume the paginated FastAPI endpoints. When built, it will be React/TypeScript
generated via Stitch and refined via Google AI Studio per MASTER_CONTEXT.

### 5.6 Google Sheets Integration

**Via n8n.** The existing n8n instance already has `googleSheetsOAuth2Api` credentials
configured (credential IDs: `FcG3kpEHdKpSbOyX`, `GYyysi4hZsQQRkJq`). The export path is:

```
FastAPI /api/v1/export/businesses → JSON response
    → n8n Google Sheets node → Append rows (batched)
```

No Google API credentials in the Python backend. No `gspread`. No service account keys
on disk. The n8n credential vault handles all Google auth.

---

## 6. Security Model

### 6.1 Ethical Scraping

- Scrape only publicly visible Google Maps listings
- No CAPTCHA bypass, no login bypass, no anti-bot circumvention
- Detect blocking/CAPTCHA and fail gracefully (mark job as BLOCKED)
- Respect rate limits with configurable delays between requests
- Use standard browser fingerprint (no stealth plugins in Phase 1)

### 6.2 Credential Security

- Google OAuth tokens stored in n8n credential vault only
- No API keys in source code, config files, or environment variables
- SQLite database file excluded from git via `.gitignore`
- No secrets in the FastAPI process — it only serves data

### 6.3 Data Security

- No personal/private data collected (only public business listings)
- Phone numbers and emails are public business contact info
- No user authentication on FastAPI in Phase 1 (localhost only)
- API key auth header added in Phase 2 when exposed to n8n

---

## 7. Folder Structure

```
G-Map_Data_Scraper_2.0/
├── docs/                          # Architecture documentation (source of truth)
│   ├── MASTER_CONTEXT.md          # Immutable project charter
│   ├── PROJECT_SPEC.md            # This file
│   ├── DATA_MODEL.md              # Database schema and models
│   ├── API_CONTRACT.md            # FastAPI endpoint specifications
│   ├── AI_CONTEXT.md              # Current state for AI continuity
│   └── DECISION_LOG.md            # Technology and design decisions
│
├── src/                           # Production source code
│   ├── __init__.py
│   ├── main.py                    # FastAPI application entry point
│   ├── config.py                  # Settings, paths, constants
│   ├── database.py                # SQLAlchemy engine, session, Base
│   │
│   ├── models/                    # SQLAlchemy ORM models
│   │   ├── __init__.py
│   │   ├── location.py
│   │   ├── category.py
│   │   ├── job.py
│   │   ├── business.py
│   │   └── run_log.py
│   │
│   ├── schemas/                   # Pydantic request/response schemas
│   │   ├── __init__.py
│   │   ├── location.py
│   │   ├── category.py
│   │   ├── job.py
│   │   ├── business.py
│   │   └── common.py              # Pagination, error responses
│   │
│   ├── routers/                   # FastAPI route handlers
│   │   ├── __init__.py
│   │   ├── config.py              # /api/v1/config/* endpoints
│   │   ├── jobs.py                # /api/v1/jobs/* endpoints
│   │   ├── businesses.py          # /api/v1/businesses/* endpoints
│   │   ├── discovery.py           # /api/v1/discovery/* endpoints
│   │   └── export.py              # /api/v1/export/* endpoints
│   │
│   ├── services/                  # Business logic layer
│   │   ├── __init__.py
│   │   ├── config_loader.py       # Excel → database ingestion
│   │   ├── job_manager.py         # Job generation, state transitions
│   │   ├── discovery_engine.py    # Playwright Google Maps scraping
│   │   ├── normalizer.py          # Field cleaning and normalization
│   │   ├── geo_validator.py       # Haversine distance validation
│   │   ├── deduplicator.py        # Phone+name composite dedup
│   │   └── export_service.py      # Batch export formatting
│   │
│   └── utils/                     # Shared utilities
│       ├── __init__.py
│       └── logging.py             # Structured logging setup
│
├── data/                          # Runtime data (gitignored)
│   └── gmaps_discovery.db         # SQLite database file
│
├── n8n/                           # n8n workflow exports (version controlled)
│   └── daily_discovery.json       # Main orchestration workflow
│
├── Scraped Data/                  # REFERENCE ONLY — old scraper artifacts
│
├── Geocoded_Ad_Targeting_Locations_FINAL.xlsx   # Source config (read-only)
├── G-Map Scraper Categories.xlsx                # Source config (read-only)
├── requirements.txt               # Python dependencies
├── .env.example                   # Environment variable template
└── .gitignore
```

---

## 8. Autonomous Execution Model

### 8.1 Daily Run Lifecycle

```
n8n Cron (daily, e.g., 02:00 AM)
    │
    ├── POST /api/v1/config/sync          ← Reload Excel if changed
    │
    ├── POST /api/v1/jobs/generate         ← Generate missing jobs
    │
    ├── POST /api/v1/discovery/batch       ← Process N pending jobs
    │       │                                  (configurable batch size)
    │       ├── For each job:
    │       │   ├── Build search query
    │       │   ├── Navigate Google Maps
    │       │   ├── Scroll to load all listings
    │       │   ├── Extract basic info (name, URL)
    │       │   ├── Visit each listing detail page
    │       │   ├── Extract phone, address, website
    │       │   ├── Normalize fields
    │       │   ├── Validate geo distance
    │       │   ├── Deduplicate
    │       │   ├── Persist to businesses table
    │       │   └── Update job status
    │       │
    │       └── Return batch summary
    │
    ├── GET /api/v1/export/businesses      ← Fetch new businesses since last export
    │       └── n8n Google Sheets node → Append to spreadsheet
    │
    └── Log run summary
```

### 8.2 Job State Machine

```
PENDING ──▶ RUNNING ──▶ COMPLETED
    │           │              │
    │           ├──▶ PARTIAL   │ (some listings failed)
    │           │              │
    │           ├──▶ FAILED    │ (job-level failure)
    │           │              │
    │           └──▶ BLOCKED   │ (CAPTCHA/rate-limit detected)
    │                          │
    └──────────────────────────┘
         (retry logic returns
          FAILED/PARTIAL → PENDING
          after cooldown)
```

### 8.3 Incremental Processing Rules

1. **Jobs are never re-created** if they already exist for a location+category pair
2. **COMPLETED jobs are skipped** during batch processing
3. **FAILED jobs retry** up to `MAX_RETRIES` (default: 3) with exponential backoff
4. **PARTIAL jobs** can be retried to discover remaining listings
5. **New locations or categories** added to Excel automatically generate new PENDING jobs
6. **Businesses are deduplicated** by phone+name composite key — existing records are updated, not duplicated

### 8.4 Fault Isolation

- One failed listing extraction does NOT fail the job
- One failed job does NOT fail the batch
- Browser crash restarts Playwright for next job
- Network timeout marks the job FAILED for retry
- CAPTCHA detection marks the job BLOCKED (requires manual review)

---

## 9. Development Phases

### Phase 1: Foundation (Current)
- [x] Architecture documentation
- [ ] SQLAlchemy models + database initialization
- [ ] Config loader (Excel → database)
- [ ] Job generator (LOCATION × CATEGORY)
- [ ] FastAPI skeleton with health check
- [ ] Basic CRUD endpoints (locations, categories, jobs)

### Phase 2: Discovery Engine
- [ ] Playwright-based Google Maps scraper
- [ ] Scroll-to-load-all pattern
- [ ] Detail page extraction (phone, address, website)
- [ ] Normalizer service
- [ ] Geo validator (haversine)
- [ ] Deduplicator service
- [ ] Job state machine transitions
- [ ] Batch processing endpoint

### Phase 3: Orchestration & Export
- [ ] n8n daily workflow
- [ ] Google Sheets export via n8n
- [ ] Run logging and summaries
- [ ] Retry/recovery logic
- [ ] Monitoring endpoints

### Phase 4: Frontend
- [ ] React/TypeScript SPA
- [ ] Server-side paginated data table
- [ ] Export button (triggers n8n)
- [ ] Job monitoring dashboard
- [ ] Filter/search UI

### Phase 5: Hardening
- [ ] API key authentication
- [ ] Rate limiting
- [ ] Structured logging + log rotation
- [ ] Error alerting (n8n → email/Slack)
- [ ] Database backup automation

---

## 10. Risks

| Risk | Severity | Mitigation |
|------|----------|------------|
| Google Maps DOM changes break selectors | High | Use ARIA selectors (`button[aria-label^="Phone"]`), selector versioning, failure detection |
| CAPTCHA/blocking at scale | High | Rate limiting, human-like delays, graceful BLOCKED state, manual review |
| 8,468 jobs × 30s = 70+ hours of scraping | Medium | Daily batching (N jobs/day), parallel browser contexts (Phase 2) |
| SQLite write contention under load | Low | WAL mode, single writer, migrate to PostgreSQL if needed |
| n8n instance unavailability | Medium | FastAPI can run independently, n8n is orchestration only |
| Excel source files moved/renamed | Low | Configurable paths via `.env`, startup validation |
| Stale business data over time | Medium | Re-scrape COMPLETED jobs on configurable refresh cycle |

---

## 11. What Should NOT Be Implemented Yet

1. **Frontend (React/TypeScript)** — Phase 4
2. **PostgreSQL** — SQLite is sufficient for ~200K rows
3. **Message queues (Redis, RabbitMQ)** — Single-process architecture
4. **Microservices** — Modular monolith is correct for this scale
5. **AI-agent framework** — Autonomy comes from state machines and rules
6. **LLM integration** — No NLP needed for structured data extraction
7. **Docker containerization** — Running locally on Windows
8. **Parallel browser instances** — Sequential processing first, optimize later
9. **User authentication** — localhost-only access in Phase 1-2
10. **Reverse geocoding** — District/state enrichment deferred
11. **puppeteer-extra-plugin-stealth equivalent** — Standard browser first
12. **Email notifications** — n8n can handle this in Phase 3
13. **Data archival/retention policies** — Premature at this stage
