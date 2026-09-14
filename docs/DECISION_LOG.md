# DECISION_LOG.md — Technology and Design Decision Record

> Version: 1.0.0 | Created: 2026-09-14

Every significant decision is recorded here with context, alternatives considered,
and rationale. Decisions are numbered and immutable once accepted.

---

## D001: Playwright over Puppeteer

**Date:** 2026-09-14
**Status:** Accepted
**Context:** The old scraper uses Puppeteer (Node.js) invoked from n8n via `Execute Command`.
This creates a cross-language boundary (Python FastAPI ↔ Node.js subprocess), requires
parsing JSON from stdout via regex, and offers no error propagation.

**Alternatives:**
1. **Puppeteer (Node.js)** — Proven in the old scraper, but requires a separate Node runtime
   and subprocess management
2. **Playwright (Python)** — Same process as FastAPI, native async, auto-wait, richer selectors
3. **Selenium (Python)** — Older API, no auto-wait, heavier

**Decision:** Playwright (Python)

**Rationale:**
- Single-language backend (Python everywhere)
- No subprocess spawning, no stdout parsing, no cross-process error handling
- Auto-wait eliminates the `setTimeout(resolve, 3000)` pattern from the old scraper
- `aria-label` selectors (which the old scraper already uses for phones/addresses) work natively
- Browser context isolation allows future parallel execution
- The old scraper's successful patterns (scroll-until-stable, per-listing error isolation)
  are easily reimplemented

**Risks:** Team has existing Puppeteer experience. Playwright Python has a slightly different API.
Mitigated by Playwright's excellent documentation and similar conceptual model.

---

## D002: SQLite over PostgreSQL

**Date:** 2026-09-14
**Status:** Accepted
**Context:** The system needs persistent storage for ~200K business records, 8.5K jobs,
and 200 config rows. The deployment environment is a single Windows desktop machine
with no Docker or PostgreSQL installed.

**Alternatives:**
1. **PostgreSQL** — Full RDBMS, excellent for concurrent access, but requires installation
   and management
2. **SQLite** — Zero-config, single-file, built into Python, WAL mode for concurrent reads
3. **MongoDB** — Document store, no schema enforcement, unnecessary complexity
4. **JSON files** — Fragile, no querying, no transactions

**Decision:** SQLite with WAL mode

**Rationale:**
- ~200K rows is well within SQLite's comfortable range (it handles millions)
- Exactly one writer process (FastAPI), so no write contention
- Zero operational complexity — no server, no credentials, no backup strategy beyond file copy
- SQLAlchemy abstracts the engine, so migration to PostgreSQL is a one-line config change
- Already available in the Python standard library (no installation needed)

**Migration trigger:** If concurrent writers are needed (e.g., multiple FastAPI workers)
or the dataset exceeds 10M rows, migrate to PostgreSQL.

---

## D003: Modular Monolith over Microservices

**Date:** 2026-09-14
**Status:** Accepted
**Context:** The system has distinct functional areas (config loading, job management,
discovery, validation, export) that could be separate services.

**Decision:** Single FastAPI process with modular internal structure

**Rationale:**
- All functions are tightly coupled to the same database
- No independent scaling needs — the bottleneck is Playwright browser time, not API throughput
- Single process means no service discovery, no inter-service communication, no distributed tracing
- Internal modules (services/, routers/, models/) provide clean separation without network boundaries
- The team operates this on a single machine

**Migration trigger:** If the discovery engine needs to run on separate hardware
from the API, extract it as a worker service.

---

## D004: n8n for Orchestration Only

**Date:** 2026-09-14
**Status:** Accepted
**Context:** The old n8n workflow (`G-Map_Scraper EPS.json`) does everything:
reads Google Sheets, loops items, executes `node scraper.js` commands, parses stdout
with regex, and writes results back to Sheets. This made n8n the entire runtime.

**Decision:** n8n orchestrates; FastAPI owns all logic

**Rationale:**
- The old pattern of `Execute Command` → `node scraper.js` → parse stdout is fragile
  (regex on stdout to extract JSON, no error codes, no retry logic)
- FastAPI owns: config loading, job state, discovery execution, validation, dedup, persistence
- n8n owns: scheduling (cron), triggering FastAPI endpoints (HTTP), Google Sheets export
  (native node), monitoring/alerting
- This makes the system testable (FastAPI endpoints can be tested without n8n)
  and debuggable (all state is in the database, visible via API)

---

## D005: Coordinate-Based Search over Text-Based Location

**Date:** 2026-09-14
**Status:** Accepted
**Context:** The old scraper searches `{category} near {officename}, {district}, {statename}`.
The current location dataset has only PIN code + lat/long — no district, state, or office name.

**Decision:** Use `@lat,lng,zoom` parameter in Google Maps URL

**Rationale:**
- The location dataset has precise coordinates for all 58 locations
- `https://www.google.com/maps/search/ATM/@28.89,78.47,12z` anchors results to exact coords
- Eliminates dependency on text fields (district, state) that the dataset doesn't have
- More precise than text-based search which relies on Google's geocoding
- Zoom level 12 approximates a 20km radius view

---

## D006: Hash-Based IDs over Auto-Increment

**Date:** 2026-09-14
**Status:** Accepted
**Context:** Records need stable, deterministic identifiers for deduplication and
idempotent operations (re-running config sync shouldn't create duplicates).

**Decision:** SHA256-based truncated hashes as primary keys

**Rationale:**
- `location_id = SHA256(lat + lng + pincode)[:12]` — same input always generates same ID
- `job_id = SHA256(location_id + category_id)[:16]` — idempotent job generation
- `business_id = SHA256(name + phone + lat + lng)[:16]` — natural deduplication
- Re-running config sync or job generation is safe (same IDs = no duplicates)
- IDs are portable across database resets

**Risk:** Hash collisions at 12-16 hex chars. With 200K records and 16 hex chars,
collision probability is ~10^-9. Acceptable.

---

## D007: Deduplication by Composite Key

**Date:** 2026-09-14
**Status:** Accepted
**Context:** The same business can appear in multiple job results (e.g., an ATM near
two overlapping 20km radii). The old scraper had no deduplication, resulting in the
`results-ATM-110001.json` sample having 5 identical "Axis Bank ATM" entries.

**Decision:** Composite dedup key: `normalized(name) + "|" + normalized(phone)`

**Rationale:**
- Name alone has duplicates (many "Axis Bank ATM" entries across locations)
- Phone alone has nulls/missing values
- Name + phone composite uniquely identifies a business establishment
- For phoneless businesses: `normalized(name) + "|nophone"` may cause false dedup,
  which is acceptable (better than showing 5 identical nameless ATMs)
- UNIQUE constraint on `dedup_key` column enforces at database level
- Upsert (INSERT ON CONFLICT UPDATE) handles re-discovery gracefully

---

## D008: No LLM in the Extraction Pipeline

**Date:** 2026-09-14
**Status:** Accepted
**Context:** MASTER_CONTEXT explicitly states: "Do NOT put an LLM everywhere."
The old email automation workflow uses GPT-5 for email copywriting, but that is
a separate concern from data extraction.

**Decision:** No LLM in the discovery/extraction/validation pipeline

**Rationale:**
- Google Maps has structured DOM elements with ARIA labels
- Phone, address, website are extractable via CSS/ARIA selectors
- Field normalization is deterministic string processing
- Validation is rule-based (regex, haversine math)
- LLM adds latency, cost, and non-determinism to an inherently structured task
- The email automation workflow (separate system) appropriately uses LLM for copywriting

---

## D009: No Google Sheets API in Python Backend

**Date:** 2026-09-14
**Status:** Accepted
**Context:** MASTER_CONTEXT requires Google Sheets export. Two approaches:
1. Python backend uses `gspread` with a service account
2. n8n handles Sheets via its native Google Sheets node (OAuth credentials already configured)

**Decision:** All Google Sheets interaction through n8n

**Rationale:**
- n8n already has working Google Sheets OAuth credentials (`FcG3kpEHdKpSbOyX`)
- No service account keys to manage in the Python environment
- No `gspread` dependency, no `google-auth` complexity
- Spreadsheet IDs configured in n8n workflow, not in application code
- FastAPI provides a clean export endpoint; n8n handles the Sheets append
- MASTER_CONTEXT: "Google credentials must never be exposed to the frontend"
  and "n8n credentials/environment configuration should handle authentication"

---

## D010: ARIA-Based Selectors over Class-Based

**Date:** 2026-09-14
**Status:** Accepted
**Context:** MASTER_CONTEXT warns against relying on `div.Nv2PK` and `a.hfpxzc`.
The old scraper uses these brittle class selectors alongside ARIA selectors
(`button[aria-label^="Phone"]`, `a[aria-label^="Open website"]`).

**Decision:** Prefer ARIA and role-based selectors; use class selectors only as fallback

**Rationale:**
- ARIA labels are semantic (Google maintains them for accessibility compliance)
- Class names are minified/obfuscated and change frequently
- Playwright supports `page.get_by_role()`, `page.get_by_label()` natively
- The old scraper's ARIA patterns for phone/address/website already work
- The listing container (`div[role="feed"]`) is role-based and more stable than `div.Nv2PK`
- Failure detection: if expected ARIA elements are absent, the selector strategy may need update

---

## D011: Deferred Frontend

**Date:** 2026-09-14
**Status:** Accepted
**Context:** MASTER_CONTEXT specifies React/TypeScript frontend with server-side pagination.

**Decision:** Frontend is Phase 4. Not built until the backend is fully functional.

**Rationale:**
- Backend API must be stable before frontend development
- n8n + API endpoints provide full functionality without a frontend
- The API contract (API_CONTRACT.md) defines the interface the frontend will consume
- Frontend will be generated via Stitch (per MASTER_CONTEXT) and refined in AI Studio
- Building frontend now would create coupling to an unstable API

---

## D012: No Stealth/Anti-Detection in Phase 1

**Date:** 2026-09-14
**Status:** Accepted
**Context:** The old scraper uses `puppeteer-extra-plugin-stealth`. MASTER_CONTEXT
states: "CAPTCHA/blocking/security mechanisms must cause graceful failure, not bypass attempts."

**Decision:** Standard Playwright browser in Phase 1. Add stealth measures only if
blocking becomes a measurable problem.

**Rationale:**
- Stealth plugins are a form of anti-bot circumvention, which MASTER_CONTEXT prohibits
- Standard browser with normal User-Agent and human-like delays is the ethical approach
- If Google blocks, the system marks jobs as BLOCKED for manual review
- Configurable delays between requests provide natural rate limiting
- Monitor the BLOCKED rate; if it exceeds 10%, evaluate ethical mitigation options
