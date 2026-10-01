import type { PaginatedResponse } from '../types/api';

import { getApiBaseUrl } from './index';

// Resolved from the shared base so this module follows the public path — and
// the backend-URL override in Settings — instead of assuming the root.
const API_BASE = `${getApiBaseUrl()}/api/v1/whatsapp`;

export interface WhatsAppAccount {
  account_id: string;
  display_name: string | null;
  phone_number: string;
  phone_number_id: string | null;
  waba_id: string | null;
  status: string;
  created_at: string;
  updated_at: string;
}

export interface WhatsAppTemplate {
  template_id: string;
  name: string;
  meta_template_name?: string | null;
  language_code?: string | null;
  category?: string | null;
  header_type: string | null;
  header_content: string | null;
  body: string;
  footer: string | null;
  buttons: any | null;
  status: string;
  created_at: string;
  updated_at: string;
  last_used_at: string | null;
  /** "manual", "agent" (Template Studio drafts) or "sheet" (made from a messages sheet). */
  origin?: string | null;
  /** Columns a sheet template fills per recipient; empty for other templates. */
  sheet_variables?: string[];
}

export interface WhatsAppCampaign {
  campaign_id: string;
  name: string;
  template_id: string | null;
  account_id: string | null;
  data_source_type: string;
  status: string;
  total_contacts: number;
  successful_count: number;
  failed_count: number;
  skipped_count: number;
  pending_count: number;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
  unique_visits: number;
  repeated_visits: number;
  /** Hits from link-preview fetchers, scanners and scripts: recorded, but
   *  never counted as a recipient visiting. */
  automated_hits: number;
  total_clicks: number;

  /** Delivery as reported by Meta's webhook. These accumulate rather than
   *  partition: every read message was also delivered. */
  delivered_count: number;
  read_count: number;
  /** Only messages Meta actually reported a failure for — a message with no
   *  webhook yet is unknown, not undelivered. */
  undelivered_count: number;
  /** Quick-reply taps. Meta reports nothing for call-to-action URL buttons,
   *  which show up under unique_visits instead. */
  button_click_count: number;
  button_clickers: number;
  /** False until Meta has reported anything, which separates "nobody read it"
   *  from "no webhook is configured yet". */
  has_delivery_data: boolean;

  /** What this campaign cost. Meta bills per delivered template message at a
   *  rate set by the template's category. */
  currency: string;
  billing_category: string | null;
  rate_per_message: number;
  billable_messages: number;
  cost_net: number;
  cost_gst: number;
  cost_total: number;
  /** "delivered" when Meta reported on this campaign; "sent" for campaigns
   *  that ran before the webhook existed, where accepted sends stand in and
   *  the figure is therefore a ceiling. */
  cost_basis: 'delivered' | 'sent';
}

export interface SpendBreakdown {
  category: string;
  billable_messages: number;
  net: number;
  gst: number;
  total: number;
}

export interface Spend {
  currency: string;
  billable_messages: number;
  net: number;
  gst: number;
  total: number;
  by_category: SpendBreakdown[];
  /** Campaigns priced off accepted sends rather than delivery reports. */
  estimated_from_sends: number;
  /** Meta's own billed figure — authoritative where it is available. */
  meta_total: number | null;
  meta_days: number | null;
  meta_error: string | null;
}

export interface WhatsAppCampaignRecipient {
  recipient_id: string;
  business_id: string | null;
  name: string | null;
  phone: string;
  status: string;
  reason: string | null;
  provider_message_id: string | null;
  updated_at: string;

  /** Each stage keeps its own timestamp, so a read message still shows when
   *  it was delivered. Null means no report has arrived — not a failure. */
  sent_at: string | null;
  delivered_at: string | null;
  read_at: string | null;
  failed_at: string | null;
  failure_code: string | null;

  /** The category this recipient was discovered under; null for uploads. */
  category: string | null;

  button_clicks: number;
  last_button_text: string | null;
  link_clicks: number;
}

export interface ValidationResponse {
  total_records: number;
  valid_mobile_numbers: number;
  invalid_numbers: number;
  empty_phone_numbers: number;
  landlines: number;
  duplicates_removed: number;
  final_sendable_contacts: number;
  valid_contacts: any[];
  invalid_contacts: any[];
}

export interface MediaUploadResponse {
  status: string;
  media_id: string;
  media_type: string;
  filename: string;
  mime_type: string;
  size_bytes: number;
}

export const uploadMedia = async (file: File, mediaType: 'image' | 'video'): Promise<MediaUploadResponse> => {
  const formData = new FormData();
  formData.append('file', file);
  formData.append('media_type', mediaType);

  const res = await fetch(`${API_BASE}/media/upload`, {
    credentials: 'include',
    method: 'POST',
    body: formData,
  });

  if (!res.ok) {
    const errorData = await res.json().catch(() => ({}));
    throw new Error(errorData.detail || 'Failed to upload media');
  }
  return res.json();
};

export const fetchAccounts = async (): Promise<WhatsAppAccount[]> => {
  const res = await fetch(`${API_BASE}/accounts`, { credentials: 'include' });
  if (!res.ok) throw new Error('Failed to fetch WhatsApp accounts');
  return res.json();
};

export const createAccount = async (data: Partial<WhatsAppAccount>): Promise<WhatsAppAccount> => {
  const res = await fetch(`${API_BASE}/accounts`, {
    credentials: 'include',
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!res.ok) throw new Error('Failed to create account');
  return res.json();
};

export const connectAccount = async (): Promise<WhatsAppAccount> => {
  const res = await fetch(`${API_BASE}/accounts/connect`, {
    credentials: 'include',
    method: 'POST',
  });
  if (!res.ok) {
    const errorData = await res.json().catch(() => ({}));
    throw new Error(errorData.detail || 'Failed to connect account');
  }
  return res.json();
};

export const fetchTemplates = async (): Promise<WhatsAppTemplate[]> => {
  const res = await fetch(`${API_BASE}/templates`, { credentials: 'include' });
  if (!res.ok) throw new Error('Failed to fetch templates');
  return res.json();
};

export const createTemplate = async (data: Partial<WhatsAppTemplate>): Promise<WhatsAppTemplate> => {
  const res = await fetch(`${API_BASE}/templates`, {
    credentials: 'include',
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!res.ok) throw new Error('Failed to create template');
  return res.json();
};

export const deleteTemplate = async (templateId: string): Promise<void> => {
  const res = await fetch(`${API_BASE}/templates/${templateId}`, {
    credentials: 'include',
    method: 'DELETE',
  });
  if (!res.ok) throw new Error('Failed to delete template');
};

export const validateContacts = async (contacts: any[]): Promise<ValidationResponse> => {
  const res = await fetch(`${API_BASE}/contacts/validate`, {
    credentials: 'include',
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ contacts }),
  });
  if (!res.ok) throw new Error('Failed to validate contacts');
  return res.json();
};

export const createCampaign = async (data: any): Promise<WhatsAppCampaign> => {
  const res = await fetch(`${API_BASE}/campaigns`, {
    credentials: 'include',
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  const json = await res.json();
  if (!res.ok) throw new Error(json.detail || 'Failed to create campaign');
  return json;
};

export const fetchCampaigns = async (): Promise<WhatsAppCampaign[]> => {
  const res = await fetch(`${API_BASE}/campaigns`, { credentials: 'include' });
  if (!res.ok) throw new Error('Failed to fetch campaigns');
  return res.json();
};

/** Total outreach spend, by category, plus Meta's own billed figure. */
export const fetchSpend = async (metaDays = 30): Promise<Spend> => {
  const res = await fetch(`${API_BASE}/spend?meta_days=${metaDays}`, { credentials: 'include' });
  if (!res.ok) throw new Error('Failed to fetch spend');
  return res.json();
};

export const fetchCampaignRecipients = async (campaignId: string, page = 1, pageSize = 50): Promise<PaginatedResponse<WhatsAppCampaignRecipient>> => {
  const res = await fetch(`${API_BASE}/campaigns/${campaignId}/recipients?page=${page}&page_size=${pageSize}`, { credentials: 'include' });
  if (!res.ok) throw new Error('Failed to fetch campaign recipients');
  return res.json();
};

export const cancelCampaign = async (campaignId: string): Promise<void> => {
  const res = await fetch(`${API_BASE}/campaigns/${campaignId}/cancel`, {
    credentials: 'include',
    method: 'POST',
  });
  if (!res.ok) throw new Error('Failed to cancel campaign');
};

export const downloadCleanedData = (validContacts: any[]) => {
  const headers = ['Name', 'Phone', 'Business ID'];
  const rows = validContacts.map(c => `"${c.name || ''}","${c.phone}","${c.business_id || ''}"`);
  const csvContent = [headers.join(','), ...rows].join('\n');
  const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.setAttribute('href', url);
  link.setAttribute('download', 'cleaned_whatsapp_contacts.csv');
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
};

export interface WhatsAppCampaignLog {
  log_id: string;
  recipient_id: string | null;
  status: string;
  provider_status: string | null;
  provider_code: string | null;
  error_reason: string | null;
  duration_ms: number | null;
  created_at: string;
}

export interface CampaignLogsResponse {
  campaign_id: string;
  status: string;
  started_at: string | null;
  completed_at: string | null;
  duration_seconds: number | null;
  total_contacts: number;
  successful_count: number;
  failed_count: number;
  skipped_count: number;
  items: WhatsAppCampaignLog[];
}

export const fetchCampaignLogs = async (campaignId: string): Promise<CampaignLogsResponse> => {
  const res = await fetch(`${API_BASE}/campaigns/${campaignId}/logs`, { credentials: 'include' });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || 'Failed to fetch campaign logs');
  }
  return res.json();
};

/** Re-reads one campaign, so delivery counts refresh as webhooks land. */
export const fetchCampaign = async (campaignId: string): Promise<WhatsAppCampaign> => {
  const res = await fetch(`${API_BASE}/campaigns/${campaignId}`, { credentials: 'include' });
  if (!res.ok) throw new Error('Failed to fetch campaign');
  return res.json();
};

export const fetchTemplate = async (templateId: string): Promise<WhatsAppTemplate> => {
  const res = await fetch(`${API_BASE}/templates/${templateId}`, { credentials: 'include' });
  if (!res.ok) throw new Error('Failed to fetch template');
  return res.json();
};

export interface TemplateSyncResult {
  status: string;
  checked: number;
  updated: number;
  error?: string | null;
}

/** Reconciles every submitted local template against the Meta WABA. */
export const syncTemplateStatuses = async (): Promise<TemplateSyncResult> => {
  const res = await fetch(`${API_BASE}/templates/sync-status`, { method: 'POST', credentials: 'include' });
  if (!res.ok) throw new Error('Failed to sync template statuses');
  return res.json();
};

export const updateTemplate = async (
  templateId: string,
  data: Partial<WhatsAppTemplate>
): Promise<WhatsAppTemplate> => {
  const res = await fetch(`${API_BASE}/templates/${templateId}`, {
    credentials: 'include',
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || 'Failed to update template');
  }
  return res.json();
};

export interface TemplateSubmitResult {
  status: string;
  meta_template_name?: string | null;
  language_code?: string | null;
  meta_status?: string | null;
  error?: string | null;
  error_code?: string | null;
}

/** Sends a local draft to Meta for review. */
export const submitTemplate = async (
  templateId: string,
  category = 'MARKETING'
): Promise<TemplateSubmitResult> => {
  const res = await fetch(`${API_BASE}/templates/${templateId}/submit`, {
    credentials: 'include',
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ category }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || 'Failed to submit template');
  }
  return res.json();
};

// --- Campaign audience selection -------------------------------------------

export interface GeoOption {
  value: string;
  businesses: number;
}

export interface AudienceOptions {
  states: GeoOption[];
  districts: GeoOption[];
  tehsils: GeoOption[];
}

export interface AudienceFilters {
  state: string;
  district: string;
  tehsil: string;
  limit?: number | null;
  include_already_contacted: boolean;
}

export interface AudienceSummary {
  total_businesses: number;
  with_phone: number;
  already_contacted: number;
  never_contacted: number;
  sendable: number;
  limit_applied?: number | null;
}

export interface AudiencePreview extends AudienceSummary {
  contacts: { name: string; phone: string; business_id: string }[];
}

export const fetchAudienceOptions = async (
  state = 'All',
  district = 'All'
): Promise<AudienceOptions> => {
  const params = new URLSearchParams({ state, district });
  const res = await fetch(`${API_BASE}/audience/options?${params}`, { credentials: 'include' });
  if (!res.ok) throw new Error('Failed to load audience options');
  return res.json();
};

export const fetchAudienceSummary = async (f: AudienceFilters): Promise<AudienceSummary> => {
  const res = await fetch(`${API_BASE}/audience/summary`, {
    credentials: 'include',
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(f),
  });
  if (!res.ok) throw new Error('Failed to summarise audience');
  return res.json();
};

export const fetchAudiencePreview = async (f: AudienceFilters): Promise<AudiencePreview> => {
  const res = await fetch(`${API_BASE}/audience/preview`, {
    credentials: 'include',
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(f),
  });
  if (!res.ok) throw new Error('Failed to build audience');
  return res.json();
};

/**
 * Hand a chosen audience to the campaign builder.
 *
 * sessionStorage rather than a URL: the list can hold thousands of contacts,
 * and it should not survive the tab being closed.
 */
const AUDIENCE_KEY = 'gmap-campaign-audience';

/** What the campaign builder can be handed: an audience from Business Data,
 *  or a sheet from the Template Studio together with the template made from it. */
export interface HandedAudience {
  contacts: any[];
  label: string;
  /** Preselect this template in the builder. */
  template_id?: string;
  /** Raw sheet rows: phone numbers still need validating. */
  needs_validation?: boolean;
}

export const stashAudience = (payload: HandedAudience) => {
  try {
    sessionStorage.setItem(AUDIENCE_KEY, JSON.stringify(payload));
  } catch {
    // Storage can throw in private mode; the builder then starts empty.
  }
};

export const takeAudience = (): HandedAudience | null => {
  try {
    const raw = sessionStorage.getItem(AUDIENCE_KEY);
    if (!raw) return null;
    sessionStorage.removeItem(AUDIENCE_KEY);
    return JSON.parse(raw);
  } catch {
    return null;
  }
};

// ---------------------------------------------------------
// Template Studio — the agent drafts, a person approves.
// ---------------------------------------------------------

const STUDIO = `${API_BASE}/studio`;

export interface StudioPoster {
  headline_line1: string;
  headline_line2: string;
  headline_highlight: string;
  subline: string;
  callout: string;
  callout_highlight: string;
  benefits_title: string;
  benefits: { icon: string; text: string }[];
  cta: string;
  opportunity_title: string;
  opportunity_text: string;
  sign_title: string;
  bank_name: string;
  phone_label: string;
  web_label: string;
}

export interface StudioPhotoCheck {
  passed?: boolean;
  attempt?: number;
  has_text?: boolean;
  photorealistic?: boolean;
  operator_serving_customer?: boolean;
  anatomy_problems?: boolean;
  issues?: string[];
}

export interface StudioDraft {
  template_id: string;
  name: string;
  /** GENERATING, AWAITING_APPROVAL, GENERATION_FAILED, REJECTED_BY_REVIEWER,
   *  or Meta's review state once approved and submitted. */
  status: string;
  target_state: string | null;
  language_code: string | null;
  category: string | null;
  header_type: string | null;
  header_content: string | null;
  body: string;
  footer: string | null;
  buttons: any[] | null;
  meta_template_name: string | null;
  generation: {
    /** Which idea from the agent's angle menu this draft tests. */
    angle_key?: string;
    angle?: string;
    brief?: string | null;
    poster?: StudioPoster;
    photo_check?: StudioPhotoCheck;
    copy_warnings?: string[];
    models?: { text?: string; image?: string };
    error?: string;
  } | null;
  review_note: string | null;
  reviewed_by: string | null;
  reviewed_at: string | null;
  created_at: string;
}

export interface StudioState {
  state: string;
  language_code: string | null;
  language: string | null;
  locations: number;
  businesses: number;
}

export interface StudioRules {
  facts: string[];
  copy_rules: string[];
  image_rules: string[];
  state_languages: Record<string, string>;
}

export interface StudioStateStats {
  state: string;
  sent: number;
  delivered: number;
  read: number;
  visitors: number;
  tappers: number;
}

export interface StudioPerformance extends Omit<StudioStateStats, 'state'> {
  template_id: string;
  name: string;
  origin: string;
  target_state: string | null;
  language: string | null;
  angle_key: string | null;
  angle: string | null;
  /** False when Meta never reported delivery for this template, so reads
   *  and taps are unknown rather than zero. */
  tracked: boolean;
  read_rate: number | null;
  response_rate: number | null;
  by_state: StudioStateStats[];
}

const studioCall = async <T>(path: string, init?: RequestInit): Promise<T> => {
  const res = await fetch(`${STUDIO}${path}`, {
    credentials: 'include',
    headers: init?.body ? { 'Content-Type': 'application/json' } : undefined,
    ...init,
  });
  const json = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(json.detail || `Request failed (${res.status})`);
  return json as T;
};

export const fetchStudioStatus = () => studioCall<{ ready: boolean; error: string | null }>('/status');
export const fetchStudioRules = () => studioCall<StudioRules>('/rules');
export const fetchStudioStates = () => studioCall<StudioState[]>('/states');
export const fetchStudioDrafts = () => studioCall<StudioDraft[]>('/drafts');
export const fetchStudioPerformance = () => studioCall<StudioPerformance[]>('/performance');

export const generateStudioDrafts = (state: string, count: number, brief: string) =>
  studioCall<StudioDraft[]>('/generate', {
    method: 'POST',
    body: JSON.stringify({ state, count, brief: brief.trim() || null }),
  });

export const requestNewPhoto = (id: string) =>
  studioCall<StudioDraft>(`/drafts/${id}/new-photo`, { method: 'POST' });

export const editStudioDraft = (
  id: string,
  edit: { body?: string; footer?: string; apply_button?: string; callback_button?: string; poster?: Partial<StudioPoster> },
) => studioCall<{ draft: StudioDraft; warnings: string[] }>(`/drafts/${id}`, {
  method: 'PATCH',
  body: JSON.stringify(edit),
});

export const approveStudioDraft = (id: string, category = 'MARKETING') =>
  studioCall<{ status: string; error: string | null; draft: StudioDraft }>(`/drafts/${id}/approve`, {
    method: 'POST',
    body: JSON.stringify({ category }),
  });

export const rejectStudioDraft = (id: string, reason: string) =>
  studioCall<StudioDraft>(`/drafts/${id}/reject`, {
    method: 'POST',
    body: JSON.stringify({ reason }),
  });

// ---------------------------------------------------------
// Templates from a messages sheet — the team's own wording, read back into
// one template and submitted to Meta without an Approve step.
// ---------------------------------------------------------

export type SheetOutcome = 'ready' | 'pending' | 'created' | 'rejected' | 'failed';

export interface SheetTemplate {
  template_id: string;
  name: string;
  meta_template_name: string | null;
  status: string;
  /** What the status means: ready to send, waiting on Meta, or why not. */
  outcome: SheetOutcome;
  reason: string | null;
  language_code: string | null;
  category: string | null;
  body: string;
  /** Placeholder keys in Meta's order, {{link}} excluded. */
  variables: string[];
  /** key -> the sheet header it is filled from. */
  columns: Record<string, string>;
  examples: Record<string, string>;
  source_name: string | null;
  rows: number | null;
  buttons: { type: string; text: string; url?: string }[];
  link_target: string | null;
  /** Whether visits through the button are recorded per recipient. */
  tracked: boolean;
  created_at: string;
}

export interface SheetSettings {
  tracking_enabled: boolean;
  default_link_target: string;
  default_button_text: string;
  button_text_limit: number;
  max_rows: number;
}

export interface FromMessagesRequest {
  rows: Record<string, string>[];
  message_column: string;
  phone_column: string;
  category: 'MARKETING' | 'UTILITY';
  language: string;
  source_name?: string | null;
  add_button: boolean;
  button_text?: string;
  link_target?: string;
}

export interface FromMessagesResult {
  action: SheetOutcome;
  reason: string | null;
  derived: { body: string; variables: string[]; rows: number };
  template: SheetTemplate | null;
}

export const fetchSheetSettings = () => studioCall<SheetSettings>('/sheet-settings');
export const fetchSheetTemplates = () => studioCall<SheetTemplate[]>('/sheet-templates');
export const templateFromMessages = (req: FromMessagesRequest) =>
  studioCall<FromMessagesResult>('/from-messages', { method: 'POST', body: JSON.stringify(req) });
