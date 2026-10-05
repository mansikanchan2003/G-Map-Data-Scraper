/**
 * Centralized API Client for G-Map_Data_Scraper_2.0
 * Connects directly to authoritative FastAPI backend.
 * Zero mocks, zero synthetic data.
 */

import type {
  SystemStatsRaw,
  NormalizedSystemStats,
  DiscoveryStatus,
  BusinessItem,
  JobItem,
  LocationItem,
  CategoryItem,
  PaginatedResponse,
  ConfigSyncResult,
  JobGenerateResult,
  ApiError,
  GoogleSheetsExportResult,
} from '../types/api';

// In production the backend serves this bundle, so the API is same-origin
// under whatever public path the app was built for. In development the Vite
// server is separate and the backend is addressed directly.
const SAME_ORIGIN_BASE = import.meta.env.BASE_URL.replace(/\/+$/, '');
const DEFAULT_BASE_URL =
  import.meta.env.VITE_API_BASE_URL ||
  (import.meta.env.PROD ? SAME_ORIGIN_BASE : 'http://127.0.0.1:8000');
const STORAGE_KEY_API_URL = 'autogmap_api_base_url';

export function getApiBaseUrl(): string {
  if (typeof window !== 'undefined') {
    const saved = localStorage.getItem(STORAGE_KEY_API_URL);
    if (saved) return saved;
  }
  return DEFAULT_BASE_URL;
}

export function setApiBaseUrl(url: string): void {
  if (typeof window !== 'undefined') {
    const trimmed = url.trim().replace(/\/+$/, '');
    localStorage.setItem(STORAGE_KEY_API_URL, trimmed);
  }
}

export function resetApiBaseUrl(): void {
  if (typeof window !== 'undefined') {
    localStorage.removeItem(STORAGE_KEY_API_URL);
  }
}

async function request<T>(endpoint: string, options: RequestInit = {}): Promise<T> {
  const baseUrl = getApiBaseUrl();
  const normalizedEndpoint = endpoint.startsWith('/') ? endpoint : `/${endpoint}`;
  const url = `${baseUrl}${normalizedEndpoint}`;

  const headers = new Headers(options.headers || {});
  if (!headers.has('Accept')) {
    headers.set('Accept', 'application/json');
  }
  if (options.body && typeof options.body === 'string' && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json');
  }

  try {
    const response = await fetch(url, {
      ...options,
      headers,
      // The session is an httpOnly cookie, so it only travels when asked for.
      // In development the API is a different origin to the page, which is
      // why this is "include" rather than "same-origin".
      credentials: 'include',
    });

    if (!response.ok) {
      let errorDetail = `HTTP ${response.status}: ${response.statusText}`;
      try {
        const errorJson = await response.json();
        if (errorJson.detail) {
          errorDetail = typeof errorJson.detail === 'string' 
            ? errorJson.detail 
            : JSON.stringify(errorJson.detail);
        } else if (errorJson.error?.message) {
          errorDetail = errorJson.error.message;
        } else if (errorJson.message) {
          errorDetail = errorJson.message;
        }
      } catch {
        const errorText = await response.text();
        if (errorText) errorDetail = errorText;
      }

      const apiErr: ApiError = {
        message: errorDetail,
        status: response.status,
        endpoint: normalizedEndpoint,
        isNetworkError: false,
      };
      throw apiErr;
    }

    if (response.status === 204) {
      return null as unknown as T;
    }

    return (await response.json()) as T;
  } catch (err: unknown) {
    if ((err as ApiError)?.status !== undefined) {
      throw err;
    }

    const networkErr: ApiError = {
      message: (err instanceof Error) ? err.message : 'Unable to connect to FastAPI backend server.',
      endpoint: normalizedEndpoint,
      isNetworkError: true,
    };
    throw networkErr;
  }
}

// ---------------------------------------------------------
// 1. SYSTEM & HEALTH
// ---------------------------------------------------------

export async function checkBackendHealth(): Promise<{ status: string; latencyMs: number }> {
  const start = performance.now();
  try {
    await request('/health');
    const latencyMs = Math.round(performance.now() - start);
    return { status: 'healthy', latencyMs };
  } catch (err) {
    const latencyMs = Math.round(performance.now() - start);
    throw { ...(err as ApiError), latencyMs };
  }
}

export function normalizeStats(raw: SystemStatsRaw): NormalizedSystemStats {
  return {
    locations_count: raw.locations_count || 0,
    categories_count: raw.categories_count || 0,
    total_jobs: raw.jobs?.total || 0,
    pending_jobs: raw.jobs?.pending || 0,
    running_jobs: raw.jobs?.running || 0,
    completed_jobs: raw.jobs?.completed || 0,
    partial_jobs: raw.jobs?.partial || 0,
    failed_jobs: raw.jobs?.failed || 0,
    blocked_jobs: raw.jobs?.blocked || 0,
    total_businesses: raw.businesses?.total || 0,
    valid_businesses: raw.businesses?.valid || 0,
    invalid_businesses: raw.businesses?.invalid || 0,
    last_run: raw.last_run || null,
  };
}

export async function fetchStats(): Promise<NormalizedSystemStats> {
  const raw = await request<SystemStatsRaw>('/api/v1/stats');
  return normalizeStats(raw);
}

// ---------------------------------------------------------
// 2. DISCOVERY & ORCHESTRATION
// ---------------------------------------------------------

export async function fetchDiscoveryStatus(): Promise<DiscoveryStatus> {
  return request<DiscoveryStatus>('/api/v1/discovery/status');
}

export async function triggerBatchDiscovery(batchSize = 25): Promise<{
  run_id: string;
  status: string;
  jobs_attempted: number;
  jobs_completed: number;
  jobs_failed: number;
  jobs_blocked: number;
  businesses_discovered: number;
  businesses_saved: number;
  duration_seconds: number;
  errors: any[];
}> {
  return request('/api/v1/discovery/batch', {
    method: 'POST',
    body: JSON.stringify({
      batch_size: batchSize,
      delay_between_jobs_seconds: 2.0,
      trigger_source: 'dashboard_ui',
    }),
  });
}

export async function stopDiscovery(): Promise<{ message: string; run_id?: string }> {
  return request('/api/v1/discovery/stop', { method: 'POST' });
}

// ---------------------------------------------------------
// 3. BUSINESSES
// ---------------------------------------------------------

export interface BusinessFilterParams {
  page?: number;
  page_size?: number;
  search?: string;
  category?: string;
  state?: string;
  district?: string;
  pincode?: string;
  is_valid?: boolean;
}

export async function fetchBusinesses(params: BusinessFilterParams = {}): Promise<PaginatedResponse<BusinessItem>> {
  const query = new URLSearchParams();
  const page = params.page || 1;
  const pageSize = params.page_size || 100;

  query.set('page', String(page));
  query.set('page_size', String(pageSize));

  if (params.search?.trim()) query.set('search', params.search.trim());
  if (params.category && params.category !== 'All') query.set('category', params.category);
  if (params.state && params.state !== 'All') query.set('state', params.state);
  if (params.district && params.district !== 'All') query.set('district', params.district);
  if (params.pincode?.trim()) query.set('pincode', params.pincode.trim());
  if (params.is_valid !== undefined) query.set('is_valid', String(params.is_valid));

  return request<PaginatedResponse<BusinessItem>>(`/api/v1/businesses?${query.toString()}`);
}

/**
 * Triggers native streaming download of all businesses directly from FastAPI.
 * Zero browser memory allocation or client-side CSV parsing.
 */
export function triggerCsvStream(): void {
  const baseUrl = getApiBaseUrl();
  const url = `${baseUrl}/api/v1/export/businesses?format=csv`;
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.setAttribute('download', `businesses_export_${new Date().toISOString().slice(0, 10)}.csv`);
  anchor.target = '_blank';
  document.body.appendChild(anchor);
  anchor.click();
  document.body.removeChild(anchor);
}

/**
 * Triggers native streaming download of all businesses in Excel (XLSX) format.
 */
export function triggerExcelStream(): void {
  const baseUrl = getApiBaseUrl();
  const url = `${baseUrl}/api/v1/export/businesses?format=excel`;
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.setAttribute('download', `businesses_export_${new Date().toISOString().slice(0, 10)}.xlsx`);
  anchor.target = '_blank';
  document.body.appendChild(anchor);
  anchor.click();
  document.body.removeChild(anchor);
}

/**
 * Creates a new Google Sheet on the server side using FastAPI and returns the URL.
 */
export interface LiveSheetInfo {
  configured: boolean;
  url: string | null;
  title: string;
  shared_with: string | null;
  /** Why there is no sheet yet, when configured is false. */
  reason: string | null;
}

export interface LiveSheetSyncResult extends LiveSheetInfo {
  created: boolean;
  rows: number;
}

/** Where the live sheet is. Never creates one. */
export async function fetchLiveSheet(): Promise<LiveSheetInfo> {
  return request<LiveSheetInfo>('/api/v1/export/google-sheets/link');
}

/** Creates the sheet if needed, then rewrites it from the database. */
export async function syncLiveSheet(): Promise<LiveSheetSyncResult> {
  return request<LiveSheetSyncResult>('/api/v1/export/google-sheets/sync', { method: 'POST' });
}

export async function exportToGoogleSheets(
  filters: Record<string, any> = {},
  selectedIds: string[] = [],
  exportAll: boolean = false
): Promise<GoogleSheetsExportResult> {
  return request<GoogleSheetsExportResult>('/api/v1/export/google-sheets', {
    method: 'POST',
    body: JSON.stringify({
      filters,
      selected_ids: selectedIds,
      export_all: exportAll
    }),
  });
}

// ---------------------------------------------------------
// 4. JOBS
// ---------------------------------------------------------

export interface JobFilterParams {
  page?: number;
  page_size?: number;
  status?: string;
}

export async function fetchJobs(params: JobFilterParams = {}): Promise<PaginatedResponse<JobItem>> {
  const query = new URLSearchParams();
  const page = params.page || 1;
  const pageSize = params.page_size || 100;

  query.set('page', String(page));
  query.set('page_size', String(pageSize));

  if (params.status && params.status !== 'All') {
    query.set('status', params.status.toUpperCase());
  }

  return request<PaginatedResponse<JobItem>>(`/api/v1/jobs?${query.toString()}`);
}

export async function runJob(jobId: string): Promise<{ success?: boolean; message?: string; [key: string]: any }> {
  return request(`/api/v1/jobs/${jobId}/run`, { method: 'POST' });
}

export async function retryJob(jobId: string): Promise<{ job_id: string; previous_status: string; new_status: string; message: string }> {
  return request(`/api/v1/jobs/${jobId}/retry`, { method: 'POST' });
}

export async function retryAllFailedJobs(status = 'FAILED'): Promise<{ jobs_retried: number; jobs_skipped?: number; message: string }> {
  return request(`/api/v1/jobs/retry-all?status=${status}`, { method: 'POST' });
}

// ---------------------------------------------------------
// 5. CONFIGURATION
// ---------------------------------------------------------

export async function fetchConfigLocations(page = 1, pageSize = 100): Promise<PaginatedResponse<LocationItem>> {
  return request<PaginatedResponse<LocationItem>>(`/api/v1/config/locations?page=${page}&page_size=${pageSize}`);
}

export async function fetchConfigCategories(page = 1, pageSize = 100): Promise<PaginatedResponse<CategoryItem>> {
  return request<PaginatedResponse<CategoryItem>>(`/api/v1/config/categories?page=${page}&page_size=${pageSize}`);
}

export interface ResolvedPlace {
  place: string;
  latitude: number;
  longitude: number;
  resolved_name?: string | null;
  /** Maps names the state for a PIN code; it never names the district. */
  state?: string | null;
  pincode?: string | null;
  radius_km: number;
}

export interface LocationCreatePayload {
  pincode: string;
  state: string;
  district: string;
  tehsil?: string | null;
  anchor_name?: string | null;
  latitude?: number | null;
  longitude?: number | null;
  radius_km?: number | null;
}

/** Look a place up without saving it, so the add form can be filled in. */
export async function resolveLocation(place: string): Promise<ResolvedPlace> {
  return request<ResolvedPlace>('/api/v1/config/locations/resolve', {
    method: 'POST',
    body: JSON.stringify({ place }),
  });
}

export async function createLocation(payload: LocationCreatePayload): Promise<LocationItem> {
  return request<LocationItem>('/api/v1/config/locations', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export async function deleteLocation(locationId: string): Promise<{ status: string }> {
  return request(`/api/v1/config/locations/${locationId}`, { method: 'DELETE' });
}

export async function syncConfiguration(): Promise<ConfigSyncResult> {
  return request<ConfigSyncResult>('/api/v1/config/sync', { method: 'POST' });
}

export async function generateJobQueue(): Promise<JobGenerateResult> {
  return request<JobGenerateResult>('/api/v1/jobs/generate', { method: 'POST' });
}

// --- On-demand discovery ----------------------------------------------------

export interface DiscoveryTarget {
  value: string;
  label: string;
  pending: number;
  done: number;
}

export interface DiscoveryTargets {
  states: string[];
  locations: DiscoveryTarget[];
  categories: DiscoveryTarget[];
}

export const fetchDiscoveryTargets = async (state?: string): Promise<DiscoveryTargets> => {
  const qs = state ? `?state=${encodeURIComponent(state)}` : '';
  return request<DiscoveryTargets>(`/api/v1/discovery/targets${qs}`);
};

/** Runs existing queued jobs for the chosen locations and categories. */
export const runTargetedDiscovery = async (body: {
  anchor_names?: string[];
  categories?: string[];
  states?: string[];
  batch_size: number;
  delay_between_jobs_seconds: number;
}): Promise<any> => {
  return request('/api/v1/discovery/batch', {
    method: 'POST',
    body: JSON.stringify({ ...body, trigger_source: 'dashboard', run_in_background: true }),
  });
};

/** Adds places and categories that are not in the spreadsheets, then runs them. */
export const runCustomDiscovery = async (body: {
  places: { place: string; latitude?: number | null; longitude?: number | null; radius_km?: number | null }[];
  categories: string[];
  batch_size: number;
  delay_between_jobs_seconds: number;
  run_now: boolean;
}): Promise<any> => {
  return request('/api/v1/discovery/custom-run', {
    method: 'POST',
    body: JSON.stringify(body),
  });
};

// ---------------------------------------------------------
// 9. AUTHENTICATION
// ---------------------------------------------------------

export interface AuthUser {
  user_id: string;
  email: string;
  full_name: string | null;
  role: 'admin' | 'member';
  status: 'PENDING' | 'APPROVED' | 'REJECTED' | 'DISABLED';
  created_at: string;
  decided_by: string | null;
  decided_at: string | null;
  last_login_at: string | null;
}

export interface SignupResult {
  status: string;
  email: string;
  message: string;
}

/** Records a request for access. Never signs anyone in. */
export async function signup(email: string, password: string, fullName?: string): Promise<SignupResult> {
  return request<SignupResult>('/api/v1/auth/signup', {
    method: 'POST',
    body: JSON.stringify({ email, password, full_name: fullName || null }),
  });
}

export async function login(email: string, password: string): Promise<AuthUser> {
  return request<AuthUser>('/api/v1/auth/login', {
    method: 'POST',
    body: JSON.stringify({ email, password }),
  });
}

export async function logout(): Promise<void> {
  await request('/api/v1/auth/logout', { method: 'POST' });
}

/** The signed-in user, or null when there is no valid session. */
export async function fetchMe(): Promise<AuthUser | null> {
  try {
    return await request<AuthUser>('/api/v1/auth/me');
  } catch {
    return null;
  }
}

export async function fetchUsers(status?: string): Promise<AuthUser[]> {
  const q = status ? `?status=${encodeURIComponent(status)}` : '';
  return request<AuthUser[]>(`/api/v1/auth/users${q}`);
}

export async function approveUser(userId: string): Promise<AuthUser> {
  return request<AuthUser>(`/api/v1/auth/users/${userId}/approve`, { method: 'POST' });
}

export async function rejectUser(userId: string, reason?: string): Promise<AuthUser> {
  return request<AuthUser>(`/api/v1/auth/users/${userId}/reject`, {
    method: 'POST',
    body: JSON.stringify({ reason: reason || null }),
  });
}

// ---------------------------------------------------------
// 10. LEADS (quick-reply taps)
// ---------------------------------------------------------

export interface Reply {
  reply_id: string;
  body: string;
  status: string;
  error_reason: string | null;
  sent_by: string | null;
  sent_at: string;
}

export interface Lead {
  click_id: string;
  name: string | null;
  phone: string | null;
  category: string | null;
  district: string | null;
  state: string | null;
  campaign: string | null;
  button_text: string | null;
  clicked_at: string;
  /** After this, only an approved template can reach the number. */
  window_expires_at: string;
  replies: Reply[];
}

/** People who asked to be called back, newest first. */
export async function fetchLeads(limit = 20): Promise<Lead[]> {
  return request<Lead[]>(`/api/v1/whatsapp/leads?limit=${limit}`);
}

/**
 * Answer a callback request from the business number.
 *
 * Only works inside Meta's 24-hour window; outside it the server refuses with
 * a message explaining why, which is worth showing verbatim.
 */
export async function replyToLead(clickId: string, message: string): Promise<Reply> {
  return request<Reply>(`/api/v1/whatsapp/leads/${clickId}/reply`, {
    method: 'POST',
    body: JSON.stringify({ message }),
  });
}

// ---------------------------------------------------------
// Scraping autopilot — rounds of batches, one state at a time.
// ---------------------------------------------------------

export interface AutopilotSettings {
  enabled: boolean;
  batch_size: number;
  batches_per_round: number;
  gap_between_rounds_minutes: number;
  gap_between_batches_seconds: [number, number];
  job_delay_seconds: number;
  job_delay_jitter_seconds: number;
  daily_batch_target: number;
  continue_after_target: boolean;
  states: string[];
}

export interface AutopilotBatch {
  batch: number;
  location_id: string;
  anchor: string | null;
  pincode: string | null;
  district: string | null;
  tehsil: string | null;
  categories: string[];
  /** PLANNED, RUNNING, DONE, or SKIPPED after repeated CAPTCHAs. */
  status: string;
  blocks: number;
  run_id: string | null;
  started_at: string | null;
  completed_at: string | null;
  jobs_completed: number;
  businesses_saved: number;
  jobs: number;
  jobs_finished: number;
}

export interface AutopilotRound {
  round_id: string;
  state: string;
  status: string;
  batches_done: number;
  batches: number;
  plan: AutopilotBatch[];
  created_at: string | null;
  completed_at: string | null;
}

export interface AutopilotStatus {
  settings: AutopilotSettings;
  state: {
    /** What it is doing right now: off, running_batch, gap_between_batches,
     *  gap_between_rounds, captcha_cooldown, daily_target_reached, ... */
    phase: string;
    captcha_level: number;
    clean_streak: number;
    cooldown_until: string | null;
    offline_until?: string | null;
    offline_level?: number;
    next_batch_at: string | null;
    next_round_at?: string | null;
    current_batch?: number;
    last_event: string | null;
    last_event_at: string | null;
  };
  now: string;
  today: {
    batches_done: number;
    target: number;
    jobs: number;
    businesses_saved: number;
    captchas: number;
    avg_batch_seconds: number | null;
    target_eta: string | null;
  };
  pending_by_state: Record<string, number>;
  rounds: AutopilotRound[];
}

export const fetchAutopilot = () => request<AutopilotStatus>('/api/v1/discovery/autopilot');

export const updateAutopilot = (changes: Partial<AutopilotSettings>) =>
  request<AutopilotStatus>('/api/v1/discovery/autopilot', { method: 'PUT', body: JSON.stringify(changes) });

export const clearAutopilotCooldown = () =>
  request<AutopilotStatus>('/api/v1/discovery/autopilot/clear-cooldown', { method: 'POST' });
