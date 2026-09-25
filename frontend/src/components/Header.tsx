import React, { useState } from 'react';
import { triggerCsvStream } from '../api';
import { ThemeToggle } from './ThemeToggle';
import type { Theme } from '../hooks/useTheme';

export type NavTab = 'dashboard' | 'businesses' | 'jobs' | 'config' | 'whatsapp-campaign' | 'whatsapp-templates' | 'whatsapp-history';

interface HeaderProps {
  activeTab: NavTab;
  isBackendConnected: boolean;
  latencyMs?: number;
  onSyncBackend: () => void;
  isSyncing: boolean;
  onOpenSettings: () => void;
  onNavigate: (tab: NavTab) => void;
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
  onNavigate,
  searchQuery,
  onSearchChange,
  theme,
  onToggleTheme,
}) => {
  const [downloading, setDownloading] = useState(false);

  const handleExportCsv = () => {
    setDownloading(true);
    try {
      triggerCsvStream();
    } finally {
      setTimeout(() => setDownloading(false), 2000);
    }
  };

  const breadcrumbs: Record<NavTab, { section: string; sub: string }> = {
    dashboard: { section: 'operations', sub: 'telemetry' },
    businesses: { section: 'records', sub: 'discovered-businesses' },
    jobs: { section: 'orchestration', sub: 'jobs-monitor' },
    config: { section: 'configuration', sub: 'matrix-sources' },
    'whatsapp-campaign': { section: 'whatsapp', sub: 'campaign-builder' },
    'whatsapp-templates': { section: 'whatsapp', sub: 'templates' },
    'whatsapp-history': { section: 'whatsapp', sub: 'history' },
  };

  const { section, sub } = breadcrumbs[activeTab] || breadcrumbs['dashboard'];

  return (
    <header className="sticky top-0 z-30 flex items-center justify-between px-4 h-14 w-full bg-slate-900 border-b border-slate-800 shadow-sm select-none shrink-0">
      {/* Search and Breadcrumbs on Left */}
      <div className="flex items-center gap-4 max-w-lg w-full">
        <div className="hidden sm:flex items-center gap-1.5 text-[11px] font-mono-code text-slate-400 shrink-0">
          <span className="text-sky-400 font-semibold uppercase">AutoGMap</span>
          <span>/</span>
          <span className="text-slate-200 font-medium">{section}</span>
          <span>/</span>
          <span className="text-sky-400 font-semibold">{sub}</span>
        </div>

        <div className="relative flex-1 flex items-center min-w-[180px]">
          <span className="material-symbols-outlined absolute left-2.5 text-slate-500 text-[16px]">
            search
          </span>
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => onSearchChange(e.target.value)}
            placeholder="Search across coordinates, category or job..."
            className="w-full h-8 pl-8 pr-7 text-xs font-mono-code bg-slate-950 border border-slate-700 rounded text-slate-100 placeholder:text-slate-500 focus:outline-none focus:border-sky-500 focus:ring-1 focus:ring-sky-500 transition-all"
          />
        </div>
      </div>

      {/* Genuine Navigation Shortcuts */}
      <nav className="hidden xl:flex items-center gap-5">
        <button
          onClick={() => onNavigate('dashboard')}
          className={`text-xs font-mono-code flex items-center gap-1.5 cursor-pointer transition-colors ${
            activeTab === 'dashboard' ? 'text-sky-400 font-semibold' : 'text-slate-400 hover:text-slate-200'
          }`}
        >
          <span className={`w-1.5 h-1.5 rounded-full ${activeTab === 'dashboard' ? 'bg-sky-400' : 'bg-slate-600'}`} />
          Operations
        </button>
        <button
          onClick={() => onNavigate('jobs')}
          className={`text-xs font-mono-code flex items-center gap-1.5 cursor-pointer transition-colors ${
            activeTab === 'jobs' ? 'text-sky-400 font-semibold' : 'text-slate-400 hover:text-slate-200'
          }`}
        >
          <span className={`w-1.5 h-1.5 rounded-full ${activeTab === 'jobs' ? 'bg-sky-400' : 'bg-slate-600'}`} />
          Jobs Queue
        </button>
        <button
          onClick={() => onNavigate('businesses')}
          className={`text-xs font-mono-code flex items-center gap-1.5 cursor-pointer transition-colors ${
            activeTab === 'businesses' ? 'text-sky-400 font-semibold' : 'text-slate-400 hover:text-slate-200'
          }`}
        >
          <span className={`w-1.5 h-1.5 rounded-full ${activeTab === 'businesses' ? 'bg-sky-400' : 'bg-slate-600'}`} />
          Discovered Data
        </button>
      </nav>

      {/* Right Actions & Health Indicators */}
      <div className="flex items-center gap-2 sm:gap-3">
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
          <span className="md:hidden">{isBackendConnected ? 'Online' : 'Offline'}</span>
        </button>

        <div className="h-4 w-px bg-slate-800" />

        {/* Sync Backend Action */}
        <button
          onClick={onSyncBackend}
          disabled={isSyncing}
          className="h-8 px-2.5 text-xs font-mono-code bg-slate-800 border border-slate-700 hover:bg-slate-700 text-slate-200 rounded flex items-center gap-1.5 transition-colors cursor-pointer disabled:opacity-50 shadow-sm"
          title="Manual sync with FastAPI backend"
        >
          <span
            className={`material-symbols-outlined text-[15px] text-slate-400 ${
              isSyncing ? 'animate-spin' : ''
            }`}
          >
            sync
          </span>
          <span className="hidden sm:inline font-semibold">SYNC BACKEND</span>
        </button>

        {/* Export Stream / Download Data Action */}
        <div className="relative group">
          <button
            onClick={handleExportCsv}
            disabled={downloading}
            className="h-8 px-3 text-xs font-mono-code bg-sky-600 hover:bg-sky-500 text-white rounded flex items-center gap-1.5 font-bold transition-colors shadow-sm cursor-pointer active:scale-95 disabled:opacity-50"
            title="Download full business dataset via backend streaming endpoint"
          >
            <span className="material-symbols-outlined text-[15px]">
              {downloading ? 'sync' : 'cloud_download'}
            </span>
            <span className="hidden sm:inline">DOWNLOAD DATA</span>
            <span className="sm:hidden">CSV</span>
          </button>
          <div className="absolute right-0 top-full mt-1 hidden group-hover:flex flex-col z-50 w-72 p-2.5 bg-slate-900 border border-slate-700 rounded shadow-xl pointer-events-none text-left">
            <span className="text-[10px] font-mono-code text-sky-400 font-bold uppercase">
              Streaming CSV Endpoint
            </span>
            <span className="text-[11px] font-mono-code text-slate-200 mt-0.5 break-all font-semibold">
              GET /api/v1/export/businesses?format=csv
            </span>
            <span className="text-[10px] text-slate-400 mt-1">
              Streams full dataset directly from FastAPI backend with zero browser memory bloat.
            </span>
          </div>
        </div>

        {/* Utility Icon Cluster */}
        <div className="flex items-center gap-1 pl-1">
          <button
            onClick={onSyncBackend}
            className="w-8 h-8 flex items-center justify-center text-slate-400 hover:text-slate-100 hover:bg-slate-800 rounded transition-colors cursor-pointer"
            title="Refresh Telemetry"
          >
            <span className="material-symbols-outlined text-[18px]">refresh</span>
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

        {/* Operator Badge */}
        <div
          className="w-7 h-7 rounded border border-slate-700 bg-sky-950 flex items-center justify-center text-sky-400 font-mono-code text-xs font-bold ml-1"
          title="Operator Node Active"
        >
          OP
        </div>
      </div>
    </header>
  );
};
