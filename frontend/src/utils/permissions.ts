// What each role may see. The server is what enforces it — a member's
// changes are refused there whatever the page shows — so this only keeps the
// page from offering things that would be refused.

import type { NavTab } from '../components/Header';

export type Role = 'admin' | 'manager' | 'member' | 'operator';

/** Roles that may look and not change. */
export const isReadOnly = (role?: string | null) => role === 'member';

/** The tabs a member has: the data, and nothing that exists to act. */
const VIEW_ONLY_TABS: NavTab[] = [
  'dashboard', 'businesses', 'partners', 'whatsapp-templates', 'whatsapp-history', 'whatsapp-insights',
];

/**
 * Whether an account may open a tab. Access Requests is the administrator's
 * alone. An account limited to some tabs (allowed) sees only those, within
 * what its role allows.
 */
export const canOpen = (role: string | null | undefined, tab: NavTab, allowed?: string[] | null): boolean => {
  if (tab === 'approvals') return role === 'admin';
  if (allowed && allowed.length && role !== 'admin' && !allowed.includes(tab)) return false;
  if (isReadOnly(role)) return VIEW_ONLY_TABS.includes(tab);
  return true;
};

/** The tab an account lands on: the dashboard, or the first it is allowed. */
export const homeTab = (role: string | null | undefined, allowed?: string[] | null): NavTab =>
  canOpen(role, 'dashboard', allowed) ? 'dashboard' : ((allowed?.[0] as NavTab) || 'dashboard');

export const ROLE_LABELS: Record<string, string> = {
  admin: 'Admin', manager: 'Manager', operator: 'Operator', member: 'Member · view only',
};
