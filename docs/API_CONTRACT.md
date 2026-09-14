# API_CONTRACT.md — FastAPI Endpoint Specifications

> Version: 1.0.0 | Created: 2026-09-14 | Base URL: `http://localhost:8000`

---

## 1. API Design Principles

- **RESTful** with consistent URL patterns
- **JSON** request/response bodies
- **Server-side pagination** on all list endpoints (default: 100 records/page)
- **Consistent error format** across all endpoints
- **No authentication** in Phase 1 (localhost only)
- **API key header** (`X-API-Key`) in Phase 2+

---

## 2. Common Response Models

### Pagination Envelope

All list endpoints return this wrapper:

```json
{
  "items": [...],
  "total": 8468,
  "page": 1,
  "page_size": 100,
  "total_pages": 85,
  "has_next": true,
  "has_prev": false
}
```

### Error Response

```json
{
  "error": {
    "code": "JOB_NOT_FOUND",
    "message": "Job with ID abc123 not found",
    "details": null
  }
}
```

### Standard Status Codes

| Code | Usage |
|------|-------|
| 200  | Success (GET, PUT) |
| 201  | Created (POST that creates resources) |
| 204  | No Content (DELETE) |
| 400  | Bad Request (validation errors) |
| 404  | Not Found |
| 409  | Conflict (duplicate resource) |
| 422  | Unprocessable Entity (Pydantic validation) |
| 500  | Internal Server Error |
| 503  | Service Unavailable (discovery engine busy) |

---

## 3. Endpoints

### 3.1 Health & System

#### `GET /health`

Quick liveness check.

**Response 200:**
```json
{
  "status": "healthy",
  "version": "1.0.0",
  "database": "connected",
  "timestamp": "2026-09-14T08:00:00Z"
}
```

#### `GET /api/v1/stats`

System-wide statistics.

**Response 200:**
```json
{
  "locations_count": 58,
  "categories_count": 146,
  "jobs": {
    "total": 8468,
    "pending": 7200,
    "running": 0,
    "completed": 1100,
    "partial": 50,
    "failed": 118,
    "blocked": 0
  },
  "businesses": {
    "total": 22000,
    "valid": 21500,
    "invalid": 500
  },
  "last_run": {
    "run_id": "uuid",
    "started_at": "2026-09-14T02:00:00Z",
    "status": "COMPLETED",
    "jobs_completed": 50,
    "businesses_new": 750
  }
}
```

---

### 3.2 Configuration

#### `POST /api/v1/config/sync`

Reload source Excel files into the database. Detects new/removed locations and categories.
Does NOT delete existing records — only adds new ones.

**Request body:** None

**Response 200:**
```json
{
  "locations": {
    "total_in_excel": 58,
    "new": 0,
    "existing": 58
  },
  "categories": {
    "total_in_excel": 146,
    "new": 0,
    "existing": 146
  },
  "message": "Configuration synced successfully"
}
```

**Error 500:** Excel file not found or unreadable.

#### `GET /api/v1/config/locations`

List all loaded locations.

**Query params:**

| Param     | Type   | Default | Description |
|-----------|--------|---------|-------------|
| `page`    | int    | 1       | Page number |
| `page_size`| int   | 100     | Records per page (max 500) |
| `pincode` | string | null    | Filter by pincode |
| `state`   | string | null    | Filter by state |

**Response 200:** Paginated list of locations.

```json
{
  "items": [
    {
      "location_id": "a1b2c3d4e5f6",
      "pincode": "244221",
      "latitude": 28.8922129,
      "longitude": 78.4744272,
      "radius_km": 20.0,
      "district": null,
      "state": null,
      "source_dataset": "geocoded_locations",
      "created_at": "2026-09-14T08:00:00Z"
    }
  ],
  "total": 58,
  "page": 1,
  "page_size": 100,
  "total_pages": 1,
  "has_next": false,
  "has_prev": false
}
```

#### `GET /api/v1/config/categories`

List all loaded categories.

**Query params:**

| Param      | Type   | Default | Description |
|------------|--------|---------|-------------|
| `page`     | int    | 1       | Page number |
| `page_size`| int    | 100     | Records per page (max 500) |
| `search`   | string | null    | Search category name |
| `persona`  | string | null    | Filter by persona |

**Response 200:** Paginated list of categories.

```json
{
  "items": [
    {
      "category_id": "x1y2z3w4q5r6",
      "category_name": "Auto insurance agency",
      "persona": null,
      "created_at": "2026-09-14T08:00:00Z"
    }
  ],
  "total": 146,
  "page": 1,
  "page_size": 100,
  "total_pages": 2,
  "has_next": true,
  "has_prev": false
}
```

---

### 3.3 Jobs

#### `POST /api/v1/jobs/generate`

Generate PENDING jobs for all location × category pairs that don't already exist.

**Request body:** None (generates from database state)

**Response 201:**
```json
{
  "jobs_created": 8468,
  "jobs_existing": 0,
  "total_jobs": 8468,
  "message": "Job generation complete"
}
```

**Response 200:** (when no new jobs needed)
```json
{
  "jobs_created": 0,
  "jobs_existing": 8468,
  "total_jobs": 8468,
  "message": "All jobs already exist"
}
```

#### `GET /api/v1/jobs`

List jobs with filters.

**Query params:**

| Param       | Type   | Default  | Description |
|-------------|--------|----------|-------------|
| `page`      | int    | 1        | Page number |
| `page_size` | int    | 100      | Records per page (max 500) |
| `status`    | string | null     | Filter: PENDING, RUNNING, COMPLETED, PARTIAL, FAILED, BLOCKED |
| `location_id`| string| null     | Filter by location |
| `category_id`| string| null     | Filter by category |
| `sort_by`   | string | created_at | Sort field |
| `sort_order`| string | desc     | asc or desc |

**Response 200:** Paginated list of jobs.

```json
{
  "items": [
    {
      "job_id": "abcdef1234567890",
      "location_id": "a1b2c3d4e5f6",
      "category_id": "x1y2z3w4q5r6",
      "status": "PENDING",
      "search_query": "Auto insurance agency",
      "attempt_count": 0,
      "listings_found": null,
      "businesses_saved": null,
      "error_message": null,
      "last_attempt_at": null,
      "completed_at": null,
      "created_at": "2026-09-14T08:00:00Z",
      "location": {
        "pincode": "244221",
        "latitude": 28.8922129,
        "longitude": 78.4744272
      },
      "category": {
        "category_name": "Auto insurance agency"
      }
    }
  ],
  "total": 8468,
  "page": 1,
  "page_size": 100,
  "total_pages": 85,
  "has_next": true,
  "has_prev": false
}
```

#### `GET /api/v1/jobs/{job_id}`

Get single job with full details.

**Response 200:** Single job object (same schema as list item, with nested location and category).

**Response 404:** Job not found.

#### `POST /api/v1/jobs/{job_id}/retry`

Reset a FAILED or BLOCKED job back to PENDING for retry.

**Response 200:**
```json
{
  "job_id": "abcdef1234567890",
  "previous_status": "FAILED",
  "new_status": "PENDING",
  "attempt_count": 2,
  "message": "Job queued for retry"
}
```

**Response 400:** Job is not in a retriable state.

#### `POST /api/v1/jobs/retry-all`

Reset all eligible FAILED/PARTIAL jobs to PENDING.

**Query params:**

| Param  | Type   | Default | Description |
|--------|--------|---------|-------------|
| `status` | string | FAILED | Which status to retry: FAILED, PARTIAL, BLOCKED |

**Response 200:**
```json
{
  "jobs_retried": 42,
  "jobs_skipped": 76,
  "message": "42 jobs queued for retry"
}
```

---

### 3.4 Discovery

#### `POST /api/v1/discovery/batch`

Start a batch discovery run. Picks the next N PENDING jobs and processes them sequentially.
This is a **long-running** endpoint. For n8n, set a long timeout (e.g., 1 hour).

**Request body:**
```json
{
  "batch_size": 50,
  "delay_between_jobs_seconds": 5,
  "delay_between_listings_seconds": 2,
  "trigger_source": "n8n"
}
```

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `batch_size` | int | 50 | Number of PENDING jobs to process |
| `delay_between_jobs_seconds` | int | 5 | Pause between jobs |
| `delay_between_listings_seconds` | int | 2 | Pause between detail pages |
| `trigger_source` | string | "api" | Who triggered: n8n, manual, api |

**Response 200:**
```json
{
  "run_id": "uuid",
  "status": "COMPLETED",
  "jobs_attempted": 50,
  "jobs_completed": 47,
  "jobs_failed": 2,
  "jobs_blocked": 1,
  "businesses_discovered": 940,
  "businesses_new": 875,
  "businesses_updated": 40,
  "businesses_duplicate": 25,
  "duration_seconds": 1523.4,
  "errors": [
    {
      "job_id": "abc123",
      "error": "Timeout waiting for listings"
    }
  ]
}
```

**Response 503:** Discovery engine already running (another batch is in progress).

#### `GET /api/v1/discovery/status`

Check if a discovery batch is currently running.

**Response 200:**
```json
{
  "is_running": true,
  "current_run_id": "uuid",
  "started_at": "2026-09-14T02:00:00Z",
  "jobs_processed": 23,
  "jobs_total": 50,
  "current_job_id": "xyz789"
}
```

#### `POST /api/v1/discovery/stop`

Gracefully stop the current batch. Completes the current job, then stops.

**Response 200:**
```json
{
  "message": "Stop signal sent. Current job will complete before stopping.",
  "run_id": "uuid"
}
```

---

### 3.5 Businesses

#### `GET /api/v1/businesses`

List discovered businesses with filters and server-side pagination.

**Query params:**

| Param        | Type     | Default    | Description |
|--------------|----------|------------|-------------|
| `page`       | int      | 1          | Page number |
| `page_size`  | int      | 100        | Records per page (max 500) |
| `category`   | string   | null       | Filter by category name |
| `district`   | string   | null       | Filter by district |
| `state`      | string   | null       | Filter by state |
| `pincode`    | string   | null       | Filter by source pincode |
| `is_valid`   | boolean  | null       | Filter valid/invalid |
| `search`     | string   | null       | Search name/address |
| `since`      | datetime | null       | Only records discovered after this time |
| `sort_by`    | string   | discovered_at | Sort field |
| `sort_order` | string   | desc       | asc or desc |

**Response 200:** Paginated list of businesses.

```json
{
  "items": [
    {
      "business_id": "1234567890abcdef",
      "name": "Axis Bank ATM",
      "address": "C-104, Block CD, Pitampura, New Delhi, 110034",
      "phone": "7848918181",
      "email": null,
      "website": null,
      "category": "ATM",
      "officename": null,
      "district": "NEW DELHI",
      "state": "DELHI",
      "google_maps_url": "https://www.google.com/maps/place/...",
      "distance_km": 3.2,
      "is_valid": true,
      "discovered_at": "2026-09-14T02:15:00Z"
    }
  ],
  "total": 22000,
  "page": 1,
  "page_size": 100,
  "total_pages": 220,
  "has_next": true,
  "has_prev": false
}
```

> **Critical:** The frontend must use this paginated endpoint.
> Never load the complete dataset into the browser.

#### `GET /api/v1/businesses/{business_id}`

Get single business with full details including internal metadata.

**Response 200:** Full business object.

**Response 404:** Business not found.

---

### 3.6 Export

#### `GET /api/v1/export/businesses`

Export businesses for Google Sheets ingestion via n8n. Returns the **primary fields only**
(name, address, phone, email, website, category, officename, district, statename)
in a flat format suitable for spreadsheet rows.

**Query params:**

| Param      | Type     | Default | Description |
|------------|----------|---------|-------------|
| `since`    | datetime | null    | Only businesses discovered after this time |
| `page`     | int      | 1       | Page number |
| `page_size`| int      | 500     | Larger page size for bulk export (max 1000) |
| `is_valid` | boolean  | true    | Default to valid businesses only |

**Response 200:**
```json
{
  "items": [
    {
      "name": "Axis Bank ATM",
      "address": "C-104, Block CD, Pitampura, New Delhi, 110034",
      "phone": "7848918181",
      "email": null,
      "website": null,
      "category": "ATM",
      "officename": null,
      "district": "NEW DELHI",
      "statename": "DELHI"
    }
  ],
  "total": 875,
  "page": 1,
  "page_size": 500,
  "total_pages": 2,
  "has_next": true,
  "has_prev": false,
  "export_metadata": {
    "exported_at": "2026-09-14T08:00:00Z",
    "filter_since": "2026-09-13T08:00:00Z",
    "valid_only": true
  }
}
```

---

### 3.7 Run Logs

#### `GET /api/v1/runs`

List processing run history.

**Query params:**

| Param      | Type   | Default | Description |
|------------|--------|---------|-------------|
| `page`     | int    | 1       | Page number |
| `page_size`| int    | 20      | Records per page |
| `status`   | string | null    | Filter by status |

**Response 200:** Paginated list of run log entries.

#### `GET /api/v1/runs/{run_id}`

Get detailed run report.

**Response 200:** Full run log entry with error details.

---

## 4. n8n Integration Pattern

### 4.1 Daily Discovery Workflow

```
┌─────────────┐     ┌──────────────────┐     ┌───────────────────┐
│ Cron Trigger │────▶│ HTTP Request     │────▶│ HTTP Request      │
│ (02:00 AM)  │     │ POST /config/sync│     │ POST /jobs/generate│
└─────────────┘     └──────────────────┘     └────────┬──────────┘
                                                       │
                    ┌──────────────────┐                │
                    │ HTTP Request     │◀───────────────┘
                    │ POST /discovery/ │
                    │   batch          │
                    │ (timeout: 3600s) │
                    └────────┬─────────┘
                             │
                    ┌────────▼─────────┐
                    │ HTTP Request     │
                    │ GET /export/     │──── Loop pages until has_next=false
                    │   businesses     │
                    │ ?since=yesterday │
                    └────────┬─────────┘
                             │
                    ┌────────▼─────────┐
                    │ Google Sheets    │
                    │ Append Rows      │
                    └──────────────────┘
```

### 4.2 n8n HTTP Request Configuration

For the discovery batch call:
- **Method:** POST
- **URL:** `http://localhost:8000/api/v1/discovery/batch`
- **Timeout:** 3600000 (1 hour in ms)
- **Body:**
```json
{
  "batch_size": 50,
  "trigger_source": "n8n"
}
```

### 4.3 Google Sheets Export Pagination in n8n

```javascript
// n8n Code node: paginate through export endpoint
let page = 1;
let allItems = [];
let hasNext = true;

while (hasNext) {
  const response = await $http.get(
    `http://localhost:8000/api/v1/export/businesses?since=${yesterday}&page=${page}&page_size=500`
  );
  allItems = allItems.concat(response.data.items);
  hasNext = response.data.has_next;
  page++;
}

return allItems.map(item => ({ json: item }));
```
