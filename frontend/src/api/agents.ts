import { getApiBaseUrl } from './index';

/** How AutoGMap's agents are doing (agent_telemetry.py): the blueprint's KPIs and every run's chain. */

export interface ContextChunk { source: string; ref: string | null; text: string; tokens: number; score: number | null;
  /** The three tiers of the UI spec: global rules, the project's memory, this session's input. */
  layer: 'global' | 'project' | 'session' }

export interface Evaluation {
  checks?: { name: string; passed: boolean; detail: string }[];
  first_problems?: string[]; remaining?: string[]; repaired?: boolean;
  /** How sure the bot was of a reading (0 to 1), and the readings when a reply meant two things. */
  confidence?: number; ambiguous?: string[];
}

export interface AgentSummary {
  runs: number; failed: number; pending: number; accepted: number; edited: number; rejected: number;
  /** Runs that did not fail (target > 95%). */
  completion_rate: number | null;
  /** Of the runs a person decided on, the share kept as they were (target > 75%). */
  acceptance_rate: number | null;
  /** Levenshtein distance between the agent's output and the final version, and per character (target 0). */
  avg_edit_distance: number | null;
  avg_edit_ratio: number | null;
  tokens_per_run: number | null;
  context_tokens_per_run: number | null;
}

export interface AgentQuality {
  days: number;
  targets: { acceptance_rate: number; completion_rate: number; avg_edit_ratio: number };
  overall: AgentSummary;
  agents: (AgentSummary & { key: string; label: string })[];
  /** Tickets: each time a person had to step in. */
  hitl_interventions: number;
  /** Drift & repair: the runs people changed the most. */
  biggest_corrections: AgentRun[];
  weeks: { week: string; runs: number; acceptance_rate: number | null; avg_edit_ratio: number | null;
           tokens_per_run: number | null; completion_rate: number | null; hitl: number }[];
}

export interface AgentRun {
  id: string; agent: string; agent_label: string; subject_type: string; subject_id: string; model: string | null;
  outcome: 'pending' | 'accepted' | 'edited' | 'rejected' | 'failed';
  output: string | null; final_output: string | null; edit_distance: number | null; edit_ratio: number | null;
  prompt_tokens: number | null; context_tokens: number | null; output_tokens: number | null; latency_ms: number | null;
  error: string | null; finalized_by: string | null; context: ContextChunk[];
  evaluation: Evaluation | null;
  /** The model's context window, for the token health bar; null for the rule-based bot. */
  context_window: number | null;
  created_at: string | null; finalized_at: string | null; prompt?: string | null;
}

const base = () => `${getApiBaseUrl()}/api/v1/agents`;
const call = async <T>(path: string, init?: RequestInit): Promise<T> => {
  const res = await fetch(`${base()}${path}`, { credentials: 'include', ...init });
  const json = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(json.detail || `Request failed (${res.status})`);
  return json as T;
};

export const fetchAgentQuality = (days = 30) => call<AgentQuality>(`/quality?days=${days}`);
export const fetchAgentRuns = (agent?: string, outcome?: string, limit = 50, subject?: string) => {
  const q = new URLSearchParams({ limit: String(limit) });
  if (subject) q.set('subject', subject);
  if (agent) q.set('agent', agent);
  if (outcome) q.set('outcome', outcome);
  return call<AgentRun[]>(`/runs?${q}`);
};
export const fetchAgentRun = (id: string) => call<AgentRun>(`/runs/${id}`);

export interface GoldenReport {
  ran_at: string; seconds: number; total: number; passed: number;
  suites: Record<string, { total: number; passed: number }>;
  failures: { id: string; suite: string; title: string; problems: string[] }[];
}
export interface GoldenHistory { last: GoldenReport | null; history: { ran_at: string; total: number; passed: number }[] }
/** The golden set's last run before a deploy, and the ones before it. */
export const fetchGolden = () => call<GoldenHistory>('/golden');

export interface SourceRow { key: string; label: string; icon: string; synced_at: string | null;
  status: 'fresh' | 'stale' | 'never'; fresh_for_hours: number; note: string; used_by: string[] }
/** Each source the agents draw on, with when it was last refreshed. */
export const fetchSources = () => call<SourceRow[]>('/sources');

export interface Switch { key: string; label: string; enabled: boolean; changed_by: string | null; changed_at: string | null;
  on?: string; off?: string; about?: string }
export interface Controls { agents: Switch[]; context: Switch[]; history: { what: string; on: boolean; by: string; at: string }[] }
/** The admin's guardrails over the agents. */
export const fetchControls = () => call<Controls>('/controls');
export const setSwitch = (group: 'agents' | 'context', key: string, enabled: boolean) =>
  call<Controls>(`/controls/${group}/${key}`, { method: 'PUT', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ enabled }) });

export interface Patch {
  id: string; kind: 'copy_lesson' | 'rule_phrase' | 'faq_review'; agent: string; title: string; lesson: string;
  before: string; after: string; key?: string; phrase?: string; question?: string;
  evidence: { run_id: string; agent: string; edit_ratio: number | null; by: string | null; at: string | null };
  accepted_by?: string; accepted_at?: string; gate?: { passed: number; total: number } | null;
}
export interface Learning { proposals: Patch[]; accepted: Patch[]; log: { what: string; id: string; lesson?: string; by: string; at: string }[] }
export interface GateReport { total: number; passed: number; failures: { id: string; title: string; problems: string[] }[] }
/** The learning loop: patches proposed from corrections, those in force, and what was done. */
export const fetchLearning = () => call<Learning>('/learning');
export const acceptPatch = async (id: string): Promise<{ ok: true } | { ok: false; message: string; gate?: GateReport }> => {
  const res = await fetch(`${base()}/learning/${id}/accept`, { method: 'POST', credentials: 'include' });
  const json = await res.json().catch(() => ({}));
  if (res.ok) return { ok: true };
  const d = json.detail;
  return { ok: false, message: typeof d === 'string' ? d : d?.message || `Request failed (${res.status})`, gate: d?.gate };
};
export const dismissPatch = (id: string) => call<Learning>(`/learning/${id}/dismiss`, { method: 'POST' });
export const undoPatch = (id: string) => call<Learning>(`/learning/${id}/undo`, { method: 'POST' });

export interface Reading { key: string | null; label: string; by: string; confidence: number | null }
export interface BotAction { kind: 'auto_reply' | 'clarify' | 'disposition' | 'faq' | 'team' | 'step'; title: string; detail: string; answer?: string }
export const tryReply = (text: string) => call<{ text: string; today: Reading; with_patches: Reading; pending_rules: number; bot: BotAction }>(
  '/playground/reply', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ text }) });
export interface Draft { body: string | null; angle: string | null; problems: string[]; prompt_tokens: number }
export interface CopyTrial { status: 'running' | 'done' | 'failed'; state: string; instruction: string; without: string[];
  today?: Draft; changed?: Draft; error?: string }
export const startCopyTrial = (state: string, instruction: string, without: string[]) =>
  call<{ id: string }>('/playground/copy', { method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ state, instruction, without }) });
export const fetchCopyTrial = (id: string) => call<CopyTrial>(`/playground/copy/${id}`);
