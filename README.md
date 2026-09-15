# Autonomous Google Maps Business Discovery Agent

An autonomous system that discovers Indian businesses on Google Maps, enriches them with email data, and exports results to Google Sheets via n8n.

## Architecture

```
React/Vite Dashboard  ←→  FastAPI Backend  ←→  PostgreSQL
                               ↕
                         Playwright (Chromium)
                               ↕
                      n8n Workflow Orchestrator
```

- **Backend**: Python 3.12 + FastAPI + SQLAlchemy
- **Browser**: Playwright (Chromium, headless)
- **Database**: PostgreSQL (production) / SQLite (development)
- **Orchestration**: n8n scheduled workflow
- **Frontend**: React 19 + TypeScript + Vite + Tailwind CSS v4

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
| `BACKEND_BASE_URL` | ✅ | URL n8n uses to call the backend (e.g. `http://backend:8000`) |
| `CORS_ORIGINS` | ✅ | Comma-separated frontend origins (e.g. `https://dashboard.example.com`) |
| `N8N_OUTPUT_SPREADSHEET_ID` | For export | Google Sheets ID for daily export |
| `BATCH_SIZE` | Optional | Jobs per n8n batch run (default: 50) |
| `JOB_RETRY_LIMIT` | Optional | Max auto-retries per job (default: 3) |
| `DEFAULT_RADIUS_KM` | Optional | Discovery radius in km (default: 20) |
| `LOG_LEVEL` | Optional | `INFO` or `DEBUG` (default: INFO) |

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
#    BACKEND_BASE_URL = http://backend:8000
#    BATCH_SIZE = 50
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
| `BACKEND_BASE_URL` | `http://backend:8000` (Docker) or `http://your-server:8000` |
| `BATCH_SIZE` | `50` (or as configured) |
| `N8N_OUTPUT_SPREADSHEET_ID` | Your Google Sheets ID |

**Google Sheets credential**: Add a Google OAuth2 credential in n8n (Settings → Credentials → Google Sheets OAuth2 API). The credential never leaves n8n's encrypted store.

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
| POST | `/api/v1/jobs/generate` | Generate (location × category) job matrix |
| POST | `/api/v1/jobs/maintenance` | Recover stale + auto-retry failed jobs |
| POST | `/api/v1/discovery/batch` | Run a batch of discovery jobs |
| GET | `/api/v1/businesses` | Paginated business list |
| GET | `/api/v1/export/businesses` | Export businesses (JSON or CSV) |

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
- [ ] `BACKEND_BASE_URL` is reachable from n8n
- [ ] `alembic upgrade head` has been run on the production database
- [ ] `/health` returns `{"status": "healthy"}`
- [ ] Playwright Chromium launches successfully in the backend container
- [ ] n8n workflow imported and schedule confirmed
- [ ] n8n Google Sheets credential configured
- [ ] Daily backup of PostgreSQL configured
- [ ] Log monitoring in place
