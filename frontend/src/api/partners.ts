import { getApiBaseUrl } from './index';

// Resolved per call so the backend-URL override in Settings applies at once.
const base = () => `${getApiBaseUrl()}/api/v1/partners`;

export interface PartnerOrganisation {
  business_id: string;
  name: string;
  /** The Google Maps category it was found under, e.g. "Self help group". */
  type: string;
  phone: string | null;
  email: string | null;
  website: string | null;
  address: string | null;
  district: string | null;
  state: string | null;
  google_maps_url: string | null;
  /** The SBI branch PIN code it was found at. */
  pincode: string;
  branches: { code: string; name: string }[];
  discovered_at: string | null;
}

export interface PartnerList {
  partners: PartnerOrganisation[];
  /** Every kind searched for, with why it is a useful partner. */
  types: { value: string; why: string }[];
  branches: { code: string; name: string; pincode: string }[];
  /** Scraping jobs for these kinds at branch PINs. */
  progress: { total: number; done: number; pending: number; failed: number };
}

export const fetchPartners = async (filters: { type?: string; branch?: string; q?: string }): Promise<PartnerList> => {
  const params = new URLSearchParams();
  if (filters.type) params.set('type', filters.type);
  if (filters.branch) params.set('branch', filters.branch);
  if (filters.q?.trim()) params.set('q', filters.q.trim());
  const res = await fetch(`${base()}?${params}`, { credentials: 'include' });
  const json = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(json.detail || `Could not load partner organisations (${res.status})`);
  return json as PartnerList;
};
