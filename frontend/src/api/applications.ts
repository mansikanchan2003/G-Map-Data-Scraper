import { getApiBaseUrl } from './index';

// Resolved per call so the backend-URL override in Settings applies at once.
const base = () => `${getApiBaseUrl()}/api/v1/applications`;

export interface ApplicationDocument {
  document_id: string;
  type: string;
  label: string;
  name: string | null;
  drive_url: string | null;
  uploaded_at: string | null;
}

export interface ApplicationComment {
  comment_id: string;
  body: string;
  author: string;
  created_at: string | null;
}

export interface Application {
  phone: string;
  name: string | null;
  /** The PIN the person gave in the chat. */
  pincode: string | null;
  /** Taken from their messages because the bot could not place it on the map. */
  pincode_unchecked: boolean;
  /** The applicant's own area, from their PIN (our location list or India Post). */
  state: string | null;
  district: string | null;
  tehsil: string | null;
  /** The nearest of our target PINs, from the bot's check. */
  place: string | null;
  distance_km: number | null;
  /** The persona: the business's Google Maps category, from the campaign that reached them. */
  category: string | null;
  qualification: string | null;
  franchise_background: boolean | null;
  can_invest: boolean | null;
  language: string | null;
  stage: string;
  bot_step: string | null;
  pin_qualified: boolean;
  strongly_qualified: boolean;
  not_qualified: boolean;
  not_qualified_reasons: string[];
  verdict: 'Strongly qualified' | 'Not qualified' | 'PIN qualified' | 'In progress';
  documents: ApplicationDocument[];
  documents_count: number;
  documents_total: number;
  required_documents_done: boolean;
  drive_folder_url: string | null;
  submitted: boolean;
  submitted_at: string | null;
  started_at: string | null;
  last_message_at: string | null;
  source: { campaign: string; business_name: string | null; category: string | null;
            district: string | null; state: string | null } | null;
  comments: ApplicationComment[];
  removed: boolean;
  removed_by: string | null;
}

export interface ApplicationStats {
  total: number;
  pin_qualified: number;
  strongly_qualified: number;
  not_qualified: number;
  submitted: number;
  removed: number;
}

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${base()}${path}`, {
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    ...init,
  });
  if (!res.ok) {
    let detail = `HTTP ${res.status}`;
    try { detail = (await res.json()).detail || detail; } catch { /* not JSON */ }
    throw new Error(detail);
  }
  return res.json();
}

const digits = (phone: string) => phone.replace(/\D/g, '');

export const fetchApplications = (removed = false) =>
  call<{ stats: ApplicationStats; items: Application[] }>(removed ? '?removed=true' : '');

export const addApplicationComment = (phone: string, body: string) =>
  call<ApplicationComment>(`/${digits(phone)}/comments`, { method: 'POST', body: JSON.stringify({ body }) });

export const deleteApplicationComment = (commentId: string) =>
  call<{ status: string }>(`/comments/${commentId}`, { method: 'DELETE' });

export const removeApplication = (phone: string) =>
  call<{ status: string }>(`/${digits(phone)}`, { method: 'DELETE' });

export const restoreApplication = (phone: string) =>
  call<{ status: string }>(`/${digits(phone)}/restore`, { method: 'POST' });

/** Opens an uploaded document (or its copy in Drive). */
export const documentUrl = (documentId: string) => `${getApiBaseUrl()}/api/v1/inbox/documents/${documentId}`;
