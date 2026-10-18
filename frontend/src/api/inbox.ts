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
  /** Agent to Human: who is answering by hand while the bot waits, and since when. */
  handled_by: string | null;
  handled_since: string | null;
  /** The chat's outcome now: the team's last one, or the bot's when it has moved on since. */
  disposition: Disposition | null;
}

export interface Disposition {
  key: string;
  label: string;
  note: string | null;
  by: string | null;
  at: string;
  source: 'team' | 'bot';
}

export interface DispositionOption { key: string; label: string; group: 'positive' | 'follow_up' | 'negative' | 'other' }

export interface DispositionDashboard {
  total: number;
  by_team: number;
  groups: (DispositionOption & { count: number })[];
  recent_days: number;
  recent_count: number;
  recent_by_disposition: { key: string; label: string; count: number }[];
  recent: { phone: string; name: string | null; key: string; label: string; note: string | null; by: string; at: string }[];
  with_people: { phone: string; name: string | null; by: string; since: string | null }[];
  group_totals?: Record<'positive' | 'follow_up' | 'negative' | 'other', number>;
  /** Outcomes the team recorded each day of the range (IST), oldest first. */
  by_day?: { date: string; count: number }[];
  by_person?: { by: string; count: number }[];
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
  /** The open ticket while the conversation needs attention. */
  ticket_id: string | null;
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
export const setAttention = (phone: string, needed: boolean, disposition?: string, note?: string) =>
  call<{ needs_attention: boolean }>(`/conversations/${digits(phone)}/attention`, {
    method: 'POST', body: JSON.stringify({ needed, disposition, note }),
  });

export const fetchDispositionOptions = () => call<DispositionOption[]>('/dispositions');

export const recordDisposition = (phone: string, disposition: string, note?: string) =>
  call<Disposition>(`/conversations/${digits(phone)}/disposition`, {
    method: 'POST', body: JSON.stringify({ disposition, note }),
  });

/** Agent to Human ("person") or Human to Agent ("bot"), with the outcome so far. */
export const handOver = (phone: string, to: 'person' | 'bot', disposition?: string, note?: string, resume = true) =>
  call<{ bot_paused: boolean; handled_by: string | null; bot_said: string | null; disposition: Disposition }>(
    `/conversations/${digits(phone)}/handover`, {
      method: 'POST', body: JSON.stringify({ to, disposition, note, resume }),
    });

export const fetchDispositionDashboard = (days = 7) => call<DispositionDashboard>(`/dispositions/dashboard?days=${days}`);

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

/** A conversation at a glance: who, how far, what they asked, and what to send next. */
export interface ChatSummary {
  generated_at: string;
  person: {
    name: string | null; phone: string; pincode: string | null; tehsil: string | null; district: string | null;
    state: string | null; category: string | null; business_name: string | null; campaign: string | null; language: string | null;
  };
  headline: string;
  /** One or two plain sentences: where this person stands. */
  in_short: string;
  /** The conversation from the start, one plain line per thing that happened. */
  timeline: { when: string; kind: 'event' | 'said' | 'answered' | 'waiting' | 'team'; text: string }[];
  /** True when they wrote to us on their own, not from a campaign or the bot's flow. */
  direct?: boolean;
  timeline_earlier: number;
  waiting_questions: { text: string; at: string; voice: boolean }[];
  story: string[];
  questions: { text: string; at: string; voice: boolean; answers: { question: string; answer: string }[]; answered_by_bot: boolean }[];
  unanswered_questions: number;
  other_messages: { text: string; at: string; voice: boolean }[];
  attention: { reason: string | null; at: string } | null;
  next: { action: string; reply: string | null; reply_language: string; window_open: boolean };
}

export const fetchChatSummary = (phone: string) =>
  call<ChatSummary>(`/conversations/${digits(phone)}/summary`);

/** Conversations waiting for a person, newest first; shown on every page until resolved. */
export interface AttentionAlert { phone: string; name: string | null; reason: string | null; at: string | null; ticket_id: string | null }
export const fetchAttentionAlerts = () => call<AttentionAlert[]>('/attention-alerts');
/** Fired when someone marks or resolves a conversation, so the alerts refresh at once. */
export const ATTENTION_CHANGED = 'autogmap:attention-changed';

/** A conversation left for a person, as a ticket: raised on "Attention needed", solved on "Question resolved". */
export interface Ticket {
  ticket_id: string;
  phone: string;
  /** The person who asked. */
  raised_by: string | null;
  question: string | null;
  /** A later question while the ticket was open, if any. */
  latest_question: string | null;
  questions_count: number;
  /** "bot", or the team member who marked it. */
  raised_via: string;
  status: 'Resolved' | 'Not resolved';
  raised_at: string | null;
  resolved_at: string | null;
  resolved_by: string | null;
  /** The bot answered it itself, from Eko's FAQ and kiosk.eko.in; bot_answer is what it sent. */
  resolved_by_bot?: boolean;
  bot_answer?: string | null;
}
export const fetchTickets = (status?: 'open' | 'resolved') => call<Ticket[]>(`/tickets${status ? `?status=${status}` : ''}`);
export const fetchRecentlyResolved = () => call<Ticket[]>('/tickets/recently-resolved');
