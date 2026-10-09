# AutoGMap — Project Documentation

> **Internal reference for the rack server deployment at Eko.**
> Last updated: 7 October 2026

---

## 1. What Is AutoGMap?

AutoGMap (**Autonomous Google Maps Business Discovery & WhatsApp Outreach**) is a
full-stack platform built by Eko's team. It automates three things end-to-end:

1. **Discover** Indian businesses on Google Maps — by PIN code × category.
2. **Enrich** each business with phone, address, website, email and geography.
3. **Reach** those businesses through WhatsApp marketing campaigns via the Meta
   Cloud API — from a single dashboard.

The target audience is **SBI CSP / Kiosk operators and small retailers** across
Indian states. The outreach drives signups to [kiosk.eko.in](https://kiosk.eko.in).

---

## 2. Use Cases

### 2.1 Business Discovery (Google Maps Scraping)

| Use Case | Description |
|---|---|
| **Batch Discovery** | Searches Google Maps for a (pincode × category) pair, extracts name, address, phone, website from each listing's detail page. |
| **Radius Filtering** | Discards results outside the location's radius — Google returns results hundreds of km away, these are filtered out. |
| **Email Enrichment** | Crawls each business website for a contact email, on a strict time budget. |
| **Deduplication** | Deduplicates on place ID, name, phone and coordinates so the same shop discovered under multiple categories is stored once. |
| **CAPTCHA Handling** | CAPTCHA is detected → batch stops early rather than escalating. Never tries to solve a CAPTCHA. |
| **Scraping Autopilot** | Fully autonomous mode that runs in rounds (1 state, 5 batches of 25 jobs), rotating states, pacing itself to avoid detection, with daily limits (10 batches/day IST). |
| **Failed Job Retries** | Failed jobs are re-queued and retried up to `JOB_RETRY_LIMIT` (default: 3) before each round. |
| **Internet Outage Resilience** | Checks connectivity before every batch; if lost mid-batch, stops after 3 failures and waits (5, 15, 30, then every 60 min). |
| **Server Safety** | Memory-capped container (4 GB), orphan browser cleanup, PID limit (2048). Cannot take the shared rack server down. |

### 2.2 Target Location Management

| Use Case | Description |
|---|---|
| **PIN Management** | Add/remove PIN codes via the dashboard. State + district are required for every PIN. |
| **Place Resolution** | "Look up" resolves a place through Google Maps, auto-fills coordinates, state and PIN. |
| **Source Data Sync** | Loads locations and categories from Excel spreadsheets (`Geocoded_Ad_Targeting_Locations_FINAL.xlsx`, `G-Map Scraper Categories.xlsx`). |

### 2.3 WhatsApp Campaigns (Meta Cloud API)

| Use Case | Description |
|---|---|
| **Template Lifecycle** | Compose templates in the UI → auto-submitted to Meta → PENDING → APPROVED → sendable. |
| **Template Studio (AI Agent)** | Gemini-powered agent drafts templates in regional languages (Hindi, Punjabi, Gujarati, Marathi, Bengali, Tamil, Telugu, Kannada, Malayalam) across 19 states, with live performance data feedback. |
| **Template Studio (Messages Sheet)** | Upload a CSV/Excel of per-person messages → the system extracts a single template with placeholders → submits to Meta. |
| **Campaign Execution** | Four-step builder: data → template → preview → confirm. Validates contacts, normalises Indian numbers to `+91XXXXXXXXXX`. |
| **Resumable Campaigns** | A stopped campaign can continue for unsent recipients without re-contacting anyone. |
| **Click Tracking** | Each recipient gets a unique `/r/<token>` short link → visit recorded → 302 redirect to destination. |
| **Delivery & Engagement Tracking** | Tracks delivered, read, button clicks per campaign via Meta webhooks. Events are monotonic and idempotent. |
| **Leads & Replies** | Quick-reply button taps surface as leads in a dedicated panel; operators can send free-form replies directly from the dashboard. |
| **Poster Rendering** | WhatsApp poster images are rendered in Chromium with real Indic fonts (Noto Sans family), avoiding AI models that misspell Indic scripts. |
| **Campaign Insights** | AI-generated playbooks analysing what messaging approaches work per state. |

### 2.4 Data Export

| Use Case | Description |
|---|---|
| **CSV / Excel Download** | Export scraped business data from the dashboard. |
| **Google Sheets Sync** | Single shared Google Sheet ("All Scraped Data from AutoGMap") is rewritten on demand. |
| **n8n Automated Export** | Daily n8n workflow appends results to a Google Sheet. |

### 2.5 Access Control & Authentication

| Use Case | Description |
|---|---|
| **Domain-Gated Signup** | Only `@eko.co.in` email addresses can request access. |
| **Admin Approval** | Signup creates a `PENDING` account; an admin must approve before login works. |
| **Role-Based Access** | Member (view-only), Operator, Manager, Admin — enforced server-side. |
| **Password Reset** | 6-digit code sent to admin email, 10-minute expiry, 5-attempt limit. |

---

## 3. Tech Stack

| Layer | Technology |
|---|---|
| **Backend** | Python 3.12 · FastAPI · SQLAlchemy · Alembic · Pydantic |
| **Browser Automation** | Playwright (Chromium, headless) |
| **Database** | PostgreSQL 16 (production) · SQLite (development) |
| **Messaging** | Meta WhatsApp Cloud API (Graph API v21.0) |
| **AI / LLM** | Google Gemini API (copywriting, image checks) · FLUX.1 Schnell (image generation via BFL API) |
| **Orchestration** | n8n (scheduled daily workflow) |
| **Frontend** | React 19 · TypeScript 6 · Vite 5 · Tailwind CSS v4 |
| **Containerisation** | Docker (multi-stage build) · Docker Compose |
| **Auth** | JWT sessions (PyJWT) · bcrypt password hashing |
| **Export** | gspread + Google Auth (Sheets) · openpyxl (Excel) |

---

## 4. Architecture Overview

```
┌──────────────────────────── React Dashboard ────────────────────────────┐
│  Discovery │ Business Data │ Campaign Builder │ Campaign History │ …    │
└────────────────────────────────┬────────────────────────────────────────┘
                                 │  REST API
                        ┌────────▼────────┐
                        │    FastAPI       │
                        │   (uvicorn)      │
                        └──┬─────┬─────┬──┘
          Playwright ◄─────┘     │     └─────► Meta WhatsApp Cloud API
         (Google Maps)           │             (templates · sends · media)
                                 │
                        ┌────────▼────────┐
                        │   PostgreSQL    │  businesses · jobs · campaigns
                        └────────▲────────┘
                                 │
                        n8n scheduled workflow (daily at 02:00 UTC)
```

### Docker Compose Services

| Service | Image | Purpose |
|---|---|---|
| `postgres` | `postgres:16-alpine` | Production database, data in named volume |
| `backend` | Custom Dockerfile (Python 3.12-slim + Playwright) | FastAPI app, serves built frontend |
| `n8n` | `n8nio/n8n:latest` | Workflow automation, daily scraping schedule |

---

## 5. Directory Structure on the Rack Server

The project is deployed on the rack server at:

```
/home/mansi/AUTOGMAP/
```

Below is the complete directory tree:

```
/home/mansi/AUTOGMAP/
│
├── .env                          # Runtime configuration (git-ignored, NEVER committed)
├── .env.example                  # Template with all variables documented
├── .gitignore                    # Excludes .env, databases, node_modules, etc.
├── Dockerfile                    # Multi-stage: Node build + Python 3.12-slim + Playwright
├── docker-compose.yml            # 3 services: postgres, backend, n8n
├── requirements.txt              # Python dependencies (FastAPI, Playwright, SQLAlchemy, etc.)
├── alembic.ini                   # Alembic migration configuration
├── pytest.ini                    # Test runner config
├── README.md                     # Full project documentation (1,173 lines)
│
├── Geocoded_Ad_Targeting_Locations_FINAL.xlsx   # Source: PIN codes with coordinates
├── G-Map Scraper Categories.xlsx                # Source: business categories to search
│
├── src/                          # ── Python Backend ──
│   ├── __init__.py
│   ├── main.py                   # FastAPI app, lifespan, middleware, static file serving
│   ├── config.py                 # Pydantic Settings (all env vars)
│   ├── database.py               # SQLAlchemy engine, session factory, init
│   │
│   ├── models/                   # SQLAlchemy ORM models
│   │   ├── business.py           #   Discovered businesses
│   │   ├── job.py                #   Scraping jobs (pincode × category)
│   │   ├── location.py           #   Target PIN codes / locations
│   │   ├── category.py           #   Business categories
│   │   ├── run_log.py            #   Batch execution logs
│   │   ├── whatsapp.py           #   Accounts, templates, campaigns, recipients, logs
│   │   ├── autopilot.py          #   Autopilot round tracking
│   │   ├── insights.py           #   Campaign insight snapshots
│   │   ├── user.py               #   User accounts and access control
│   │   └── app_setting.py        #   Persistent app settings
│   │
│   ├── schemas/                  # Pydantic request/response schemas
│   │   ├── business.py
│   │   ├── job.py
│   │   ├── location.py
│   │   ├── category.py
│   │   ├── run_log.py
│   │   ├── whatsapp.py
│   │   └── common.py
│   │
│   ├── routers/                  # FastAPI route handlers (API endpoints)
│   │   ├── auth.py               #   Login, signup, password reset, access requests
│   │   ├── config.py             #   Location/category CRUD, sync from xlsx
│   │   ├── discovery.py          #   Batch scraping, autopilot control, stop
│   │   ├── jobs.py               #   Job generation, maintenance, retry
│   │   ├── businesses.py         #   Paginated business listing
│   │   ├── export.py             #   CSV, Excel, Google Sheets export
│   │   ├── whatsapp.py           #   Templates, campaigns, webhook, media upload
│   │   ├── template_studio.py    #   AI template drafting (Gemini-powered)
│   │   ├── tracking.py           #   Campaign link redirect & click recording
│   │   ├── audience.py           #   Audience selection from business data
│   │   ├── insights.py           #   Campaign insights & playbook
│   │   └── runs.py               #   Run history
│   │
│   ├── services/                 # Business logic layer
│   │   ├── discovery_engine.py       # Playwright Google Maps scraping
│   │   ├── discovery_autopilot.py    # Autonomous scraping scheduler
│   │   ├── email_enricher.py         # Website crawl for contact emails
│   │   ├── deduplicator.py           # Business deduplication
│   │   ├── job_manager.py            # Job queue management
│   │   ├── config_loader.py          # xlsx → database sync
│   │   ├── geo_bounds.py             # Radius filtering math
│   │   ├── geo_validator.py          # Geography validation
│   │   ├── normalizer.py             # Data normalisation
│   │   ├── whatsapp_service.py       # Campaign send logic
│   │   ├── meta_whatsapp_service.py  # Meta Graph API client
│   │   ├── whatsapp_normalizer.py    # Phone number normalisation
│   │   ├── template_studio.py        # AI template generation (Gemini)
│   │   ├── business_agent.py         # AI agent for business-targeted templates
│   │   ├── sheet_templates.py        # Messages-sheet → template extraction
│   │   ├── creative_brief.py         # State languages + brief for AI
│   │   ├── poster_renderer.py        # Chromium-rendered WhatsApp poster images
│   │   ├── gemini_client.py          # Google Gemini API wrapper
│   │   ├── campaign_insights.py      # Campaign performance analysis
│   │   ├── google_sheets.py          # Google Sheets sync
│   │   ├── custom_target.py          # Custom audience targeting
│   │   ├── auth_service.py           # User auth, JWT, password hashing
│   │   ├── notifier.py              # Email notifications (SMTP)
│   │   ├── click_filter.py          # Automated click detection
│   │   └── pricing.py              # WhatsApp message pricing
│   │
│   ├── utils/
│   │   ├── logging.py            # Structured logging setup
│   │   ├── browser_processes.py  # Orphan browser cleanup
│   │   └── connectivity.py      # Internet connectivity checks
│   │
│   └── assets/                   # Static assets (fonts, images for poster rendering)
│
├── frontend/                     # ── React Frontend ──
│   ├── package.json              # React 19, Vite 5, Tailwind CSS v4
│   ├── vite.config.ts            # Dev proxy to backend, base path
│   ├── index.html                # SPA entry point
│   ├── tsconfig.json
│   │
│   └── src/
│       ├── main.tsx              # React entry
│       ├── App.tsx               # Root component, routing, auth context
│       ├── App.css               # App-level styles
│       ├── index.css             # Global styles / Tailwind
│       │
│       ├── views/                # Page-level components
│       │   ├── DashboardView.tsx              # Overview: job stats, engine health
│       │   ├── BusinessesView.tsx             # Searchable business data table
│       │   ├── JobsView.tsx                   # Per-job status, retries, inspector
│       │   ├── ConfigView.tsx                 # Locations & categories management
│       │   ├── WhatsAppCampaignView.tsx       # 4-step campaign builder
│       │   ├── WhatsAppTemplatesView.tsx      # Template compose, edit, submit
│       │   ├── WhatsAppHistoryView.tsx        # Campaign history list
│       │   ├── WhatsAppCampaignDetailView.tsx # Per-campaign detail & delivery
│       │   ├── TemplateStudioView.tsx         # AI template drafting UI
│       │   ├── CampaignInsightsView.tsx       # Insights & playbook
│       │   ├── ApprovalsView.tsx              # Admin: access request management
│       │   └── LoginView.tsx                  # Sign in / sign up / forgot password
│       │
│       ├── components/           # Reusable UI components
│       │   ├── Header.tsx                 # Top bar, theme toggle, account menu
│       │   ├── Sidebar.tsx                # Navigation sidebar
│       │   ├── AutopilotPanel.tsx         # Autopilot controls & status
│       │   ├── DiscoveryRunner.tsx         # Manual batch runner
│       │   ├── AudienceSelector.tsx       # Campaign audience picker
│       │   ├── WhatsAppPreview.tsx        # Live WhatsApp message preview
│       │   ├── MessageBodyEditor.tsx      # Template body editor
│       │   ├── BusinessTemplateAgent.tsx  # AI agent for business templates
│       │   ├── SheetTemplateBuilder.tsx   # Sheet-to-template builder
│       │   ├── DownloadMenu.tsx           # CSV/Excel/Sheets export
│       │   ├── AddLocationForm.tsx        # Add PIN code form
│       │   ├── LeadsPanel.tsx             # Quick-reply leads panel
│       │   ├── JobDistributionDonut.tsx   # Donut chart for job status
│       │   ├── ScaleBars.tsx              # Scale bar visualisation
│       │   ├── StatusBadge.tsx            # Status indicator badges
│       │   ├── CollapsiblePanel.tsx       # Collapsible section
│       │   ├── ThemeToggle.tsx            # Light/dark mode toggle
│       │   ├── BackendSettingsModal.tsx   # Runtime API URL override
│       │   ├── ChangePasswordForm.tsx     # Password change form
│       │   └── ForgotPasswordForm.tsx     # Password reset flow
│       │
│       ├── api/                  # API client functions
│       ├── hooks/                # Custom React hooks
│       ├── types/                # TypeScript type definitions
│       ├── utils/                # Frontend utilities
│       └── assets/               # Static assets
│
├── alembic/                      # ── Database Migrations ──
│   ├── env.py                    # Migration environment
│   ├── script.py.mako            # Migration template
│   └── versions/                 # 17 migration files
│       ├── 0001_initial_schema.py
│       ├── 0e08654b0f18_add_whatsapp_campaign_models.py
│       ├── 1a7c3b9e2d40_add_template_meta_name_and_language.py
│       ├── 2b9f4c7d1e88_add_campaign_link_click_tracking.py
│       ├── 3c1a8e5f7b22_add_template_category.py
│       ├── 4d2b7a9c3e51_template_delete_keeps_history.py
│       ├── 5e3c1d8a4f76_add_business_tehsil.py
│       ├── 6f4d2e9b5a83_add_delivery_lifecycle_and_button_clicks.py
│       ├── 7a5e3c1b9d64_add_app_settings.py
│       ├── 8b6f4d2a1c95_add_users.py
│       ├── 9c7a5e3b2d17_add_whatsapp_replies.py
│       ├── a1d8e6f3c2b4_add_template_studio_fields.py
│       ├── b2e9f7a4d3c5_add_campaign_insights.py
│       ├── c4a7e2d9b8f1_flag_automated_link_hits.py
│       ├── d5b8f3a1c6e2_add_discovery_rounds.py
│       ├── e6c9a4b2d7f3_add_recipient_sheet_variables.py
│       └── f7d1b5c3e8a4_add_user_password_changed_at.py
│
├── n8n/                          # ── Workflow Automation ──
│   └── autonomous_google_maps_daily.json   # Daily scraping + export workflow
│
├── AI_Studio_UI/                 # ── AI Studio Interface (standalone) ──
│   ├── index.html
│   ├── package.json
│   ├── vite.config.ts
│   └── src/                      # Separate frontend for AI Studio features
│
├── data/                         # ── Runtime Data ──
│   ├── gmaps_discovery.db        # SQLite database (development)
│   ├── whatsapp_media/           # Uploaded WhatsApp header media (images/videos)
│   └── backups/                  # Database backups
│
├── docs/                         # ── Technical Documentation ──
│   ├── PROJECT_SPEC.md           # Full project specification
│   ├── API_CONTRACT.md           # REST API contract
│   ├── DATA_MODEL.md             # Database schema documentation
│   ├── DECISION_LOG.md           # Architecture decision records
│   ├── MASTER_CONTEXT.md         # Master context for development
│   └── AI_CONTEXT.md             # AI assistant context
│
├── scripts/                      # ── Utility Scripts ──
│   ├── migrate_data.py           # Data migration helper
│   ├── validate_migration.py     # Migration validation
│   └── smoke_api.py              # API smoke test
│
├── tests/                        # ── Test Suite (35 test files) ──
│   ├── conftest.py               # Shared fixtures
│   ├── test_discovery.py         # Discovery engine tests
│   ├── test_discovery_autopilot.py
│   ├── test_auth.py              # Authentication & authorisation
│   ├── test_whatsapp_module.py   # WhatsApp campaign tests
│   ├── test_whatsapp_delivery_webhook.py
│   ├── test_template_studio.py   # AI template generation
│   ├── test_sheet_templates.py   # Sheet-to-template extraction
│   ├── test_business_agent.py    # Business agent tests
│   ├── test_campaign_insights.py
│   ├── test_email_enricher.py
│   ├── test_export_google_sheets.py
│   └── ... (22 more test files)
│
├── Scraped Data/                 # Historical scraped data exports
└── scraper.db                    # Legacy scraper database
```

---

## 6. Data Model (Key Tables)

| Table | Purpose |
|---|---|
| `locations` | Target PIN codes with lat/lon, state, district, tehsil |
| `categories` | Business categories to search (Kiosk, Print shop, etc.) |
| `jobs` | One row per (location × category) — the work queue |
| `businesses` | Discovered businesses with name, address, phone, website, email, geography |
| `run_logs` | Batch execution history |
| `discovery_rounds` | Autopilot round tracking (state rotation) |
| `whatsapp_accounts` | Connected Meta WhatsApp sending numbers |
| `whatsapp_templates` | Message templates (local + Meta sync) |
| `whatsapp_campaigns` | Campaign metadata |
| `whatsapp_campaign_recipients` | Per-recipient status (sent, delivered, read, clicked) |
| `whatsapp_campaign_logs` | Execution log per message with Meta error codes |
| `whatsapp_link_clicks` | Click tracking records (`/r/<token>` visits) |
| `whatsapp_button_clicks` | Quick-reply button taps attributed via `context.id` |
| `whatsapp_replies` | Free-form replies sent back to button-tap leads |
| `campaign_insights` | Per-campaign performance metrics and suggestions |
| `insight_snapshots` | Playbook snapshots — what has been learned over time |
| `users` | User accounts with role, status, password hash |
| `app_settings` | Persistent application settings |

---

## 7. Key API Endpoints

### Discovery & Data
| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/health` | Liveness + database check |
| `GET` | `/ready` | Readiness probe |
| `GET` | `/api/v1/stats` | System statistics |
| `POST` | `/api/v1/config/sync` | Load locations/categories from xlsx |
| `POST` | `/api/v1/config/locations` | Add a target PIN |
| `POST` | `/api/v1/jobs/generate` | Generate (location × category) job matrix |
| `POST` | `/api/v1/discovery/batch` | Run a batch of discovery jobs |
| `POST` | `/api/v1/discovery/stop` | Stop the running batch |
| `GET` | `/api/v1/businesses` | Paginated business list |
| `GET` | `/api/v1/export/businesses` | Export (CSV / Excel / JSON) |

### WhatsApp Campaigns
| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/v1/whatsapp/accounts/connect` | Verify Meta connectivity |
| `GET/POST` | `/api/v1/whatsapp/templates` | List / create templates |
| `POST` | `/api/v1/whatsapp/campaigns` | Create and send a campaign |
| `POST` | `/api/v1/whatsapp/campaigns/{id}/resume` | Continue for unsent recipients |
| `GET` | `/r/{token}` | Campaign link redirect + click recording |

---

## 8. Deployment Details

### Live Environment
- **Dashboard URL**: [https://indev.eko.in/autogmap/#dashboard](https://indev.eko.in/autogmap/#dashboard)

### Docker Compose (Production)

```bash
# Start all services
docker compose up -d

# Run migrations (first deployment)
docker compose exec backend alembic upgrade head

# Verify
curl http://localhost:8000/health

# View logs
docker compose logs -f backend
```

### Container Resource Limits
- **Backend memory ceiling**: 4 GB (configurable via `BACKEND_MEMORY_LIMIT`)
- **PID limit**: 2048 (prevents fork bombs from runaway browsers)
- **Swap**: capped at same figure as memory, cannot be dodged by paging
- **Init process**: tiny init as PID 1 reaps zombie browser processes

### Ports (localhost-only)
| Service | Default Port | Config Variable |
|---|---|---|
| Backend (FastAPI) | `8000` | `BACKEND_HOST_PORT` |
| PostgreSQL | `55432` (host) / `5432` (internal) | `POSTGRES_HOST_PORT` |
| n8n | `5678` | `N8N_HOST_PORT` |

### Key Environment Variables
| Variable | Purpose |
|---|---|
| `DATABASE_URL` | PostgreSQL connection string |
| `META_ACCESS_TOKEN` | WhatsApp Cloud API token (System User — never expires) |
| `META_PHONE_NUMBER_ID` | Sending number ID |
| `META_WABA_ID` | WhatsApp Business Account ID |
| `GEMINI_API_KEY` | Template Studio AI text generation and checks |
| `HF_TOKEN` | Template Studio AI image generation (Hugging Face Inference API for FLUX.1 Schnell/Dev) |
| `PUBLIC_BASE_URL` | Enables click tracking and webhook |
| `GOOGLE_CREDENTIALS_BASE64` | Google Sheets service account |
| `CORS_ORIGINS` | Allowed frontend origins |

---

## 9. n8n Scheduled Workflow

**File**: `n8n/autonomous_google_maps_daily.json`
**Schedule**: 02:00 UTC daily (07:30 IST)

**Flow**:
1. Health check → fail fast if backend is down
2. Config sync → load locations and categories
3. Job maintenance → recover stale jobs, auto-retry failed
4. Generate jobs → create pending jobs for all (location × category) pairs
5. Check stats → count pending jobs
6. Batch discovery → run `BATCH_SIZE` jobs (Playwright scraping + email enrichment)
7. Export → fetch new businesses since run start
8. Google Sheets → append results to spreadsheet

---

## 10. Security Notes

- **Secrets**: All credentials are env-var based; `.env` is git-ignored
- **CORS**: Strict origins, never `*` with credentials
- **Non-root**: Docker image runs as `appuser` (uid 996)
- **Auth**: JWT sessions, bcrypt password hashing, domain-gated signup
- **Logs**: Never contain passwords, tokens, private keys, or cookie values
- **Browser**: Headless Playwright with container-safe flags, no CAPTCHA solvers
- **Webhook**: Signature-verified via `META_APP_SECRET`

---

## 11. Backup Strategy

| Data | Location | Frequency |
|---|---|---|
| PostgreSQL | `postgres_data` Docker volume | Daily |
| n8n workflows | `n8n_data` Docker volume | After changes |
| Source spreadsheets | Root directory | On change |
| WhatsApp media | `data/whatsapp_media/` | On change |

```bash
# Docker Compose backup
docker compose exec -T postgres \
  pg_dump -U gmap_user -d gmap_scraper --format=custom \
  > gmap_scraper_$(date +%Y%m%d).dump
```

---

## 12. Health Monitoring

```bash
# Liveness
curl http://localhost:8000/health
# → {"status": "healthy", "database": "healthy", "db_backend": "postgresql", ...}

# Readiness
curl http://localhost:8000/ready

# System stats
curl http://localhost:8000/api/v1/stats
```

---

*Document generated from source code analysis of the `G-Map_Data_Scraper_2.0` project.*
