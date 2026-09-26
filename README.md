# AutoGMap — Business Discovery & WhatsApp Outreach

Discovers Indian businesses on Google Maps, enriches them with contact details,
and runs WhatsApp campaigns to them through the Meta Cloud API — from a single
dashboard.

```
┌──────────────────────────── React Dashboard ───────────────────────────┐
│  Discovery  │  Business Data  │  Campaign Builder  │  Campaign History │
└────────────────────────────────┬───────────────────────────────────────┘
                                 │  REST
                        ┌────────▼────────┐
                        │  FastAPI        │
                        └────┬───────┬────┘
              Playwright ◄───┘       └───► Meta WhatsApp Cloud API
             (Google Maps)                 (templates · sends · media)
                        ┌─────────────────┐
                        │   PostgreSQL    │  businesses · jobs · campaigns
                        └─────────────────┘
                                 ▲
                        n8n scheduled workflow
```

| Layer | Stack |
|---|---|
| Backend | Python 3.12 · FastAPI · SQLAlchemy · Alembic |
| Browser | Playwright (Chromium, headless) |
| Database | PostgreSQL (production) · SQLite (development) |
| Messaging | Meta WhatsApp Cloud API |
| Orchestration | n8n scheduled workflow |
| Frontend | React 19 · TypeScript · Vite · Tailwind CSS v4 |

---

## What it does

### Discovery
- Searches Google Maps per **(pincode × category)** pair and extracts name,
  address, phone and website from each listing's detail page.
- **Radius filtering.** Google treats the map viewport as a hint, not a
  constraint, and regularly returns results hundreds of km away. Anything
  outside the location's radius is discarded rather than stored as a
  name-only row.
- **Email enrichment** crawls each business website for a contact address,
  on a strict time budget so a slow site cannot hold up a batch.
- **Deduplication** on place ID, name, phone and coordinates, so the same
  shop discovered under several categories is stored once.
- CAPTCHA is detected and the batch stops early rather than escalating.

### Target locations
- **The PIN list is editable.** The spreadsheets seed it, but new PIN codes and
  towns are added from **Configuration → Add PIN** as the business expands into
  new geography, without touching the source files.
- **Look up** resolves a place through Google Maps and fills in the
  coordinates, and the state and PIN where Maps names them.
- **State and district are required.** Every business discovered at a location
  copies its state, district and tehsil, so a PIN saved without them yields
  rows that can never be filtered by geography. Maps states the state for a PIN
  code search but never the district, so that one is always typed rather than
  guessed.
- A PIN with jobs against it cannot be deleted, so businesses already
  discovered there are never orphaned.

### Turning the webhook on

Everything below the line is built and tested; these are the four steps that
connect it to Meta.

1. **Expose the backend over HTTPS** and set `PUBLIC_BASE_URL` to it (e.g.
   `https://link.eko.in`). The same URL serves the click-tracking redirect, so
   this one variable switches both on.
2. **Set `META_APP_SECRET`** to the app secret from the Meta app dashboard.
   Until it is set, `POST /api/v1/whatsapp/webhook` answers **403 to every
   call**, including Meta's — the signature cannot be verified without it.
3. **Register the callback** in Meta → WhatsApp → Configuration:
   - Callback URL: `<PUBLIC_BASE_URL>/api/v1/whatsapp/webhook`
   - Verify token: the value of `META_WEBHOOK_VERIFY_TOKEN`
4. **Subscribe the fields** `messages` (delivery statuses *and* quick-reply
   taps both arrive under it) and, optionally,
   `message_template_status_update` for template approvals.

Then send one message to your own number and confirm the row in **Campaign
History → View Details** turns Delivered, then Read.

Note that Meta does not replay events for messages already sent, so campaigns
run before this is switched on will never show delivery data.

### Delivery & engagement tracking
- **Campaign History** shows delivered, read and button clicks per campaign;
  **View Details** adds a Delivery & Engagement panel and per-recipient
  Delivered / Read / Clicked columns.
- **Stages are timestamps, not one status.** A message that was read was also
  delivered, so the stages accumulate. Collapsed into a single status field,
  READ overwrites DELIVERED and the delivered count is lost for good.
- **A dash is not a zero.** A sent message Meta has not reported on is unknown,
  not undelivered — only messages Meta actually failed are counted as such.
- **Quick-reply taps are attributed** through the `context.id` on the inbound
  message. Meta sends **no event at all** when a call-to-action URL button is
  tapped, so those are measured by the tracking link instead.
- Events arrive out of order and are repeated until acknowledged, so handling
  is monotonic and idempotent: a late "delivered" never undoes a "read", and a
  redelivered tap is never counted twice.
- **Requires the webhook.** Data only flows once `/api/v1/whatsapp/webhook` is
  reachable at a public HTTPS URL and subscribed to `messages` in the Meta app.
  Meta does not replay events for messages already sent, so campaigns run
  before that show no delivery data.

### WhatsApp campaigns
- **Template lifecycle against Meta.** Templates are composed in the UI with a
  live preview, submitted for review automatically, and their status and
  billing category are synced back from the WhatsApp Business Account.
- **Pre-flight checks.** Before a campaign sends anything it verifies the
  template is `APPROVED` in the WABA and that its header media exists and fits
  Meta's per-type size limit. A misconfigured campaign fails once with a
  readable reason instead of one rejected recipient at a time.
- **Contact validation** normalises Indian numbers to `+91XXXXXXXXXX`,
  separating landlines, malformed entries and duplicates before sending.
- **Resumable campaigns.** A campaign stopped mid-run can continue for the
  recipients it never reached, without re-contacting anyone already sent to.
- **Per-campaign execution log** with Meta's own error codes, visible in the
  dashboard rather than only in container logs.

### Dashboard
- Light and dark themes, remembered per browser.
- Campaign history with a detail view: delivery counters, failure reasons
  grouped by cause, the template that was sent, and the full execution log.
- Timestamps render in the viewer's own timezone.

---

## Quick Start — Local Development

### Prerequisites

- Python 3.12+
- Node.js 20+
- Git

### 1. Clone and set up environment

```bash
git clone https://github.com/mansikanchan2003/G-Map-Data-Scraper.git
cd G-Map-Data-Scraper
cp .env.example .env
# Edit .env if needed — SQLite defaults work for local dev
```

### 2. Install Python dependencies

```bash
pip install -r requirements.txt
```

### 3. Install Playwright Chromium browser

```bash
python -m playwright install chromium
python -m playwright install-deps chromium   # Linux only
```

### 4. Initialize the database (SQLite — local dev)

```bash
# Option A: let the app create it on startup (automatic)
uvicorn src.main:app --reload

# Option B: use Alembic explicitly
alembic upgrade head
uvicorn src.main:app --reload
```

### 5. Verify the backend

```bash
curl http://localhost:8000/health
# Expected: {"status": "healthy", "database": "healthy", ...}
```

### 6. Install and start the frontend

```bash
cd frontend
npm install
npm run dev
# Open http://localhost:5173
```

---

## Production Deployment

### Prerequisites

- Linux server (Ubuntu 22.04+ or Debian 12+ recommended)
- Docker 24+ and Docker Compose v2
- PostgreSQL 16+ (or use the provided docker-compose)
- Minimum 2 GB RAM (Playwright Chromium requires ~500 MB per browser context)

### Environment Variables

Copy `.env.example` to `.env` and configure all required values:

| Variable | Required | Description |
|---|---|---|
| `DATABASE_URL` | ✅ | PostgreSQL connection string: `postgresql+psycopg://user:pass@host:5432/db` |
| `POSTGRES_PASSWORD` | ✅ | PostgreSQL password (Docker Compose only) |
| `N8N_BACKEND_BASE_URL` | ✅ | URL n8n uses to call the backend (e.g. `http://backend:8000`) |
| `CORS_ORIGINS` | ✅ | Comma-separated frontend origins (e.g. `https://dashboard.example.com`) |
| `N8N_OUTPUT_SPREADSHEET_ID` | For export | Google Sheets ID for daily export |
| `BATCH_SIZE` | Optional | Jobs per n8n batch run (default: 15) |
| `JOB_RETRY_LIMIT` | Optional | Max auto-retries per job (default: 3) |
| `DEFAULT_RADIUS_KM` | Optional | Discovery radius in km (default: 20) |
| `LOG_LEVEL` | Optional | `INFO` or `DEBUG` (default: INFO) |

**WhatsApp (Meta Cloud API)**

| Variable | Required | Description |
|---|---|---|
| `META_ACCESS_TOKEN` | For campaigns | Graph API token. Use a **System User** token — a personal user token expires and every send then fails with `#131005`. |
| `META_PHONE_NUMBER_ID` | For campaigns | The sending number's ID, from WhatsApp → API Setup |
| `META_WABA_ID` | For campaigns | WhatsApp Business Account ID. Required to read and submit templates. |
| `META_APP_SECRET` | For webhooks | Verifies webhook signatures |
| `META_API_VERSION` | Optional | Graph API version (default: `v21.0`) |
| `MOCK_WHATSAPP_API` | Optional | `true` simulates sends without contacting Meta. For local testing only. |

**Discovery tuning** — defaults are tuned from measured job profiles; detail-page
fetching is roughly 78% of a job, so the per-listing pause is the cheapest thing
to trim.

| Variable | Default | Description |
|---|---|---|
| `LISTING_DELAY_SECONDS` | `0.3` | Pause after each detail page |
| `MAX_SCROLL_ATTEMPTS` | `3` | Result-feed scroll iterations |
| `ELEMENT_TIMEOUT_MS` | `4000` | Wait for the place panel to render |
| `EMAIL_MAX_CONCURRENCY` | `8` | Parallel website crawls during enrichment |
| `EMAIL_ENRICHMENT_TIMEOUT_SECONDS` | `15` | Per-business enrichment budget |
| `EMAIL_ENRICHMENT_BATCH_TIMEOUT_SECONDS` | `60` | Whole-batch enrichment budget |

**Campaign link tracking** (optional)

| Variable | Description |
|---|---|
| `PUBLIC_BASE_URL` | A URL a phone can reach over the internet, e.g. `https://link.example.com`. Without it, messages carry the plain destination and no clicks are recorded. |
| `CAMPAIGN_LINK_TARGET_URL` | Where a tracked link forwards to |
| `CAMPAIGN_LINK_FALLBACK_URL` | Destination for an unknown or expired token |
| `CAMPAIGN_LINK_HASH_SALT` | Salt for hashing visitor IPs |

**Never commit your `.env` file. It is excluded by `.gitignore`.**

### Option A — Docker Compose (Recommended)

```bash
# 1. Configure environment
cp .env.example .env
# Edit .env: set POSTGRES_PASSWORD, DATABASE_URL, BACKEND_BASE_URL, CORS_ORIGINS

# 2. Build and start all services
docker compose up -d

# 3. Run database migrations (first deployment only)
docker compose exec backend alembic upgrade head

# 4. Verify health
curl http://localhost:8000/health

# 5. Import n8n workflow
# Open http://localhost:5678
# Settings → Import workflow → select n8n/autonomous_google_maps_daily.json

# 6. Configure n8n environment variables in n8n UI:
#    N8N_BACKEND_BASE_URL = http://backend:8000
#    BATCH_SIZE = 15
#    N8N_OUTPUT_SPREADSHEET_ID = your-sheet-id

# 7. Sync configuration data
curl -X POST http://localhost:8000/api/v1/config/sync

# 8. Generate job queue
curl -X POST http://localhost:8000/api/v1/jobs/generate
```

### Option B — Bare Metal (without Docker)

```bash
# PostgreSQL setup (on Ubuntu/Debian)
sudo apt install postgresql-16
sudo -u postgres createuser gmap_user
sudo -u postgres createdb gmap_scraper -O gmap_user
sudo -u postgres psql -c "ALTER USER gmap_user PASSWORD 'your_strong_password';"

# Install dependencies
pip install -r requirements.txt
python -m playwright install chromium
python -m playwright install-deps chromium

# Configure
cp .env.example .env
# Set DATABASE_URL=postgresql+psycopg://gmap_user:your_strong_password@localhost:5432/gmap_scraper

# Run migrations
alembic upgrade head

# Start backend (production — single worker because of Playwright)
uvicorn src.main:app --host 0.0.0.0 --port 8000 --workers 1

# Start frontend (production build)
cd frontend
npm install
npm run build
# Serve dist/ with nginx or any static file server
```

---

## WhatsApp Campaigns

### How a message actually gets sent

This is the part that surprises people, and most campaign failures trace back
to it:

> **A template's text lives with Meta, not here.** A send transmits only the
> template *name*, *language* and *parameters*. Meta renders the message from
> its own approved copy.

Two consequences:

- A template must be **submitted to Meta and approved** before it can be sent.
  A local draft cannot be delivered — Meta answers `#132001 Template name does
  not exist`.
- Editing a template locally changes the dashboard preview but **not** what
  recipients receive. The app therefore pushes edits to Meta, which sends the
  template back through review.

### Credentials

| Variable | Notes |
|---|---|
| `META_ACCESS_TOKEN` | Use a **System User** token from Business Settings. A personal user token expires — often within hours — and every send then fails with `#131005 Access denied`. |
| `META_PHONE_NUMBER_ID` | The sending number, from WhatsApp → API Setup |
| `META_WABA_ID` | Needed to list, submit and edit templates |
| `META_APP_SECRET` | Webhook signature verification |

Credentials live in `.env` (git-ignored) or your secret manager. They are never
sent to the frontend, and error messages are redacted before being logged.
Connection is only reported as **Connected** after a successful Meta API call,
never merely because the variables are set.

### Template workflow

```
Compose in UI  →  auto-submitted to Meta  →  PENDING  →  APPROVED  →  sendable
                                                     ↘  REJECTED  →  edit & resubmit
```

- Creating a template submits it for review automatically. If Meta refuses the
  submission the template stays a local draft and the reason is shown.
- **Sync Status** pulls each template's current review state and billing
  category from the WABA. Meta can reclassify a template during review, so the
  category shown is the one Meta assigned, not the one requested.
- Deleting a template keeps past campaign history; the campaign's link to it is
  cleared. The copy registered with Meta is left untouched.

### Media limits

Meta enforces different ceilings per media type and rejects anything larger at
send time with an opaque `(#100) Invalid parameter`. The same limits are applied
at upload instead, so an oversized file is refused while you are still looking at
the dialog.

| Header type | Limit |
|---|---|
| Image | 5 MB |
| Video | 16 MB |

Header media is uploaded to Meta **once per campaign** and reused for every
recipient.

### Costs

Marketing and utility templates are priced very differently. Real figures for
your account come from Meta:

```bash
# Per-message cost and volume, by category
curl -s -G "https://graph.facebook.com/v21.0/$META_WABA_ID" \
  -H "Authorization: Bearer $META_ACCESS_TOKEN" \
  --data-urlencode "fields=currency,pricing_analytics.start(<unix>).end(<unix>).granularity(DAILY).dimensions([\"PRICING_CATEGORY\"])"
```

### Delivery visibility

`SENT` means **Meta accepted the request**, not that the message arrived.
Aggregate delivery counts are available without any webhook setup:

```bash
curl -s -G "https://graph.facebook.com/v21.0/$META_WABA_ID" \
  -H "Authorization: Bearer $META_ACCESS_TOKEN" \
  --data-urlencode "fields=analytics.start(<unix>).end(<unix>).granularity(DAY)"
# → {"sent": 1270, "delivered": 1239}
```

Per-recipient delivery and read receipts require Meta to reach this backend over
the internet, which means a public URL and a subscribed webhook.

Note that Meta may accept a marketing message and silently not deliver it if the
recipient has received many marketing messages without engaging. This is
deliberate on Meta's side and is not reported back through the send response.

### Click tracking (optional)

WhatsApp does not report clicks on a link written in a message body, and a URL
identical for every recipient cannot attribute a visit to anyone. Each recipient
therefore gets their own short link:

```
https://<PUBLIC_BASE_URL>/r/<token>  →  click recorded  →  302 to the destination
```

Campaign History then shows **Unique Visits** (recipients who opened the link at
least once) and **Repeated Visits** (opens beyond each recipient's first).

Requirements: a publicly reachable `PUBLIC_BASE_URL`, and a template whose body
contains `{{link}}`. Without `PUBLIC_BASE_URL` the plain destination is sent and
no clicks are recorded — messages always carry a working link. Visitor IPs are
hashed, never stored, and a tracking failure never blocks the redirect.

---

## Playwright Browser Setup

The discovery engine and email enricher both use Playwright Chromium.

The following flags are already configured in the code for container execution:
```
--no-sandbox
--disable-setuid-sandbox
--disable-dev-shm-usage
--disable-blink-features=AutomationControlled
```

If Chromium fails to launch in your environment:
```bash
# Verify browser is installed
python -m playwright install chromium

# Linux: install OS dependencies
python -m playwright install-deps chromium

# Test launch
python -c "from playwright.sync_api import sync_playwright; p = sync_playwright().start(); b = p.chromium.launch(headless=True); b.close(); p.stop(); print('OK')"
```

---

## Database Migrations

### First deployment (PostgreSQL)

```bash
alembic upgrade head
```

### After schema changes

```bash
# Generate a new migration from model changes
alembic revision --autogenerate -m "describe_your_change"

# Review and edit the generated file in alembic/versions/
# Then apply:
alembic upgrade head
```

### Current status

```bash
alembic current
alembic history --verbose
```

### Migrations in this project

| Revision | Adds |
|---|---|
| `0001` | Locations, categories, jobs, businesses, run log |
| `0e08654b0f18` | WhatsApp accounts, templates, campaigns, recipients, logs |
| `1a7c3b9e2d40` | Template's Meta name and approved language |
| `2b9f4c7d1e88` | Per-recipient tracking token and link-click records |
| `3c1a8e5f7b22` | Template billing category as reported by Meta |
| `4d2b7a9c3e51` | Template delete clears the campaign link instead of blocking |

---

## n8n Workflow

The daily automation workflow file: `n8n/autonomous_google_maps_daily.json`

**Schedule**: Runs at 02:00 UTC daily (configurable in the Schedule Trigger node).

**Flow**:
1. Health check → fail fast if backend is down
2. Config sync → load locations and categories
3. Job maintenance → recover stale jobs, auto-retry failed jobs
4. Generate jobs → create pending jobs for all (location × category) pairs
5. Check stats → count pending jobs
6. Batch discovery → run `BATCH_SIZE` jobs (Playwright scraping + email enrichment)
7. Export → fetch new businesses since run start
8. Google Sheets → append results to spreadsheet

**Required n8n environment variables** (set in n8n UI under Settings → Variables):

| Variable | Value |
|---|---|
| `N8N_BACKEND_BASE_URL` | `http://backend:8000` (Docker) or `http://your-server:8000` |
| `BATCH_SIZE` | `15` (or as configured) |
| `N8N_OUTPUT_SPREADSHEET_ID` | Your Google Sheets ID |

**Google Sheets credential**: Add a Google OAuth2 credential in n8n (Settings → Credentials → Google Sheets OAuth2 API). The credential never leaves n8n's encrypted store.

---

## Dashboard

```bash
cd frontend && npm run dev     # http://localhost:5173
```

| View | Purpose |
|---|---|
| Dashboard | Job queue state, last orchestration run, engine health |
| Business Data | Discovered businesses, searchable, exportable to CSV / Excel / Sheets |
| Jobs Monitor | Per-job status, retries, and a job inspector |
| Configuration | Locations (pincode, district, tehsil, anchor) and categories |
| WhatsApp Campaign | Four-step builder: data → template → preview → confirm |
| Templates | Compose with live WhatsApp preview; search, edit, submit, status |
| Campaign History | Counters, visit tracking, and a per-campaign detail view |

The theme toggle sits in the header and is remembered per browser.

---

## Health Verification

```bash
# Liveness check
curl http://localhost:8000/health

# Readiness check
curl http://localhost:8000/ready

# System stats
curl http://localhost:8000/api/v1/stats
```

Expected healthy response:
```json
{
  "status": "healthy",
  "version": "1.0.0",
  "database": "healthy",
  "db_backend": "postgresql",
  "environment": "production",
  "timestamp": "2026-09-15T12:00:00.000000+00:00"
}
```

---

## Logs

### Docker Compose

```bash
# All services
docker compose logs -f

# Backend only
docker compose logs -f backend

# Tail last 100 lines
docker compose logs --tail=100 backend
```

### Bare metal

```bash
# Redirect uvicorn logs to a file
uvicorn src.main:app --host 0.0.0.0 --port 8000 --workers 1 \
  --log-level info --access-log 2>&1 | tee /var/log/gmap_scraper.log
```

Log events you will see:
- `Starting Autonomous Google Maps Business Discovery Agent` — startup
- `Database schema initialized` — DB ready
- `Starting discovery for Job <id>` — job begins
- `Discovered N listing cards` — Playwright found results
- `Enriching email for <name>` — email enrichment in progress
- `Recovered N stale RUNNING jobs` — maintenance
- `Shutdown complete` — clean exit

**Logs never contain**: passwords, tokens, private keys, OAuth credentials, or cookie values.

---

## Backup and Recovery

### What to back up

| Data | Location | Frequency |
|---|---|---|
| PostgreSQL database | `postgres_data` Docker volume | Daily |
| n8n workflows | `n8n_data` Docker volume | After changes |
| Source data files | `Geocoded_Ad_Targeting_Locations_FINAL.xlsx`, `G-Map Scraper Categories.xlsx` | On change |

### PostgreSQL backup

```bash
# Full database dump (replace placeholders)
pg_dump \
  --host=YOUR_DB_HOST \
  --port=5432 \
  --username=YOUR_DB_USER \
  --dbname=YOUR_DB_NAME \
  --no-password \
  --format=custom \
  --file=gmap_scraper_$(date +%Y%m%d).dump

# Docker Compose (backup from running container)
docker compose exec -T postgres \
  pg_dump -U gmap_user -d gmap_scraper --format=custom \
  > gmap_scraper_$(date +%Y%m%d).dump
```

### PostgreSQL restore

> ⚠️ **WARNING**: Restore overwrites the target database. Test in staging first.

```bash
pg_restore \
  --host=YOUR_DB_HOST \
  --port=5432 \
  --username=YOUR_DB_USER \
  --dbname=YOUR_DB_NAME \
  --no-password \
  --clean \
  gmap_scraper_20260915.dump

# Docker Compose restore
docker compose exec -T postgres \
  pg_restore -U gmap_user -d gmap_scraper --clean \
  < gmap_scraper_20260915.dump
```

---

## Troubleshooting

### Backend won't start

```bash
# Check Python version
python --version  # must be 3.12+

# Check for import errors
python -c "from src.main import app; print('OK')"

# Check .env configuration
python -c "from src.config import settings; print(settings.database_url[:20])"
```

### Database connection fails

```bash
# PostgreSQL — test connection
python -c "
import psycopg
conn = psycopg.connect('YOUR_DATABASE_URL')
print('Connected OK')
conn.close()
"

# Verify host/port/credentials in DATABASE_URL
```

### Playwright / Chromium fails to launch

```bash
# Linux — install OS dependencies
python -m playwright install-deps chromium

# Test launch manually
python -c "
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    b = p.chromium.launch(headless=True, args=['--no-sandbox'])
    print('Browser OK:', b.version)
    b.close()
"
```

### CAPTCHA / blocked discovery jobs

This is expected behavior. Google Maps rate-limits automated access. The system:
- Detects CAPTCHA and marks the job as `BLOCKED`
- Stops the batch early to prevent escalation
- The job can be retried later via `/api/v1/jobs/retry-all`
- Reduce `BATCH_SIZE` and increase `SEARCH_DELAY_SECONDS` to reduce blocking

### WhatsApp campaign failures

Every campaign failure is written to `whatsapp_campaign_logs` and shown in
Campaign History → **View Details**, with Meta's own error code.

| What you see | Cause | Fix |
|---|---|---|
| `#132001 Template name does not exist` | The template was never approved in the WABA, or the language does not match | Submit it for review; check **Sync Status** |
| `#131005 Access denied` | Token expired, or it lacks messaging permission on this WABA | Use a **System User** token that does not expire |
| `#100 Invalid parameter` on media upload | Header image over 5 MB / video over 16 MB | Compress and re-upload |
| `#100 Content in this language already exists` | A template with that name and language is already in the WABA | The app links to the existing one automatically |
| Campaign `FAILED`, 0 sent, 0 failed | Pre-flight stopped it before sending | Read the reason in the campaign log |
| Status `SENT` but no message received | Meta accepted it but did not deliver — often a recipient who has received many marketing messages without engaging | Test with a number that has not been messaged recently |

```bash
# Campaign execution log
curl -s http://localhost:8000/api/v1/whatsapp/campaigns/<campaign_id>/logs

# What Meta actually has approved
curl -s http://localhost:8000/api/v1/whatsapp/templates/meta
```

### Discovery returns names but no phone or website

Check the per-job summary in the logs:

```bash
docker compose logs backend | grep "extraction summary"
# in_range=18 out_of_range_discarded=2 no_contact_data=0 errors=0
```

- `out_of_range_discarded` high → Google is returning results far outside the
  radius. Expected for sparse categories in rural pincodes; those listings are
  dropped rather than stored empty.
- `no_contact_data` high → the place panel is not rendering before extraction.
  Raise `ELEMENT_TIMEOUT_MS`.

### Stopping a running batch

```bash
curl -X POST http://localhost:8000/api/v1/discovery/stop
```

The batch finishes the job it is on and then stops, so nothing is lost and
anything else sharing the process — a campaign mid-send, for instance — is
unaffected. Restarting the backend is not required.

### Frontend can't connect to backend

```bash
# Check VITE_API_BASE_URL in .env (frontend)
# Or use the Settings modal in the dashboard to override the API URL at runtime
```

---

## API Reference

Full API contract: [`docs/API_CONTRACT.md`](docs/API_CONTRACT.md)

Key endpoints:

| Method | Endpoint | Description |
|---|---|---|
| GET | `/health` | Liveness + DB check |
| GET | `/ready` | Readiness probe |
| GET | `/api/v1/stats` | System statistics |
| POST | `/api/v1/config/sync` | Load locations and categories from xlsx |
| POST | `/api/v1/config/locations/resolve` | Look a place up on Maps without saving it |
| POST | `/api/v1/config/locations` | Add a target PIN |
| DELETE | `/api/v1/config/locations/{id}` | Remove a target PIN that has no jobs |
| POST | `/api/v1/jobs/generate` | Generate (location × category) job matrix |
| POST | `/api/v1/jobs/maintenance` | Recover stale + auto-retry failed jobs |
| POST | `/api/v1/discovery/batch` | Run a batch of discovery jobs |
| POST | `/api/v1/discovery/stop` | Stop the running batch after its current job |
| GET | `/api/v1/businesses` | Paginated business list |
| GET | `/api/v1/export/businesses` | Export businesses (JSON or CSV) |

`/discovery/batch` can be narrowed to a subset of the job queue — all filters
combine with AND:

```jsonc
{
  "batch_size": 25,
  "delay_between_jobs_seconds": 5,
  "states": ["Punjab"],              // or pincodes / anchor_names
  "categories": ["Kiosk", "Print shop"]
}
```

**WhatsApp**

| Method | Endpoint | Description |
|---|---|---|
| POST | `/api/v1/whatsapp/accounts/connect` | Verify Meta connectivity and register the sending number |
| GET | `/api/v1/whatsapp/templates` | Local templates |
| POST | `/api/v1/whatsapp/templates` | Create, and submit to Meta for review |
| PATCH | `/api/v1/whatsapp/templates/{id}` | Edit, and push the change to Meta |
| DELETE | `/api/v1/whatsapp/templates/{id}` | Delete locally, keeping campaign history |
| GET | `/api/v1/whatsapp/templates/meta` | Templates as registered in the WABA |
| POST | `/api/v1/whatsapp/templates/sync-status` | Refresh review status and category from Meta |
| POST | `/api/v1/whatsapp/templates/{id}/submit` | Submit an existing draft for review |
| POST | `/api/v1/whatsapp/media/upload` | Upload header media (validated against Meta's limits) |
| POST | `/api/v1/whatsapp/contacts/validate` | Normalise and deduplicate phone numbers |
| POST | `/api/v1/whatsapp/campaigns` | Create a campaign and start sending |
| GET | `/api/v1/whatsapp/campaigns` | Campaign list with visit counters |
| GET | `/api/v1/whatsapp/campaigns/{id}/recipients` | Per-recipient status and reason |
| GET | `/api/v1/whatsapp/campaigns/{id}/logs` | Execution log with Meta error codes |
| POST | `/api/v1/whatsapp/campaigns/{id}/resume` | Continue for recipients never reached |
| POST | `/api/v1/whatsapp/campaigns/{id}/cancel` | Stop a running campaign |
| GET | `/r/{token}` | Campaign link redirect — records the click |

---

## Development

### Running tests

```bash
pytest -q
```

### TypeScript type check

```bash
cd frontend
npx tsc -b
```

### Frontend production build

```bash
cd frontend
npm run build
```

### Validate n8n workflow JSON

```bash
python -m json.tool n8n/autonomous_google_maps_daily.json > /dev/null && echo "Valid JSON"
```

---

## Security Notes

- **CORS**: Configured via `CORS_ORIGINS` env var. Never use `*` with credentials.
- **Secrets**: All credentials are environment-variable based. The `.gitignore` excludes `.env`, `*.env.*`, `service_account*.json`, and private key files.
- **Database**: Passwords never appear in logs. `DATABASE_URL` is only referenced by the backend process.
- **Google Sheets**: Credentials are stored in n8n's encrypted credential store — never in the backend or frontend.
- **Browser**: Playwright runs headless with container-safe flags. No proxy rotation, stealth plugins, or CAPTCHA solvers are used.
- **Non-root**: The Docker image runs as `appuser` (non-root).

---

## Production Readiness Checklist

- [ ] `DATABASE_URL` points to PostgreSQL (not SQLite)
- [ ] `POSTGRES_PASSWORD` is a strong random password
- [ ] `CORS_ORIGINS` lists only your actual frontend origin(s)
- [ ] `N8N_BACKEND_BASE_URL` is reachable from n8n
- [ ] `alembic upgrade head` has been run on the production database
- [ ] `/health` returns `{"status": "healthy"}`
- [ ] Playwright Chromium launches successfully in the backend container
- [ ] n8n workflow imported and schedule confirmed
- [ ] n8n Google Sheets credential configured
- [ ] Daily backup of PostgreSQL configured
- [ ] Log monitoring in place

**WhatsApp campaigns**

- [ ] `META_ACCESS_TOKEN` is a **System User** token (never expires)
- [ ] `META_WABA_ID` set — templates cannot be read or submitted without it
- [ ] At least one template shows `APPROVED` in the Templates view
- [ ] Header media is within Meta's limits (5 MB image / 16 MB video)
- [ ] A test campaign to a single number completed with `sent=1, failed=0`
- [ ] `PUBLIC_BASE_URL` set if click tracking is wanted
