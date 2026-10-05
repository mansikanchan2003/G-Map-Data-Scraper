// What each role may see. The server is what enforces it — an operator's
// changes are refused there whatever the page shows — so this only keeps the
// page from offering things that would be refused.

import type { NavTab } from '../components/Header';

export type Role = 'admin' | 'manager' | 'member' | 'operator';

/** Roles that may look and not change. */
export const isReadOnly = (role?: string | null) => role === 'operator';

/** The tabs an operator has: the data, and nothing that exists to act. */
const OPERATOR_TABS: NavTab[] = [
  'dashboard', 'businesses', 'whatsapp-templates', 'whatsapp-history', 'whatsapp-insights',
];

/** Whether a role may open a tab. Access Requests is the administrator's alone. */
export const canOpen = (role: string | null | undefined, tab: NavTab): boolean => {
  if (tab === 'approvals') return role === 'admin';
  if (isReadOnly(role)) return OPERATOR_TABS.includes(tab);
  return true;
};

export const ROLE_LABELS: Record<string, string> = {
  admin: 'Admin', manager: 'Manager', member: 'Member', operator: 'Operator · view only',
};
