PROJECT: Autonomous Google Maps Business Discovery Agent

Build an industrial-level autonomous system for discovering publicly available business information from Google Maps and associated legitimate public business sources.

BUSINESS PURPOSE:

The system discovers franchise-oriented and small-business leads for configured personas/categories around configured target pincodes.

The discovered business data may be used for legitimate business advertising/outreach activities.

Do not bypass CAPTCHA, authentication, access controls, anti-bot/security mechanisms, or collect private/non-public personal information.

==================================================
SOURCE CONFIGURATION
==================================================

SOURCE FILE 1:

Geocoded_Ad_Targeting_Locations_FINAL.xlsx

Relevant sheet:

Geocoded Locations

SOURCE FILE 2:

G-Map Scraper Categories.xlsx

Relevant sheet:

Persona based Categories

These are configuration datasets.

Never hard-code their contents into application code.

Never modify the original source Excel files.

==================================================
LOCATION
==================================================

The location dataset already contains geospatial information.

Preserve it.

Normalized location model should support:

location_id
district
state
tehsil
anchor_village_town
pincode
latitude
longitude
radius_km
pin_basis
coordinate_precision
source_dataset

Default radius:

20 km

==================================================
CATEGORY
==================================================

Category configuration:

category_id
persona
category

==================================================
JOB GENERATION
==================================================

Jobs are generated conceptually as:

LOCATION × CATEGORY

Each job means:

Find businesses matching CATEGORY within approximately RADIUS_KM of the target location.

==================================================
BUSINESS OUTPUT
==================================================

Primary business fields:

name
address
phone
email
website
category
officename
district
statename

The final UI must primarily show these fields.

Internal metadata may additionally be stored for:

business identity
Google Maps URL/place identifier
job ID
source query
timestamps
processing status
errors
deduplication
auditability

==================================================
AUTONOMOUS BEHAVIOR
==================================================

This is NOT a one-time scraper.

The system must eventually:

- run automatically every day
- inspect configured locations/categories
- detect new work
- process only required work
- discover new businesses
- avoid duplicate businesses
- update useful changed information
- retry transient failures
- track processing state
- survive individual job/listing failures
- monitor itself
- produce run summaries
- recover from common failures

Autonomy must primarily come from:

state
rules
scheduling
job management
validation
deduplication
retries
monitoring
incremental processing

Do NOT put an LLM everywhere.

Do NOT build an unnecessary AI-agent framework.

==================================================
ARCHITECTURE
==================================================

Preferred conceptual architecture:

Source Configuration
        ↓
Job Detection/Generation
        ↓
Scheduler / n8n
        ↓
Discovery Engine
        ↓
Geographic Validation
        ↓
Business Extraction
        ↓
Normalization
        ↓
Validation
        ↓
Deduplication
        ↓
Persistence
        ↓
FastAPI
        ↓
Frontend
        ↓
Google Sheets Export

n8n = orchestration/integration.

Discovery engine = browser automation and extraction.

FastAPI = stable backend API.

Frontend = React/TypeScript generated initially through Stitch and refined through Google AI Studio.

==================================================
ENGINEERING PRINCIPLES
==================================================

Priorities:

1. Reliability
2. Simplicity
3. Maintainability
4. Security
5. Extensibility
6. Low operational complexity

Avoid unnecessary:

microservices
queues
AI-agent frameworks
custom implementations
large abstractions
duplicate code

Use mature libraries.

Do not add dependencies without a clear reason.

==================================================
GOOGLE MAPS
==================================================

Google Maps is dynamic.

Selectors must be maintainable and failure-detectable.

Do not rely blindly on selectors such as:

div.Nv2PK
a.hfpxzc

if better robust mechanisms are available.

One failed listing must not stop the entire job.

One failed job must not stop the entire batch.

CAPTCHA/blocking/security mechanisms must cause graceful failure, not bypass attempts.

==================================================
PAGINATION
==================================================

The dataset may become very large.

The frontend must use SERVER-SIDE pagination.

Default:

100 records/page.

Never load the complete dataset into the browser.

==================================================
GOOGLE SHEETS
==================================================

The frontend must have:

Export to Google Sheets

Google credentials must never be exposed to the frontend.

Spreadsheet IDs must not be hard-coded into the scraper.

n8n credentials/environment configuration should handle authentication/configuration.

==================================================
SOURCE OF TRUTH
==================================================

Maintain:

docs/PROJECT_SPEC.md
docs/DATA_MODEL.md
docs/API_CONTRACT.md
docs/AI_CONTEXT.md
docs/DECISION_LOG.md

Every model MUST read these before changing the project.

Every model MUST update AI_CONTEXT.md before finishing its phase.

Never claim something works without testing it.