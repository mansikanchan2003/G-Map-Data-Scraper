import React from 'react';
import type { NavTab } from './Header';

/**
 * Pages that live inside another tab rather than in the sidebar (the user,
 * 2026-10-22): Dispositions in Applications, Template Studio in Templates,
 * Campaign Insights in Campaign History. Each keeps its own address and its
 * own permission, so an account allowed one keeps it.
 */
export const PARENT_TAB: Partial<Record<NavTab, NavTab>> = {
  dispositions: 'applications',
  'whatsapp-studio': 'whatsapp-templates',
  'whatsapp-insights': 'whatsapp-history',
  'agent-quality': 'dashboard',
};

const LABEL: Partial<Record<NavTab, string>> = {
  applications: 'Applications', 'whatsapp-templates': 'Templates', 'whatsapp-history': 'Campaign History', dashboard: 'Dashboard',
};

/** The button on the parent page that opens a page inside it. */
export const SubPageButton: React.FC<{ tab: NavTab; label: string; icon: string; className?: string; style?: React.CSSProperties }> =
  ({ tab, label, icon, className = '', style }) => (
  <button onClick={() => { window.location.hash = tab; }} style={style}
    className={`h-9 px-3.5 rounded-lg text-sm font-semibold flex items-center gap-1.5 shadow-sm hover:opacity-90 cursor-pointer ${className}`}>
    <span className="material-symbols-outlined text-[18px]">{icon}</span>{label}
  </button>
);

/** "← Applications" above a page that lives inside another; shown only when the account can open the parent. */
export const BackToParent: React.FC<{ tab: NavTab; can?: (t: NavTab) => boolean }> = ({ tab, can }) => {
  const parent = PARENT_TAB[tab];
  if (!parent || (can && !can(parent))) return null;
  return (
    <button onClick={() => { window.location.hash = parent; }}
      className="text-[12.5px] text-sky-300 hover:underline flex items-center gap-1 mb-1 cursor-pointer">
      <span className="material-symbols-outlined text-[16px]">arrow_back</span>{LABEL[parent]}
    </button>
  );
};
