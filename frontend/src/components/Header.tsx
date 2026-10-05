import React from 'react';
import { ThemeToggle } from './ThemeToggle';
import type { Theme } from '../hooks/useTheme';

export type NavTab = 'dashboard' | 'businesses' | 'jobs' | 'config' | 'whatsapp-campaign' | 'whatsapp-templates' | 'whatsapp-studio' | 'whatsapp-insights' | 'whatsapp-history' | 'approvals';

interface HeaderProps {
  activeTab: NavTab;
  isBackendConnected: boolean;
  latencyMs?: number;
  onSyncBackend: () => void;
  isSyncing: boolean;
  onOpenSettings: () => void;
  /** Opens the nav drawer; only rendered below lg, where it is hidden. */
  onOpenMenu: () => void;
  /** Null only while signed out, which the app never renders this with. */
  user?: { email: string; full_name: string | null; role: string } | null;
  onSignOut?: () => void;
  searchQuery: string;
  onSearchChange: (q: string) => void;
  theme: Theme;
  onToggleTheme: () => void;
}

export const Header: React.FC<HeaderProps> = ({
  activeTab,
  isBackendConnected,
  latencyMs,
  onSyncBackend,
  isSyncing,
  onOpenSettings,
  onOpenMenu,
  user,
  onSignOut,
  searchQuery,
  onSearchChange,
  theme,
  onToggleTheme,
}) => {


  const breadcrumbs: Record<NavTab, { section: string; sub: string }> = {
    dashboard: { section: 'operations', sub: 'telemetry' },
    businesses: { section: 'records', sub: 'discovered-businesses' },
    jobs: { section: 'orchestration', sub: 'jobs-monitor' },
    config: { section: 'configuration', sub: 'matrix-sources' },
    'whatsapp-campaign': { section: 'whatsapp', sub: 'campaign-builder' },
    'whatsapp-templates': { section: 'whatsapp', sub: 'templates' },
    'whatsapp-studio': { section: 'whatsapp', sub: 'template studio' },
    'whatsapp-insights': { section: 'whatsapp', sub: 'campaign insights' },
    'whatsapp-history': { section: 'whatsapp', sub: 'history' },
    'approvals': { section: 'admin', sub: 'access-requests' },
  };

  const { section, sub } = breadcrumbs[activeTab] || breadcrumbs['dashboard'];

  return (
    <header className="sticky top-0 z-30 flex items-center justify-between px-4 h-14 w-full bg-slate-900 border-b border-slate-800 shadow-sm select-none shrink-0">
      {/* Search and Breadcrumbs on Left */}
      <div className="flex items-center gap-2 sm:gap-4 flex-1 min-w-0 lg:max-w-lg">
        {/* The sidebar is a drawer below lg, so it needs a way back. */}
        <button
          onClick={onOpenMenu}
          className="lg:hidden w-9 h-9 -ml-1.5 flex items-center justify-center shrink-0 rounded
                     text-slate-300 hover:text-slate-100 hover:bg-slate-800 transition-colors cursor-pointer"
          title="Open navigation"
          aria-label="Open navigation"
        >
          <span className="material-symbols-outlined text-[22px]">menu</span>
        </button>

        <div className="hidden xl:flex items-center gap-1.5 text-[11px] font-mono-code text-slate-400 shrink-0">
          <span className="text-sky-400 font-semibold uppercase">AutoGMap</span>
          <span>/</span>
          <span className="text-slate-200 font-medium">{section}</span>
          <span>/</span>
          <span className="text-sky-400 font-semibold">{sub}</span>
        </div>

        <div className="relative flex-1 flex items-center min-w-0">
          <span className="material-symbols-outlined absolute left-2.5 text-slate-500 text-[16px]">
            search
          </span>
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => onSearchChange(e.target.value)}
            placeholder="Search..."
            className="w-full h-8 pl-8 pr-7 text-xs font-mono-code bg-slate-950 border border-slate-700 rounded text-slate-100 placeholder:text-slate-500 focus:outline-none focus:border-sky-500 focus:ring-1 focus:ring-sky-500 transition-all"
          />
        </div>
      </div>

      {/* Right Actions & Health Indicators */}
      <div className="flex items-center gap-1.5 sm:gap-3 shrink-0">
        {/* Backend Connection Live Pill */}
        <button
          onClick={onOpenSettings}
          className={`flex items-center gap-1.5 px-2.5 py-1 border rounded text-[11px] font-mono-code font-semibold transition-all cursor-pointer ${
            isBackendConnected
              ? 'bg-emerald-950/70 border-emerald-800 text-emerald-400 hover:bg-emerald-900/60'
              : 'bg-rose-950/70 border-rose-800 text-rose-400 hover:bg-rose-900/60'
          }`}
          title="Click to view or change backend API settings"
        >
          <span
            className={`w-2 h-2 rounded-full ${
              isBackendConnected ? 'bg-emerald-400 pulse-glow' : 'bg-rose-500'
            }`}
          />
          <span className="hidden md:inline">
            {isBackendConnected
              ? `Backend Connected ${latencyMs ? `(${latencyMs}ms)` : ''}`
              : 'Backend Offline'}
          </span>
          {/* On the narrowest screens the dot is the whole message: its colour
              says connected or not, and the button's title spells it out. */}
          <span className="hidden sm:inline md:hidden">
            {isBackendConnected ? 'Online' : 'Offline'}
          </span>
        </button>

        <div className="h-4 w-px bg-slate-800" />

        {/* Utility Icon Cluster */}
        <div className="flex items-center gap-1 pl-1">
          <button
            onClick={onSyncBackend}
            disabled={isSyncing}
            className="w-8 h-8 flex items-center justify-center text-slate-400 hover:text-slate-100 hover:bg-slate-800 rounded transition-colors cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed"
            title={isSyncing ? 'Syncing with backend...' : 'Refresh telemetry from the backend'}
          >
            <span className={`material-symbols-outlined text-[18px] ${isSyncing ? 'animate-spin' : ''}`}>
              refresh
            </span>
          </button>
          <button
            onClick={onOpenSettings}
            className="w-8 h-8 flex items-center justify-center text-slate-400 hover:text-slate-100 hover:bg-slate-800 rounded transition-colors cursor-pointer"
            title="Backend Settings"
          >
            <span className="material-symbols-outlined text-[18px]">tune</span>
          </button>
          <ThemeToggle theme={theme} onToggle={onToggleTheme} />
        </div>

        {/* Who is signed in, and the way out */}
        <div className="relative ml-1 group">
          <button
            className="w-8 h-8 rounded-full border border-slate-700 bg-sky-950 flex items-center
                       justify-center text-sky-400 font-mono-code text-xs font-bold cursor-pointer
                       hover:border-sky-600 transition-colors"
            title={user ? `${user.email} (${user.role})` : 'Account'}
            aria-label="Account"
          >
            {(user?.full_name || user?.email || 'OP').slice(0, 2).toUpperCase()}
          </button>

          {/* Opens on hover and on keyboard focus, so it is reachable without
              a pointer as well. */}
          <div className="absolute right-0 top-full mt-1 z-50 w-56 p-1.5 bg-slate-900 border
                          border-slate-700 rounded shadow-xl hidden
                          group-hover:block group-focus-within:block">
            <div className="px-2.5 py-2 border-b border-slate-800">
              <div className="text-xs font-semibold text-slate-200 truncate">
                {user?.full_name || user?.email?.split('@')[0] || 'Signed in'}
              </div>
              <div className="text-[11px] font-mono-code text-slate-500 truncate" title={user?.email}>
                {user?.email}
              </div>
              {user?.role === 'admin' && (
                <span className="inline-block mt-1 text-[10px] px-1.5 py-0.5 rounded uppercase
                                 font-semibold border text-sky-400 border-sky-800 bg-sky-950/50">
                  admin
                </span>
              )}
              {user?.role === 'manager' && (
                <span className="inline-block mt-1 text-[10px] px-1.5 py-0.5 rounded uppercase
                                 font-semibold border text-violet-300 border-violet-800 bg-violet-950/50">
                  manager
                </span>
              )}
              {user?.role === 'operator' && (
                <span className="inline-block mt-1 text-[10px] px-1.5 py-0.5 rounded uppercase
                                 font-semibold border text-amber-300 border-amber-800 bg-amber-950/50">
                  operator · view only
                </span>
              )}
            </div>
            <button
              onClick={onSignOut}
              className="w-full mt-1 flex items-center gap-2 px-2.5 py-2 rounded text-left text-xs
                         text-slate-300 hover:bg-slate-800 hover:text-slate-100
                         transition-colors cursor-pointer"
            >
              <span className="material-symbols-outlined text-[16px]">logout</span>
              Sign out
            </button>
          </div>
        </div>
      </div>
    </header>
  );
};
