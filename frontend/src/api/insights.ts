import { getApiBaseUrl } from './index';

const BASE = `${getApiBaseUrl()}/api/v1/whatsapp/insights`;

/** strong: the 95% intervals do not overlap. likely: a big lift, not yet
 *  certain. too_early: not enough sends or responses to say anything. */
export type Confidence = 'strong' | 'likely' | 'no_difference' | 'too_early';

export interface SegmentStats {
  values: Record<string, string>;
  sent: number;
  delivered: number;
  read: number;
  failed: number;
  visited: number;
  tapped: number;
  responded: number;
  /** Link visits + button taps, per message sent. */
  response_rate: number;
  /** People who replied or tapped, started applying, qualified, submitted. */
  engaged?: number;
  interested?: number;
  qualified?: number;
  lead?: number;
  /** The stage this row is judged on (Playbook.judged_on), its count and rate. */
  outcome?: Stage;
  success?: number;
  success_rate?: number;
  ci_low: number;
  ci_high: number;
  tracked: boolean;
  delivery_rate: number | null;
  read_rate: number | null;
  lift: number | null;
  confidence: Confidence;
  direction: 'better' | 'worse' | 'none';
}

export type Stage = 'engaged' | 'interested' | 'qualified' | 'lead';

export interface DimensionSummary {
  label: string;
  group: string;
  segments: number;
  best: SegmentStats | null;
  worst: SegmentStats | null;
  leader: SegmentStats | null;
}

export interface Playbook {
  computed_at: string;
  /** Segments are ranked and judged on how many reached this stage. */
  judged_on?: Stage;
  judged_on_label?: string;
  overall: SegmentStats;
  campaigns: number;
  test_campaigns_excluded: number;
  thresholds: { min_sent: number; min_responses: number; test_campaign_max: number };
  coverage: {
    sent: number;
    with_delivery_report: number;
    with_known_state: number;
    with_known_category: number;
    responses: number;
  };
  by_dimension: Record<string, DimensionSummary>;
  combinations: SegmentStats[];
  winning_templates: (SegmentStats & { template_id: string | null; header_content: string | null; body: string | null })[];
  recipe: Record<string, { value: string; confidence: Confidence; response_rate: number }>;
}

export interface Suggestion {
  factor: string;
  kind: 'strength' | 'weakness' | 'opportunity' | 'warning' | 'info';
  message: string;
  confidence: Confidence;
}

export interface CampaignRow {
  campaign_id: string;
  name: string;
  /** Under the test threshold: the team trying things on its own phones. */
  is_test: boolean;
  status: string;
  created_at: string;
  sent: number;
  delivered: number | null;
  read: number | null;
  responded: number | null;
  response_rate: number | null;
  tracked: boolean | null;
  vs_all_campaigns: number | null;
  headline: string | null;
  computed_at: string | null;
}

export interface CampaignReport {
  campaign_id: string;
  name: string;
  is_test: boolean;
  status: string;
  started_at: string | null;
  template: string | null;
  metrics: SegmentStats & { total_contacts: number; skipped: number; failed_to_send: number };
  vs_all_campaigns: number | null;
  breakdowns: Record<string, SegmentStats[]>;
  suggestions: Suggestion[];
}

export interface Snapshot {
  snapshot_id: string;
  created_at: string;
  trigger: string;
  campaign: string | null;
  campaigns: number;
  recipients: number;
  responses: number;
  playbook: {
    best: Record<string, string | null>;
    confident: Record<string, boolean>;
  } | null;
}

export interface DimensionInfo {
  key: string;
  label: string;
  group: string;
}

const call = async <T>(path: string, init?: RequestInit): Promise<T> => {
  const res = await fetch(`${BASE}${path}`, { credentials: 'include', ...init });
  const json = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(json.detail || `Request failed (${res.status})`);
  return json as T;
};

export const fetchDimensions = () =>
  call<{ groups: string[]; dimensions: DimensionInfo[]; min_sent: number }>('/dimensions');
export const fetchPlaybook = () => call<Playbook>('/playbook');
export const fetchCampaignInsights = () => call<CampaignRow[]>('/campaigns');
export const fetchCampaignReport = (id: string) => call<CampaignReport>(`/campaigns/${id}`);
export const fetchInsightHistory = () => call<Snapshot[]>('/history');
export const takeSnapshot = () => call<{ snapshot_id: string }>('/snapshot', { method: 'POST' });
export const exploreInsights = (dims: string[], minSent: number) =>
  call<{ dims: string[]; overall: SegmentStats | null; rows: SegmentStats[] }>(
    `/explore?dims=${encodeURIComponent(dims.join(','))}&min_sent=${minSent}`);

// --- The growth plan: leads against the goal, and what to do next -----------

export interface GrowthRow {
  name: string;
  sent: number;
  success: number;
  rate: number | null;
  confidence: Confidence | 'untried';
  direction: 'better' | 'worse' | 'none';
  /** Businesses with a mobile number there that no campaign has messaged. */
  left: number;
}

export interface CreativeRow {
  value: string;
  sent: number;
  success: number;
  rate: number;
  confidence: Confidence;
  direction: 'better' | 'worse' | 'none';
  /** How many campaigns this rests on; one means it may be the place or time. */
  campaigns: number;
}

export interface GrowthPlan {
  computed_at: string;
  goal: {
    target: number;
    deadline: string;
    leads: number;
    still_needed: number;
    days_left: number;
    per_day_needed: number | null;
    on_track: boolean;
    messages_sent: number;
    leads_per_1000: number | null;
    messages_needed: number | null;
    lead_list: { name: string | null; phone: string; submitted_at: string }[];
    /** The goal is set by the agent each month from the business data. */
    label: string;
    /** The month the goal covers: start inclusive, end exclusive (ISO dates). */
    start: string;
    end: string;
    set_by: 'agent';
    basis: string;
    reasoning: string[];
    extra_csps?: number;
    baseline_new_csps?: number;
    go_live_rate?: number;
    state_gaps?: { state: string; target: number; leads: number; gap: number }[];
    /** The month's revenue against the team's revenue goal, when one is set. */
    revenue?: {
      goal_inr: number; month: string; expected_inr: number; expected_basis: string; share: number; gap_inr: number;
      extra_txns: number; extra_txns_per_csp: number; new_csps_this_month: number;
      csps_needed: number; leads_needed: number; horizon_months: number; leads_per_month: number;
    } | null;
    stretch?: number;
  };
  /** From onboarding to revenue, from Tara; null until it has been exported. */
  business: BusinessSummary | null;
  funnel: {
    steps: { key: string; label: string; count: number; from_previous: number | null; waiting: number; of_tracked?: number }[];
    biggest_leak: { step: string; label: string; lost: number; from: number; to: number; advice: string } | null;
  };
  warm_people: { name: string | null; phone: string; stage: string; last_message_at: string | null }[];
  judged_on: Stage;
  judged_on_label: string;
  stages: { key: Stage; label: string; count: number }[];
  targets: {
    judged_on: Stage;
    districts: GrowthRow[];
    categories: GrowthRow[];
    best_pairs: { district: string; category: string; left: number }[];
    reachable_left: number;
  };
  creative: Record<string, any> & {
    untried_angles: string[];
    untried_layouts: string[];
    /** The template that moved the most people, with its image and what it was made of. */
    showcase: {
      template: string; sent: number; success: number; rate: number;
      confidence: Confidence; direction: 'better' | 'worse' | 'none';
      header_content: string | null; body: string;
      recipe: Record<string, string>;
    } | null;
  };
  /** icon: a Material Symbols name. */
  next_steps: { title: string; detail: string; why: string; impact: 'high' | 'medium' | 'low'; icon?: string }[];
}

export const fetchGrowthPlan = () => call<GrowthPlan>('/growth');
/** Revenue goals by month ("2026-10" -> rupees); the agent sets its lead goal from them. */
export const fetchRevenueGoals = () => call<Record<string, number>>('/revenue-goals');
export const setRevenueGoal = (month: string, inr: number | null) =>
  call<Record<string, number>>('/revenue-goals', {
    method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ month, inr }),
  });

export interface BusinessSummary {
  exported_at: string | null;
  months: { month: string; label: string; active_csps: number | null; transactions: number | null;
    revenue_inr: number | null; revenue_basis: 'actual' | 'projected' | 'estimated' | null; new_csps: number | null }[];
  revenue_per_txn: number | null;
  mature_csp: { median_txns: number | null; revenue_inr: number | null };
  new_csp_ramp: { month: number; median_txns: number; revenue_inr: number | null }[];
  new_csps_contribution: { month: string; label: string; from_new_csps_inr: number; share: number }[];
  latest_change: { from: string; to: string; revenue_change_inr: number; csp_change: number; from_new_csps_inr: number } | null;
  csps_live: number | null;
  csps_inactive: number | null;
  onboarding: { applicants: number | null; went_live: number | null; rejected: number | null; in_progress: number | null;
    go_live_rate: number | null; top_rejections: [string, number][] };
  this_month_by_state: { state: string; target: number; leads: number; cat1: number; cat2: number; go_live: number; rejected: number }[];
}
