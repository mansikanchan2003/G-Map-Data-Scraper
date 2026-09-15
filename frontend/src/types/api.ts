/**
 * Authoritative TypeScript types matching FastAPI backend contracts
 * and schemas for G-Map_Data_Scraper_2.0
 */

export interface LocationItem {
  location_id: string;
  pincode: string;
  latitude: number;
  longitude: number;
  radius_km: number;
  district?: string | null;
  state?: string | null;
  source_dataset?: string | null;
  created_at?: string;
}

export interface CategoryItem {
  category_id: string;
  category_name: string;
  persona?: string | null;
  created_at?: string;
}

export type JobStatus = 'PENDING' | 'RUNNING' | 'COMPLETED' | 'PARTIAL' | 'FAILED' | 'BLOCKED';

export interface JobItem {
  job_id: string;
  location_id: string;
  category_id: string;
  status: JobStatus;
  search_query: string;
  attempt_count: number;
  max_retries?: number;
  listings_found?: number | null;
  businesses_saved?: number | null;
  error_message?: string | null;
  blocked_reason?: string | null;
  last_attempt_at?: string | null;
  completed_at?: string | null;
  created_at: string;
  updated_at: string;
  location?: LocationItem | null;
  category?: CategoryItem | null;
}

export interface BusinessItem {
  business_id: string;
  job_id?: string;
  place_id?: string | null;
  name: string;
  address?: string | null;
  phone?: string | null;
  email?: string | null;
  website?: string | null;
  google_maps_url?: string | null;
  category: string;
  district?: string | null;
  state?: string | null;
  latitude?: number | null;
  longitude?: number | null;
  distance_km?: number | null;
  is_valid: boolean;
  verified: boolean;
  discovered_at: string;
  updated_at?: string;
}

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
  has_next: boolean;
  has_prev: boolean;
}

export interface LastRunInfo {
  run_id: string;
  started_at: string | null;
  status: string;
  jobs_total: number;
  jobs_completed: number;
  jobs_failed: number;
  businesses_discovered: number;
  businesses_new: number;
  businesses_updated: number;
  businesses_duplicate: number;
  email_enriched: number;
  duration_seconds: number | null;
}

export interface SystemStatsRaw {
  locations_count: number;
  categories_count: number;
  jobs: {
    total: number;
    pending: number;
    running: number;
    completed: number;
    partial: number;
    failed: number;
    blocked: number;
  };
  businesses: {
    total: number;
    valid: number;
    invalid: number;
  };
  last_run: LastRunInfo | null;
}

export interface NormalizedSystemStats {
  locations_count: number;
  categories_count: number;
  total_jobs: number;
  pending_jobs: number;
  running_jobs: number;
  completed_jobs: number;
  partial_jobs: number;
  failed_jobs: number;
  blocked_jobs: number;
  total_businesses: number;
  valid_businesses: number;
  invalid_businesses: number;
  last_run: LastRunInfo | null;
}

export interface DiscoveryStatus {
  is_running: boolean;
  current_run_id: string | null;
  started_at: number | null;
  jobs_processed: number;
  jobs_total: number;
  current_job_id: string | null;
  stop_requested: boolean;
}

export interface ConfigSyncResult {
  locations: {
    total_in_excel: number;
    new: number;
    existing: number;
  };
  categories: {
    total_in_excel: number;
    new: number;
    existing: number;
  };
  message: string;
}

export interface JobGenerateResult {
  jobs_created: number;
  jobs_existing: number;
  total_jobs: number;
  message: string;
}

export interface ApiError {
  message: string;
  status?: number;
  endpoint?: string;
  isNetworkError?: boolean;
}
