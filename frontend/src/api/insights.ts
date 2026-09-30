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
  ci_low: number;
  ci_high: number;
  tracked: boolean;
  delivery_rate: number | null;
  read_rate: number | null;
  lift: number | null;
  confidence: Confidence;
  direction: 'better' | 'worse' | 'none';
}

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
