import React, { useState } from 'react';
import { triggerBatchDiscovery } from '../api';
import type { NavTab } from './Header';

interface SidebarProps {
  activeTab: NavTab;
  /** Below lg the sidebar is a drawer, so it needs to be told when to show. */
  isOpen?: boolean;
  onClose?: () => void;
  onTabChange: (tab: NavTab) => void;
  isBackendConnected: boolean;
  latencyMs?: number;
  onRefreshAll?: () => void;
}

export const Sidebar: React.FC<SidebarProps> = ({
  activeTab,
  isOpen = false,
  onClose,
  onTabChange,
  isBackendConnected,
  latencyMs,
  onRefreshAll,
}) => {
  const [executing, setExecuting] = useState(false);
  const [execFeedback, setExecFeedback] = useState<string | null>(null);

  const handleExecutePipeline = async () => {
    if (executing) return;
    setExecuting(true);
    setExecFeedback(null);
    try {
      const res = await triggerBatchDiscovery(25);
      setExecFeedback(`Batch run #${res.run_id.slice(0, 8)}: ${res.status} (${res.jobs_completed} jobs, ${res.businesses_saved} businesses)`);
      if (onRefreshAll) onRefreshAll();
      setTimeout(() => setExecFeedback(null), 5000);
    } catch (err: any) {
      setExecFeedback(err.message || 'Pipeline execution error');
      setTimeout(() => setExecFeedback(null), 6000);
    } finally {
      setExecuting(false);
    }
  };

  const navItems: { id: NavTab; label: string; icon: string }[] = [
    { id: 'dashboard', label: 'Dashboard', icon: 'dashboard' },
    { id: 'businesses', label: 'Business Data', icon: 'dataset' },
    { id: 'jobs', label: 'Jobs Monitor', icon: 'sync' },
    { id: 'config', label: 'Configuration', icon: 'tune' },
    { id: 'whatsapp-campaign', label: 'WhatsApp Campaign', icon: 'campaign' },
    { id: 'whatsapp-templates', label: 'Templates', icon: 'chat' },
    { id: 'whatsapp-history', label: 'Campaign History', icon: 'history' },
  ];

  return (
    <>
      {/* Backdrop, drawer only. Tapping away is how a drawer is dismissed on a
          phone, and without it the sidebar can trap the reader. */}
      {isOpen && (
        <div
          onClick={onClose}
          className="lg:hidden fixed inset-0 z-40 bg-slate-950/70 backdrop-blur-sm"
          aria-hidden="true"
        />
      )}

      <aside
        className={`fixed left-0 top-0 bottom-0 z-50 flex flex-col justify-between p-3
                    bg-slate-900 border-r border-slate-800 w-60 h-screen shadow-sm select-none
                    transition-transform duration-200
                    ${isOpen ? 'translate-x-0' : '-translate-x-full'} lg:translate-x-0`}
      >
      {/* Top Branding & Navigation */}
      <div className="flex flex-col gap-4">
        {/* Brand Cluster */}
        <div className="flex items-center gap-3 px-2 py-1.5">
          {/* The wordmark is gold throughout, so it reads on both the dark
              sidebar and the teal one the light theme uses -- no plate needed. */}
          <img
            src="/eko-wordmark.svg"
            alt="Eko"
            title="AutoGMap Autonomous Engine"
            className="h-7 w-auto shrink-0"
          />
          <div className="flex flex-col min-w-0">
            <span className="text-[17px] font-bold tracking-tight text-slate-100 uppercase leading-none truncate">
              AutoGMap
            </span>
            <div className="flex items-center gap-1.5 mt-1">
              <span className={`w-1.5 h-1.5 rounded-full ${isBackendConnected ? 'bg-emerald-400 pulse-glow' : 'bg-amber-400'}`} />
              <span className="text-[10px] font-mono-code text-emerald-400 tracking-widest leading-none font-bold uppercase">
                {isBackendConnected ? 'ENGINE ONLINE' : 'DISCONNECTED'}
              </span>
            </div>
          </div>
        </div>

        {/* Real Action: Execute Pipeline (POST /api/v1/discovery/batch) */}
        <div className="space-y-1">
          <button
            onClick={handleExecutePipeline}
            disabled={executing || !isBackendConnected}
            className="w-full flex items-center justify-center gap-2 px-3 py-2 bg-sky-600 text-white rounded font-mono-code text-xs font-semibold hover:bg-sky-500 active:scale-[0.98] transition-transform duration-100 uppercase tracking-wider shadow-sm disabled:opacity-50 cursor-pointer"
            title="Trigger real discovery batch via POST /api/v1/discovery/batch"
          >
            {executing ? (
              <span className="w-3.5 h-3.5 border-2 border-white border-t-transparent rounded-full animate-spin" />
            ) : (
              <span className="material-symbols-outlined text-[16px]">play_arrow</span>
            )}
            <span>{executing ? 'DISPATCHING...' : 'EXECUTE PIPELINE'}</span>
          </button>
          {execFeedback && (
            <div className="text-[10px] font-mono-code text-sky-300 bg-sky-950/80 border border-sky-800 rounded px-2 py-1 truncate text-center">
              {execFeedback}
            </div>
          )}
        </div>

        {/* Navigation Items */}
        <nav className="flex flex-col gap-1 mt-1">
          {navItems.map((item) => {
            const isActive = activeTab === item.id;
            return (
              <button
                key={item.id}
                onClick={() => onTabChange(item.id)}
                className={`flex items-center gap-3 px-3 py-2.5 text-xs font-mono-code rounded transition-colors duration-150 text-left w-full cursor-pointer ${
                  isActive
                    ? 'bg-sky-950/60 text-sky-400 border-l-2 border-sky-500 font-bold shadow-sm'
                    : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/60 font-medium'
                }`}
              >
                <span
                  className={`material-symbols-outlined text-[19px] ${
                    isActive ? 'text-sky-400' : 'text-slate-500'
                  }`}
                >
                  {item.icon}
                </span>
                <span>{item.label}</span>
              </button>
            );
          })}
        </nav>
      </div>

      {/* Bottom Footer & System Diagnostics */}
      <div className="flex flex-col gap-2 pt-3 border-t border-slate-800">
        <div className="flex items-center justify-between px-2.5 py-1.5 bg-slate-950 rounded text-[10px] font-mono-code text-slate-400 border border-slate-800">
          <div className="flex items-center gap-1.5 truncate">
            <span className="material-symbols-outlined text-[14px] text-slate-500">terminal</span>
            <span className="text-slate-300 font-semibold truncate">Data Engine</span>
          </div>
          <span className="text-sky-400 font-semibold shrink-0">v2.0</span>
        </div>

        <div className="flex items-center justify-between px-2.5 py-1 text-[11px] font-mono-code">
          <div className="flex items-center gap-1.5 text-slate-400">
            <span
              className={`material-symbols-outlined text-[14px] ${
                isBackendConnected ? 'text-emerald-400' : 'text-amber-400'
              }`}
            >
              dns
            </span>
            <span>System Health</span>
          </div>
          <span
            className={`font-semibold ${
              isBackendConnected ? 'text-emerald-400' : 'text-amber-400'
            }`}
          >
            {isBackendConnected
              ? latencyMs !== undefined
                ? `Nominal (${latencyMs}ms)`
                : 'Nominal'
              : 'Offline'}
          </span>
        </div>
      </div>
      </aside>
    </>
  );
};
