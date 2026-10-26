import { getApiBaseUrl } from './index';

/** How AutoGMap's agents are doing (agent_telemetry.py): the blueprint's KPIs and every run's chain. */

export interface ContextChunk { source: string; ref: string | null; text: string; tokens: number; score: number | null;
  /** The three tiers of the UI spec: global rules, the project's memory, this session's input. */
  layer: 'global' | 'project' | 'session' }

export interface Evaluation {
  checks?: { name: string; passed: boolean; detail: string }[];
  first_problems?: string[]; remaining?: string[]; repaired?: boolean;
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
const call = async <T>(path: string): Promise<T> => {
  const res = await fetch(`${base()}${path}`, { credentials: 'include' });
  const json = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(json.detail || `Request failed (${res.status})`);
  return json as T;
};

export const fetchAgentQuality = (days = 30) => call<AgentQuality>(`/quality?days=${days}`);
export const fetchAgentRuns = (agent?: string, outcome?: string, limit = 50) => {
  const q = new URLSearchParams({ limit: String(limit) });
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
