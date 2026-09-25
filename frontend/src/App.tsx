import { useState, useEffect, useCallback } from 'react';
import { Sidebar } from './components/Sidebar';
import { Header } from './components/Header';
import { useTheme } from './hooks/useTheme';
import type { NavTab } from './components/Header';
import { BackendSettingsModal } from './components/BackendSettingsModal';
import { DashboardView } from './views/DashboardView';
import { BusinessesView } from './views/BusinessesView';
import { JobsView } from './views/JobsView';
import { ConfigView } from './views/ConfigView';
import { WhatsAppCampaignView } from './views/WhatsAppCampaignView';
import { WhatsAppTemplatesView } from './views/WhatsAppTemplatesView';
import { WhatsAppHistoryView } from './views/WhatsAppHistoryView';
import { fetchStats, fetchDiscoveryStatus, checkBackendHealth } from './api';
import type { NormalizedSystemStats, DiscoveryStatus, ApiError } from './types/api';

export default function App() {
  const [activeTab, setActiveTab] = useState<NavTab>('dashboard');
  const [jobsFilter, setJobsFilter] = useState<string>('All');
  const [searchQuery, setSearchQuery] = useState<string>('');

  // Top-level backend telemetry state
  const [stats, setStats] = useState<NormalizedSystemStats | null>(null);
  const [discoveryStatus, setDiscoveryStatus] = useState<DiscoveryStatus | null>(null);
  const [loadingStats, setLoadingStats] = useState<boolean>(true);
  const [statsError, setStatsError] = useState<ApiError | null>(null);

  // Connection & Diagnostics
  const [isBackendConnected, setIsBackendConnected] = useState<boolean>(false);
  const [latencyMs, setLatencyMs] = useState<number | undefined>(undefined);
  const [isSyncing, setIsSyncing] = useState<boolean>(false);
  const [settingsOpen, setSettingsOpen] = useState<boolean>(false);
  const { theme, toggleTheme } = useTheme();

  // Synchronize hash with activeTab
  useEffect(() => {
    const handleHash = () => {
      const hash = window.location.hash.replace('#', '');
      if (['businesses', 'jobs', 'config', 'dashboard', 'whatsapp-campaign', 'whatsapp-templates', 'whatsapp-history'].includes(hash)) {
        setActiveTab(hash as NavTab);
      }
    };
    handleHash();
    window.addEventListener('hashchange', handleHash);
    return () => window.removeEventListener('hashchange', handleHash);
  }, []);

  const handleTabChange = (tab: NavTab, filter = 'All') => {
    setActiveTab(tab);
    window.location.hash = tab;
    if (tab === 'jobs' && filter) {
      setJobsFilter(filter);
    }
  };

  const syncBackend = useCallback(async () => {
    setIsSyncing(true);
    try {
      const [healthRes, statsRes] = await Promise.all([
        checkBackendHealth().catch((e) => ({ status: 'error', latencyMs: e.latencyMs, err: e })),
        fetchStats().catch((e) => {
          setStatsError(e);
          return null;
        }),
      ]);

      if ('latencyMs' in healthRes && !('err' in healthRes)) {
        setIsBackendConnected(true);
        setLatencyMs(healthRes.latencyMs);
      } else {
        setIsBackendConnected(false);
      }

      if (statsRes) {
        setStats(statsRes);
        setStatsError(null);
        setIsBackendConnected(true);
      }

      // Fetch discovery status
      try {
        const disc = await fetchDiscoveryStatus();
        setDiscoveryStatus(disc);
      } catch {
        // Discovery status optional if backend has no active run
      }
    } catch (err: any) {
      setIsBackendConnected(false);
      setStatsError(err);
    } finally {
      setLoadingStats(false);
      setIsSyncing(false);
    }
  }, []);

  // Initial sync & periodic heartbeat (every 15s)
  useEffect(() => {
    syncBackend();
    const interval = setInterval(() => {
      syncBackend();
    }, 15000);
    return () => clearInterval(interval);
  }, [syncBackend]);

  return (
    <div className="flex h-screen w-screen overflow-hidden bg-slate-950 text-slate-100 font-sans antialiased select-none">
      {/* Docked Navigation Sidebar (Fixed left, width 240px) */}
      <Sidebar
        activeTab={activeTab}
        onTabChange={(tab) => handleTabChange(tab)}
        isBackendConnected={isBackendConnected}
        latencyMs={latencyMs}
        onRefreshAll={syncBackend}
      />

      {/* Main Content Area */}
      <div className="flex-1 flex flex-col min-w-0 pl-60 h-screen overflow-hidden">
        {/* Sticky Header */}
        <Header
          theme={theme}
          onToggleTheme={toggleTheme}
          activeTab={activeTab}
          isBackendConnected={isBackendConnected}
          latencyMs={latencyMs}
          onSyncBackend={syncBackend}
          isSyncing={isSyncing}
          onOpenSettings={() => setSettingsOpen(true)}
          onNavigate={handleTabChange}
          searchQuery={searchQuery}
          onSearchChange={setSearchQuery}
        />

        {/* Dynamic Workspace Views */}
        <main className="flex-1 flex flex-col min-w-0 overflow-hidden relative">
          {activeTab === 'dashboard' && (
            <DashboardView
              stats={stats}
              discoveryStatus={discoveryStatus}
              loading={loadingStats}
              error={statsError}
              onRefresh={syncBackend}
              onNavigate={handleTabChange}
            />
          )}

          {activeTab === 'businesses' && (
            <BusinessesView
              initialSearch={searchQuery}
            />
          )}

          {activeTab === 'jobs' && (
            <JobsView
              stats={stats}
              initialFilter={jobsFilter}
              onRefreshStats={syncBackend}
            />
          )}

          {activeTab === 'config' && <ConfigView />}

          {activeTab === 'whatsapp-campaign' && <WhatsAppCampaignView />}

          {activeTab === 'whatsapp-templates' && <WhatsAppTemplatesView />}

          {activeTab === 'whatsapp-history' && <WhatsAppHistoryView />}
        </main>
      </div>

      {/* Backend API URL / Connection Diagnostics Modal */}
      <BackendSettingsModal
        isOpen={settingsOpen}
        onClose={() => setSettingsOpen(false)}
        onConfigChanged={syncBackend}
      />
    </div>
  );
}
