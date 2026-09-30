import { useState, useEffect, useCallback, Suspense, lazy } from 'react';
import { Sidebar } from './components/Sidebar';
import { Header } from './components/Header';
import { useTheme } from './hooks/useTheme';
import type { NavTab } from './components/Header';
import { useAuth } from './hooks/useAuth';
import { LoginView } from './views/LoginView';
import { BackendSettingsModal } from './components/BackendSettingsModal';
import { fetchStats, fetchDiscoveryStatus, checkBackendHealth } from './api';
import type { NormalizedSystemStats, DiscoveryStatus, ApiError } from './types/api';

// ---------------------------------------------------------------------------
// Lazy-loaded views — each becomes its own chunk so the initial bundle only
// carries the dashboard. The remaining views are fetched on first navigation.
// ---------------------------------------------------------------------------
const DashboardView = lazy(() => import('./views/DashboardView').then(m => ({ default: m.DashboardView })));
const BusinessesView = lazy(() => import('./views/BusinessesView').then(m => ({ default: m.BusinessesView })));
const JobsView = lazy(() => import('./views/JobsView').then(m => ({ default: m.JobsView })));
const ConfigView = lazy(() => import('./views/ConfigView').then(m => ({ default: m.ConfigView })));
const ApprovalsView = lazy(() => import('./views/ApprovalsView').then(m => ({ default: m.ApprovalsView })));
const WhatsAppCampaignView = lazy(() => import('./views/WhatsAppCampaignView').then(m => ({ default: m.WhatsAppCampaignView })));
const WhatsAppTemplatesView = lazy(() => import('./views/WhatsAppTemplatesView').then(m => ({ default: m.WhatsAppTemplatesView })));
const WhatsAppHistoryView = lazy(() => import('./views/WhatsAppHistoryView').then(m => ({ default: m.WhatsAppHistoryView })));

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
  const { user, loading: authLoading, login, logout, signup } = useAuth();
  const [settingsOpen, setSettingsOpen] = useState<boolean>(false);
  const [sidebarOpen, setSidebarOpen] = useState<boolean>(false);
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
    // On a phone the drawer covers the page it just navigated to.
    setSidebarOpen(false);
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

  // Until the session check answers, "signed out" and "not asked yet" look
  // the same, and showing the login screen in that gap would flash it at
  // someone who is already signed in.
  if (authLoading) {
    return (
      <div className="h-screen w-screen flex items-center justify-center bg-slate-950">
        <div className="w-8 h-8 border-3 border-sky-400 border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  if (!user) {
    return <LoginView onLogin={login} onSignup={signup} />;
  }

  return (
    <div className="flex h-screen w-screen overflow-hidden bg-slate-950 text-slate-100 font-sans antialiased select-none">
      {/* Docked Navigation Sidebar (Fixed left, width 240px) */}
      <Sidebar
        activeTab={activeTab}
        isAdmin={user?.role === 'admin'}
        onTabChange={(tab) => handleTabChange(tab)}
        isBackendConnected={isBackendConnected}
        latencyMs={latencyMs}
        onRefreshAll={syncBackend}
        isOpen={sidebarOpen}
        onClose={() => setSidebarOpen(false)}
      />

      {/* Main Content Area */}
      <div className="flex-1 flex flex-col min-w-0 lg:pl-60 h-screen overflow-hidden">
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
          onOpenMenu={() => setSidebarOpen(true)}
          user={user}
          onSignOut={logout}
          searchQuery={searchQuery}
          onSearchChange={setSearchQuery}
        />

        {/* Dynamic Workspace Views */}
        <main className="flex-1 flex flex-col min-w-0 overflow-hidden relative">
          <Suspense fallback={
            <div className="flex-1 flex items-center justify-center">
              <div className="w-7 h-7 border-3 border-sky-400 border-t-transparent rounded-full animate-spin" />
            </div>
          }>
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
          {activeTab === 'approvals' && user?.role === 'admin' && <ApprovalsView />}

          {activeTab === 'whatsapp-campaign' && <WhatsAppCampaignView />}

          {activeTab === 'whatsapp-templates' && <WhatsAppTemplatesView />}

          {activeTab === 'whatsapp-history' && <WhatsAppHistoryView />}
          </Suspense>
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
