# AutoGMap Acquisition Platform

**Finds local businesses on Google Maps, reaches them through WhatsApp campaigns, and
onboards interested owners as banking agents (CSPs).** A multilingual bot handles the
conversation, then the app collects documents, runs follow-ups and calls, and tracks
every lead from discovery to hand-over.

AutoGMap is built for agent-network businesses such as banks, business correspondents
and fintechs. They grow by finding people in the right places who can run a banking
outlet, and by turning them into active agents.

```
Google Maps ──► Businesses ──► WhatsApp campaign ──► "Interested" ──► Onboarding bot
                                                                         │
     Hand-over to the acquisition team ◄── Applications & follow-ups ◄── Documents
```

---

## Contents

- [What it does](#what-it-does)
- [How it is built](#how-it-is-built)
- [Tech stack](#tech-stack)
- [Repository layout](#repository-layout)
- [Quick start (local development)](#quick-start-local-development)
- [Configuration](#configuration)
- [Running in production](#running-in-production)
- [Operating it](#operating-it)
- [Testing](#testing)
- [Security and privacy](#security-and-privacy)
- [Further documentation](#further-documentation)
- [Contributing](#contributing)

---

## What it does

### 1. Discovery: finding businesses on Google Maps

- **Searches.** Target places (PIN codes with coordinates) and business categories are
  loaded from two spreadsheets. Each place × category pair becomes a *job*: one Google
  Maps search such as "Insurance agency near 360050".
- **Scraping.** A headless Chromium (Playwright) reads every listing: name, phone,
  website, address, category and position.
  - Results are normalised, checked against the target area and de-duplicated.
  - An email is looked for on the business's own website. Social, directory and Google
    links are skipped.
- **Autopilot.** Batches run on their own, state by state:
  - a daily target, gaps between batches, and retries for failed jobs first;
  - CAPTCHA cool-downs and a pause when the network is down;
  - the round plan is saved, so a restart resumes where it stopped.
- **Hiring targets.** A search can be for agents (CSP), for agents near a District
  Coordinator, for District Coordinators, or for state heads. Each business carries a
  flag for what it was found for.
- **Bank branches.** A branch code is turned into a PIN code (through its IFSC), and
  that branch's surroundings are searched.
- **Exports.** Excel, CSV and an optional live Google Sheet.

### 2. Campaigns: reaching businesses on WhatsApp

- **Sending.** Approved templates go out through the **Meta WhatsApp Cloud API**. Every
  template carries two quick-reply buttons: **"Interested"** and a request for
  **personal guidance**, in the campaign's language.
- **Tracking.** Each recipient gets a tracking link. A click is recorded (with a hashed
  IP and bot filtering) and redirected to the sign-up page with UTM tags.
- **Delivery status.** Sent, delivered, read and failed come back by webhook, and
  campaign counts are kept accurate.
- **Safety:**
  - **maker-checker:** large campaigns wait for a second person's approval;
  - a global kill switch;
  - opt-outs (STOP) are honoured, including Meta's own;
  - sending resumes safely after a restart.

### 3. Conversation: the Inbox and the onboarding bot

- **Inbox.** One place for every WhatsApp chat. It shows media, voice notes transcribed
  on the server (Whisper, no external API), the 24-hour window, ready replies and a
  plain-language chat summary.
- **Onboarding bot.** It walks an interested person through:
  1. their language (English, Hindi and the campaign's language; more Indian languages
     are supported);
  2. their PIN code, checked against the service area;
  3. their education;
  4. their ability to invest, with an explainer video or text;
  5. their documents.
- **A lower-investment programme** is offered to anyone who cannot afford the main one,
  at whatever step they say so.
- **Personal guidance.** Questions are answered from a curated FAQ in the person's own
  language. A question the bot cannot answer raises a **ticket**, emails the team, and
  can be answered by an AI model that only drafts answers, under strict wording rules.
- **Reminders.** A person who goes quiet gets one reminder an hour later, only inside
  WhatsApp's 24-hour window.
- **Taking over.** A team member can pause the bot for a chat and hand it back later.

### 4. Documents

- **How they come in.** An upload page with a personal link (PDF, JPG or PNG, checked
  by content, not by name), photos sent in the chat (read with OCR and classified), or
  DigiLocker.
- **Where they go.** Into a per-person folder in a **Google Drive shared drive**. The
  server copy is deleted once Drive holds it.
- **Who is told.** The team gets an email summary (never the files themselves) and a
  ticket.

### 5. Applications, dispositions and calls (CRM)

- **Applications.** Everyone who started applying, with qualification, the nearest
  branch, documents, interest level, comments and the campaign they came from.
- **Dispositions.** An 11-category scheme (Interested, Not interested, Busy/Callback,
  RNR, …). Each disposition plans its own follow-ups (WhatsApp nudges, callbacks, team
  tasks) and retries.
- **Calls:**
  - AI calls come back by webhook;
  - a call-recorder app uploads recordings, which are transcribed on the server;
  - a choice made in a call updates the disposition.
- **Lead journey.** Every stage with its time, kept for reporting. Dashboard alerts flag
  leads whose steps do not add up.
- **Hand-over** to the acquisition team's API once documents are in.

### 6. Template Studio

- **AI drafts.** Template copy and posters are drafted with free AI models: Google
  Gemini's free tier for text, FLUX on Hugging Face for images, real uploaded photos
  first.
- **Checks.** A word-rule checker blocks drafts that over-promise, use banned words or
  misspell the image text.
- **Approval.** Nothing reaches Meta without a person's approval.

### 7. Insights and growth plan

- **Campaign insights.** Which template, angle, place, category and send time moved
  people furthest down the funnel, with evidence thresholds so that thin data is not
  over-read.
- **Growth plan.** A lead goal set from the business's own figures, a revenue goal,
  funnel leaks, a call list and suggested next steps.

### 8. Administration

- **Sign-in.** Email and password, or Google, restricted to the organisation's domain.
- **Access requests.** People request access and an admin approves them. An admin can
  also **create users** directly.
- **Roles:**
  - *member*: view only;
  - *operator*: full working access;
  - *manager*: also approves large campaigns;
  - *admin*.
- **Narrower access.** An account can be limited to chosen tabs and to part of the
  Inbox.
- **Agent Quality:**
  - what every AI or automatic step did and what a person did with it;
  - a golden test set of real conversations;
  - an on/off **switch for every automatic action**;
  - **System health**, which shows whether the website, worker and scraper are alive;
  - an audit log of every change.

---

## How it is built

One codebase and one Docker image, run as three containers. The process's
`APP_ROLE` decides what each container runs (`src/roles.py`):

| Container | `APP_ROLE` | Runs |
|---|---|---|
| `backend` | `api` | The website, REST API, WhatsApp webhook, bot and Inbox |
| `worker` | `worker` | Reminders, follow-ups, journey and report sync, call recordings, Studio photo queue |
| `scraper` | `scraper` | Google Maps in Chrome: the autopilot and queued batches, behind its own memory limit |

- **Work queue.** The API never opens a browser. Scraping requests go into a work queue
  in the database (`queued_tasks`), which the scraper claims with `SKIP LOCKED`. A
  stuck browser therefore stops scraping, never the website.
- **Memory guard.** Kills the scraper's browsers before the container runs out of memory.
- **One process for development.** `APP_ROLE=all` (the default) runs everything in one
  process, for development, tests and staging.

The code is a **modular monolith** (see [ARCHITECTURE.md](ARCHITECTURE.md)). Every file
belongs to one module, listed in `src/architecture/modules.py`:

| Module | Owns |
|---|---|
| platform | database, settings, sign-in, audit, switches, work queue, health |
| integrations | adapters to WhatsApp, Gemini, Google Drive and Sheets, email, DigiLocker, the hand-over API, speech-to-text |
| discovery | places, categories, jobs, the scraper and its autopilot |
| campaigns | templates, campaigns, tracking links, opt-outs |
| conversation | Inbox, onboarding bot, FAQ, tickets, reminders |
| crm | applications, dispositions, follow-ups, calls, lead journey |
| studio | AI templates and posters |
| insights | campaign insights, growth plan |

A test (`tests/test_architecture.py`) fails on any new import that reaches across
modules. Adapters may never import business code.

---

## Tech stack

| Layer | Technology |
|---|---|
| Backend | Python 3.12, FastAPI, SQLAlchemy, Alembic, Pydantic |
| Database | PostgreSQL 16 (production), SQLite (development and tests) |
| Scraping | Playwright with headless Chromium, psutil for browser clean-up |
| Messaging | Meta WhatsApp Cloud API (templates, webhook, media) |
| AI | Google Gemini API (free tier) for text and image checks, FLUX on Hugging Face Spaces for images, faster-whisper for speech, Tesseract for OCR |
| Frontend | React 19, TypeScript, Vite, Tailwind CSS v4, served by the backend |
| Google | Drive (documents), Sheets (live export), Google Sign-In |
| Ops | Docker Compose, GitHub Actions CI, deploy and rollback scripts |

---

## Repository layout

```
├── src/
│   ├── main.py              # FastAPI app: routers, middleware, the built frontend
│   ├── roles.py             # what each container runs (APP_ROLE)
│   ├── background.py        # starts this role's background threads
│   ├── worker.py            # entrypoint of the worker and scraper containers
│   ├── architecture/        # module map and the boundary checker
│   ├── routers/             # HTTP endpoints, one file per area
│   ├── services/            # business logic and adapters
│   ├── models/              # SQLAlchemy models
│   ├── schemas/             # Pydantic schemas
│   ├── evals/               # golden test set of bot conversations
│   └── utils/               # logging, connectivity, browser processes
├── alembic/                 # database migrations
├── frontend/                # React app (built into the backend image)
├── tests/                   # pytest suite
├── scripts/                 # deploy, rollback, staging, data export helpers
├── n8n/                     # optional n8n workflow for scheduled batches
├── docs/                    # early design documents (older than the code)
├── Dockerfile
├── docker-compose.yml       # backend, worker, scraper, postgres, n8n
├── docker-compose.staging.yml
└── .env.example             # every setting, with placeholders
```

---

## Quick start (local development)

### Prerequisites

- Python 3.12, Node.js 20+, Git
- Optional: Docker, and Tesseract OCR (for reading documents sent in chats)

### 1. Clone and configure

```bash
git clone https://github.com/ekoindia/autogmap-acquisition-platform.git
cd autogmap-acquisition-platform
cp .env.example .env
```

The defaults use SQLite and a mocked WhatsApp API, so nothing reaches a real person.
Set `BOOTSTRAP_ADMIN_PASSWORD` in `.env` to sign in as the first admin.

### 2. Backend

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
playwright install chromium
alembic upgrade head               # or let the app create the tables on start
uvicorn src.main:app --reload --port 8000
```

Check it at http://localhost:8000/health.

### 3. Frontend

```bash
cd frontend
npm install
npm run dev                        # http://localhost:5173
```

### 4. Load targets and run a first search

In the app, open **Configuration** and sync the locations and categories, then run a
batch from the **Dashboard**. You can also use the API:

```bash
curl -X POST http://localhost:8000/api/v1/config/sync
curl -X POST http://localhost:8000/api/v1/discovery/batch \
     -H "Content-Type: application/json" -d '{"batch_size": 5}'
```

Interactive API docs are at http://localhost:8000/docs.

---

## Configuration

All settings come from environment variables. `.env.example` lists every one with a
placeholder. **Never commit a real `.env`.** The main groups:

| Group | Variables |
|---|---|
| Database | `DATABASE_URL`, `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD` |
| App and roles | `APP_ROLE`, `ENVIRONMENT`, `PUBLIC_BASE_URL`, `CORS_ORIGINS`, `LOG_LEVEL`, `BACKEND_MEMORY_LIMIT`, `WORKER_MEMORY_LIMIT`, `SCRAPER_MEMORY_LIMIT` |
| Sign-in | `AUTH_JWT_SECRET`, `BOOTSTRAP_ADMIN_PASSWORD`, `GOOGLE_CLIENT_ID` |
| Discovery | `LOCATIONS_FILE`, `CATEGORIES_FILE`, `BATCH_SIZE`, `JOB_TIMEOUT_SECONDS`, `BROWSER_TIMEOUT_MS`, `MAX_RESULTS_PER_JOB`, `EMAIL_MAX_CONCURRENCY`, `EMAIL_ENRICHMENT_*` |
| WhatsApp | `META_ACCESS_TOKEN`, `META_PHONE_NUMBER_ID`, `META_WABA_ID`, `META_APP_SECRET`, `META_WEBHOOK_VERIFY_TOKEN`, `META_API_VERSION`, `MOCK_WHATSAPP_API`, `WHATSAPP_BUSINESS_NUMBER` |
| Campaigns | `CAMPAIGN_LINK_TARGET_URL`, `CAMPAIGN_LINK_FALLBACK_URL`, `CAMPAIGN_LINK_HASH_SALT`, `CAMPAIGN_UTM_SOURCE`, `CAMPAIGN_UTM_MEDIUM`, `CAMPAIGN_APPROVAL_MIN` |
| Bot and Inbox | `ONBOARDING_RADIUS_KM`, `WHISPER_MODEL`, `WHISPER_HINDI_MODEL`, `WHISPER_IDLE_MINUTES`, `INBOX_MEDIA_DIR`, `ONBOARDING_DOCS_DIR` |
| Google | `GOOGLE_CREDENTIALS_BASE64`, `GOOGLE_DRIVE_FOLDER_ID`, `GOOGLE_SHEET_ID`, `GOOGLE_SHEET_OWNER_EMAIL` |
| Email | `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM`, `NOTIFY_ALSO` |
| AI | `GEMINI_API_KEY`, `GEMINI_MODELS`, `HF_TOKEN` |
| DigiLocker | `EKO_DEVELOPER_KEY`, `EKO_ACCESS_KEY`, `EKO_INITIATOR_ID`, `EKO_BASE_URL`, `EKO_DIGILOCKER_DOCUMENTS` |
| Hand-over | `EKO_ACQUISITION_API_URL`, `EKO_ACQUISITION_API_KEY` |
| Calls | `CALL_RECORDER_API_KEY`, `CALL_RECORDINGS_SOURCE_URL`, `CALL_RECORDINGS_SOURCE_KEY`, `TRANSCRIBE_CALLS` |
| Privacy | `PRIVACY_CONTACT_EMAIL` |

Every outside service is optional. If it is not configured, its feature switches off
and says so, and the rest keeps working.

---

## Running in production

### Docker Compose

```bash
cp .env.example .env        # fill in real values; keep this file private (chmod 600)
docker compose build
docker compose run --rm backend alembic upgrade head
docker compose up -d backend worker scraper postgres
curl http://127.0.0.1:${BACKEND_HOST_PORT:-8000}/health
```

- **Network exposure.** Every port binds to `127.0.0.1`. Put a reverse proxy with TLS
  in front of `backend`, and set `PUBLIC_BASE_URL` to the public address.
- **Frontend path.** The frontend is built into the image. `VITE_BASE_PATH` serves it
  under a sub-path.
- **WhatsApp webhook.** Point the Meta app's webhook at
  `https://<your-domain>/api/v1/whatsapp/webhook`, using `META_WEBHOOK_VERIFY_TOKEN`.
  Every call is checked against `META_APP_SECRET`.

### Deploying updates

`scripts/deploy.sh` deploys the newest `main` the same way every time:

1. It stops unless CI is green.
2. It waits for the gap between scraping batches.
3. It runs the golden test set on the new image.
4. It backs up the database and runs the migrations.
5. It starts every container and waits for the health check.

`scripts/rollback.sh` returns to the previous version. `scripts/staging.sh` runs a
separate staging copy in which nothing can reach a real person.

---

## Operating it

- **System health** (Agent Quality, also shown in the sidebar):
  - whether the website, worker and scraper are running;
  - their memory and threads;
  - their recent errors;
  - the scraping queue and the last batch.
- **Logs.** `docker compose logs backend|worker|scraper --since 15m`.
- **Kill switches.** Agent Quality → Controls. Every automatic action has its own
  switch: campaign sending, bot replies, reminders, follow-ups, AI drafting, DigiLocker
  and more. The scraping autopilot has its own switch on the Dashboard.
- **Retention.** Admin-confirmed deletion of personal data after a set period.
  Server files are deleted, Drive copies are moved to the trash, and message text is
  redacted.

---

## Testing

```bash
pytest -q                                  # the whole suite (about 1,300 tests)
python -m src.evals.golden                 # golden set of real bot conversations
python -m src.architecture.boundaries      # module boundary report
cd frontend && npm run build               # type-check and build the frontend
```

GitHub Actions runs the test suite, the golden set and the frontend build on every
push. Deploys refuse a commit whose CI is not green.

---

## Security and privacy

- **No secrets in the repository.**
  - Keys, tokens and passwords live only in `.env`, which is git-ignored, as are
    service-account files, certificates and databases.
  - `.env.example` holds placeholders only.
- **No personal data in the repository.** The following are all git-ignored:
  - scraped business data and exports;
  - chat media, uploaded documents and call recordings;
  - database backups.
- **Identity documents** are kept in a Google Drive shared drive, not on the server.
  They are never attached to emails, and the hand-over sends Drive links, not files.
- **Sign-in.** Every API route needs a session (an httpOnly, signed cookie) except:
  - the WhatsApp webhook, checked by Meta's signature;
  - the call webhooks, checked by shared secrets;
  - tracking redirects and the personal upload page, checked by their tokens.
- **Least privilege.**
  - View-only members cannot change anything; the server enforces it.
  - Admin-only actions are checked on the server.
  - Every change is audited.
- **Opt-outs.** STOP and Meta's own opt-outs are honoured before any message is sent.

To report a security issue, please contact the maintainers privately rather than
opening a public issue.

---

## Further documentation

| File | About |
|---|---|
| [ARCHITECTURE.md](ARCHITECTURE.md) | Modules, their rules, and the plan from monolith to modules |
| [DEPLOYMENT.md](DEPLOYMENT.md) | Deploying, going back, staging, and what to do when something goes wrong |
| [LEAD_JOURNEY.md](LEAD_JOURNEY.md) | The lead's journey through the bot |
| [PROJECT_DOCUMENTATION.md](PROJECT_DOCUMENTATION.md) | Longer project notes |
| `docs/` | Early design documents. Where they disagree with the code, the code is right. |

---

## Contributing

1. Branch from `main` and open a pull request. CI must be green, and a review is
   expected before merging.
2. Keep each change to one module where you can. Do not add imports across modules
   (`tests/test_architecture.py` will fail).
3. Add or update tests with the change. Add a migration for any schema change
   (`alembic revision`).
4. Never commit `.env`, data exports, chat media, documents or anything with a real
   person's name, phone or email.
