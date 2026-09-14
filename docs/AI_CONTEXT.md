# AI_CONTEXT.md — Current Project State for AI Continuity

> **Last updated:** 2026-09-14T14:00:00+05:30
> **Updated by:** Architecture Phase (Systems Architect)
> **Conversation ID:** 9f4961d1-8769-4ead-95de-c502cba1747d

---

## READ THIS FIRST

Every AI model MUST read this file before changing the project.
Every AI model MUST update this file before finishing its phase.

Read these documents in order:
1. `docs/MASTER_CONTEXT.md` — Immutable project charter
2. `docs/AI_CONTEXT.md` — This file (current state)
3. `docs/PROJECT_SPEC.md` — Architecture and design
4. `docs/DATA_MODEL.md` — Database schema
5. `docs/API_CONTRACT.md` — API specifications
6. `docs/DECISION_LOG.md` — Technology decisions (D001–D012)

---

## Current State: ARCHITECTURE COMPLETE

### What Exists

| Component | Status | Location |
|-----------|--------|----------|
| MASTER_CONTEXT.md | ✅ Complete | `docs/MASTER_CONTEXT.md` |
| PROJECT_SPEC.md | ✅ Complete | `docs/PROJECT_SPEC.md` |
| DATA_MODEL.md | ✅ Complete | `docs/DATA_MODEL.md` |
| API_CONTRACT.md | ✅ Complete | `docs/API_CONTRACT.md` |
| DECISION_LOG.md | ✅ Complete | `docs/DECISION_LOG.md` |
| AI_CONTEXT.md | ✅ Complete | `docs/AI_CONTEXT.md` |
| Source Excel: Locations | ✅ Present | `Geocoded_Ad_Targeting_Locations_FINAL.xlsx` |
| Source Excel: Categories | ✅ Present | `G-Map Scraper Categories.xlsx` |
| Old scraper (reference) | ✅ Present | `Scraped Data/gmap-scraper/` |
| Old n8n workflows (reference) | ✅ Present | `Scraped Data/*.json` |
| Python src/ directory | ❌ Not created | — |
| SQLite database | ❌ Not created | — |
| requirements.txt | ❌ Not created | — |
| .gitignore | ❌ Not created | — |
| n8n workflow | ❌ Not created | — |
| Frontend | ❌ Not created (Phase 4) | — |

### What Does NOT Exist Yet

- No Python source code
- No database
- No FastAPI application
- No Playwright scripts
- No n8n workflow for the new system
- No tests

---

## Environment Snapshot

| Tool | Version | Installed |
|------|---------|-----------|
| Python | 3.12.5 | ✅ |
| Node.js | 20.17.0 | ✅ |
| npm | 11.4.2 | ✅ |
| FastAPI | 0.141.1 | ✅ |
| Pydantic | 2.13.4 | ✅ |
| SQLAlchemy | 2.0.38 | ✅ |
| uvicorn | 0.52.4 | ✅ |
| httpx | 0.28.1 | ✅ |
| openpyxl | 3.1.5 | ✅ |
| Playwright (Python) | — | ❌ Needs `pip install playwright` + `playwright install` |
| PostgreSQL | — | ❌ Not installed, not needed |
| Docker | — | ❌ Not installed, not needed |
| n8n | — | ⚠️ Not verified on PATH (may be running as service) |
| gspread | — | ❌ Not installed, not needed (n8n handles Sheets) |

### Dependencies to Install for Phase 2

```bash
pip install playwright aiosqlite
playwright install chromium
```

---

## Source Data Summary

### Locations (`Geocoded_Ad_Targeting_Locations_FINAL.xlsx`)
- **Sheet:** Sheet1 (logical name: "Geocoded Locations")
- **Columns:** PIN Code (string), Latitude (float), Longitude (float)
- **Rows:** 58 locations
- **Notes:** Some PIN codes are "NOT FOUND" but have valid coordinates
- **No district/state/tehsil columns** — MASTER_CONTEXT model is aspirational

### Categories (`G-Map Scraper Categories.xlsx`)
- **Sheet:** Sheet1 (logical name: "Persona based Categories")
- **Columns:** Categories (string)
- **Rows:** 146 categories
- **Notes:** Single column, no persona grouping. Flat list spanning insurance,
  banking, military, loans, legal, accounting, finance, education, marketing,
  IT services, government, hardware

### Job Matrix
- **58 × 146 = 8,468 jobs**
- **Estimated businesses: 127K–212K records**
- **Estimated scraping time: 70+ hours total (batched over days)**

---

## Key Architecture Decisions (Summary)

| ID | Decision | See |
|----|----------|-----|
| D001 | Playwright (Python) over Puppeteer (Node.js) | DECISION_LOG.md |
| D002 | SQLite over PostgreSQL | DECISION_LOG.md |
| D003 | Modular monolith over microservices | DECISION_LOG.md |
| D004 | n8n for orchestration only (not execution) | DECISION_LOG.md |
| D005 | Coordinate-based search (@lat,lng,zoom) | DECISION_LOG.md |
| D006 | Hash-based deterministic IDs | DECISION_LOG.md |
| D007 | Composite dedup key (name+phone) | DECISION_LOG.md |
| D008 | No LLM in extraction pipeline | DECISION_LOG.md |
| D009 | Google Sheets via n8n only | DECISION_LOG.md |
| D010 | ARIA-based selectors over CSS class selectors | DECISION_LOG.md |
| D011 | Frontend deferred to Phase 4 | DECISION_LOG.md |
| D012 | No stealth/anti-detection in Phase 1 | DECISION_LOG.md |

---

## Old Scraper Reference Notes

The `Scraped Data/gmap-scraper/` directory contains the previous implementation.
Key observations for reuse:

### Reusable Patterns (validated in production)
1. **Scroll-until-stable** — `while sameCount < 5` loop scrolling `div[role="feed"]`
2. **ARIA selectors** — `button[aria-label^="Phone"]`, `button[aria-label*="Address"]`,
   `a[aria-label^="Open website"]` — these work
3. **Per-listing error isolation** — try/catch around each detail page extraction
4. **Search URL format** — `https://www.google.com/maps/search/{query}`

### Anti-Patterns to Avoid
1. **Subprocess execution** — n8n `Execute Command` → `node scraper.js` → parse stdout
2. **Regex parsing of JSON** — `stdout.match(/\[.*\]/s)` in n8n Code node
3. **No deduplication** — 5 identical "Axis Bank ATM" in sample results
4. **No state tracking** — no persistence of what was scraped, no retry, no incremental
5. **Opening new tab per listing** — `browser.newPage()` per detail page is slow;
   consider clicking listing in sidebar instead
6. **Hard-coded paths** — `C:\\Users\\Himanshu\\Desktop\\gmap-scraper\\scraper.js`
7. **No geographic validation** — results may be far outside the 20km radius

### n8n Workflow Patterns (from `G-Map_Scraper EPS.json`)
1. **Google Sheets read** → Loop → Execute Command → Parse → Append to Sheets
2. **Split in batches** — n8n's native batching node
3. **Google Sheets OAuth** — Credential ID `FcG3kpEHdKpSbOyX` exists and works
4. **Output columns:** name, address, phone, website, category, officename, district, statename

---

## Next Recommended Phase: Phase 1 Implementation

### What to Build Next

1. **`requirements.txt`** — Pin all dependencies
2. **`.gitignore`** — Exclude data/, *.db, node_modules/, __pycache__/
3. **`src/config.py`** — Settings via pydantic-settings (.env file)
4. **`src/database.py`** — SQLAlchemy engine + session + Base
5. **`src/models/`** — All 5 ORM models (location, category, job, business, run_log)
6. **`src/schemas/`** — Pydantic request/response schemas
7. **`src/services/config_loader.py`** — Excel → database ingestion
8. **`src/services/job_manager.py`** — Job generation (LOCATION × CATEGORY)
9. **`src/routers/`** — FastAPI endpoints (config, jobs, businesses — stubs for discovery)
10. **`src/main.py`** — FastAPI app with router registration + startup events

### Acceptance Criteria for Phase 1

- [ ] `uvicorn src.main:app --reload` starts without errors
- [ ] `GET /health` returns 200
- [ ] `POST /api/v1/config/sync` loads 58 locations + 146 categories from Excel
- [ ] `POST /api/v1/jobs/generate` creates 8,468 PENDING jobs
- [ ] `GET /api/v1/config/locations` returns paginated locations
- [ ] `GET /api/v1/config/categories` returns paginated categories
- [ ] `GET /api/v1/jobs?status=PENDING` returns paginated jobs
- [ ] `GET /api/v1/stats` returns correct counts
- [ ] SQLite database created at `data/gmaps_discovery.db`
- [ ] Re-running config sync and job generate is idempotent (no duplicates)

### What NOT to Build in Phase 1

- ❌ Playwright discovery engine (Phase 2)
- ❌ Google Sheets export (Phase 3)
- ❌ n8n workflow (Phase 3)
- ❌ Frontend (Phase 4)
- ❌ Authentication (Phase 5)

---

## Document Changelog

| Date | Author | Change |
|------|--------|--------|
| 2026-09-14 | Systems Architect | Initial creation. Architecture phase complete. All 5 docs created. |
