import type { PaginatedResponse } from '../types/api';

const API_BASE = '/api/v1/whatsapp';

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
  total_clicks: number;
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
  const res = await fetch(`${API_BASE}/accounts`);
  if (!res.ok) throw new Error('Failed to fetch WhatsApp accounts');
  return res.json();
};

export const createAccount = async (data: Partial<WhatsAppAccount>): Promise<WhatsAppAccount> => {
  const res = await fetch(`${API_BASE}/accounts`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!res.ok) throw new Error('Failed to create account');
  return res.json();
};

export const connectAccount = async (): Promise<WhatsAppAccount> => {
  const res = await fetch(`${API_BASE}/accounts/connect`, {
    method: 'POST',
  });
  if (!res.ok) {
    const errorData = await res.json().catch(() => ({}));
    throw new Error(errorData.detail || 'Failed to connect account');
  }
  return res.json();
};

export const fetchTemplates = async (): Promise<WhatsAppTemplate[]> => {
  const res = await fetch(`${API_BASE}/templates`);
  if (!res.ok) throw new Error('Failed to fetch templates');
  return res.json();
};

export const createTemplate = async (data: Partial<WhatsAppTemplate>): Promise<WhatsAppTemplate> => {
  const res = await fetch(`${API_BASE}/templates`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!res.ok) throw new Error('Failed to create template');
  return res.json();
};

export const deleteTemplate = async (templateId: string): Promise<void> => {
  const res = await fetch(`${API_BASE}/templates/${templateId}`, {
    method: 'DELETE',
  });
  if (!res.ok) throw new Error('Failed to delete template');
};

export const validateContacts = async (contacts: any[]): Promise<ValidationResponse> => {
  const res = await fetch(`${API_BASE}/contacts/validate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ contacts }),
  });
  if (!res.ok) throw new Error('Failed to validate contacts');
  return res.json();
};

export const createCampaign = async (data: any): Promise<WhatsAppCampaign> => {
  const res = await fetch(`${API_BASE}/campaigns`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  const json = await res.json();
  if (!res.ok) throw new Error(json.detail || 'Failed to create campaign');
  return json;
};

export const fetchCampaigns = async (): Promise<WhatsAppCampaign[]> => {
  const res = await fetch(`${API_BASE}/campaigns`);
  if (!res.ok) throw new Error('Failed to fetch campaigns');
  return res.json();
};

export const fetchCampaignRecipients = async (campaignId: string, page = 1, pageSize = 50): Promise<PaginatedResponse<WhatsAppCampaignRecipient>> => {
  const res = await fetch(`${API_BASE}/campaigns/${campaignId}/recipients?page=${page}&page_size=${pageSize}`);
  if (!res.ok) throw new Error('Failed to fetch campaign recipients');
  return res.json();
};

export const cancelCampaign = async (campaignId: string): Promise<void> => {
  const res = await fetch(`${API_BASE}/campaigns/${campaignId}/cancel`, {
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
  const res = await fetch(`${API_BASE}/campaigns/${campaignId}/logs`);
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || 'Failed to fetch campaign logs');
  }
  return res.json();
};

export const fetchTemplate = async (templateId: string): Promise<WhatsAppTemplate> => {
  const res = await fetch(`${API_BASE}/templates/${templateId}`);
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
  const res = await fetch(`${API_BASE}/templates/sync-status`, { method: 'POST' });
  if (!res.ok) throw new Error('Failed to sync template statuses');
  return res.json();
};

export const updateTemplate = async (
  templateId: string,
  data: Partial<WhatsAppTemplate>
): Promise<WhatsAppTemplate> => {
  const res = await fetch(`${API_BASE}/templates/${templateId}`, {
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
