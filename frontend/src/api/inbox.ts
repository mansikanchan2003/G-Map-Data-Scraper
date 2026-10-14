import { getApiBaseUrl } from './index';

// Resolved per call so the backend-URL override in Settings applies at once.
const base = () => `${getApiBaseUrl()}/api/v1/inbox`;

export interface ConversationSummary {
  phone: string;
  name: string | null;
  last_message: string | null;
  last_direction: 'IN' | 'OUT' | null;
  last_message_at: string | null;
  unread: number;
  /** When a typed reply stops being possible; null if they never wrote. */
  window_expires_at: string | null;
  bot_step: string | null;
  bot_step_label: string | null;
  bot_paused: boolean;
  documents: number;
  /** Reached by an AutoGMap campaign; the bot answers no one else. */
  from_campaign: boolean;
  /** A question waiting for a person; cleared only by "Question resolved". */
  needs_attention: boolean;
  attention_reason: string | null;
  attention_at: string | null;
}

export interface ThreadMessage {
  id: string;
  direction: 'IN' | 'OUT';
  /** text, button, interactive, image, ... for IN; text, buttons, link or
   *  campaign (a template a campaign sent) for OUT. */
  kind: string;
  body: string | null;
  /** buttons: [{id, title}]; link: {text, url}; campaign: button labels;
   *  button/interactive: what was tapped. */
  payload: any;
  status: string | null;
  error_reason: string | null;
  /** "bot", "campaign", or the email of whoever typed it. */
  sent_by: string | null;
  campaign: string | null;
  created_at: string;
}

export interface OnboardingDocument {
  document_id: string;
  doc_type: string;
  label: string;
  original_name: string | null;
  content_type: string;
  size_bytes: number;
  uploaded_at: string;
  /** Set once the file is in Google Drive; the local copy is gone by then. */
  drive_url: string | null;
  /** Why it is not in Drive yet, if a copy was tried and failed. */
  drive_error: string | null;
}

export interface ConversationDetail extends ConversationSummary {
  category: string | null;
  district: string | null;
  state: string | null;
  bot_data: Record<string, any> | null;
  documents_submitted_at: string | null;
  upload_url: string | null;
  drive_folder_url: string | null;
  messages: ThreadMessage[];
  document_files: OnboardingDocument[];
}

export interface BotSettings {
  enabled: boolean;
  triggers: string[];
  radius_km: number;
  documents: { key: string; label: string; hint: string | null; required: boolean }[];
  public_base_url_set: boolean;
  drive_configured: boolean;
  /** The address the Drive folder has to be shared with. */
  drive_service_account: string | null;
}

const call = async <T>(path: string, init?: RequestInit): Promise<T> => {
  const res = await fetch(`${base()}${path}`, {
    credentials: 'include',
    headers: init?.body ? { 'Content-Type': 'application/json' } : undefined,
    ...init,
  });
  const json = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(json.detail || `Request failed (${res.status})`);
  return json as T;
};

const digits = (phone: string) => phone.replace(/\D/g, '');

export const fetchConversations = (q = '') =>
  call<ConversationSummary[]>(`/conversations${q.trim() ? `?q=${encodeURIComponent(q.trim())}` : ''}`);

export const fetchInboxSummary = () => call<{ unread_conversations: number }>('/summary');

export const fetchConversation = (phone: string) =>
  call<ConversationDetail>(`/conversations/${digits(phone)}`);

export const sendInboxMessage = (phone: string, message: string) =>
  call<ThreadMessage>(`/conversations/${digits(phone)}/messages`, {
    method: 'POST', body: JSON.stringify({ message }),
  });

export const markConversationRead = (phone: string) =>
  call<{ status: string }>(`/conversations/${digits(phone)}/read`, { method: 'POST' });

/** Mark a campaign conversation as needing attention, or resolve it. */
export const setAttention = (phone: string, needed: boolean) =>
  call<{ needs_attention: boolean }>(`/conversations/${digits(phone)}/attention`, {
    method: 'POST', body: JSON.stringify({ needed }),
  });

/** Send a photo, video, audio clip or document; anything else goes as a document. */
export const sendInboxMedia = async (phone: string, file: File, caption: string): Promise<ThreadMessage> => {
  const form = new FormData();
  form.append('file', file);
  if (caption.trim()) form.append('caption', caption.trim());
  const res = await fetch(`${base()}/conversations/${digits(phone)}/media`, {
    method: 'POST', credentials: 'include', body: form,
  });
  const json = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(json.detail || `Could not send the file (${res.status})`);
  return json as ThreadMessage;
};

export const setBotPaused = (phone: string, paused: boolean) =>
  call<{ bot_paused: boolean }>(`/conversations/${digits(phone)}/bot`, {
    method: 'POST', body: JSON.stringify({ paused }),
  });

export const fetchBotSettings = () => call<BotSettings>('/bot-settings');

export const saveBotSettings = (enabled: boolean, triggers: string[]) =>
  call<BotSettings>('/bot-settings', { method: 'PUT', body: JSON.stringify({ enabled, triggers }) });

export const saveDocumentsToDrive = (phone: string) =>
  call<{ copied: number; folder_url: string | null }>(`/conversations/${digits(phone)}/drive`, { method: 'POST' });

/** A photo, video, voice note or document someone sent. */
export const mediaUrl = (messageId: string, download = false) =>
  `${base()}/media/${messageId}${download ? '?download=true' : ''}`;

export const documentUrl = (id: string, download = false) =>
  `${base()}/documents/${id}${download ? '?download=true' : ''}`;
