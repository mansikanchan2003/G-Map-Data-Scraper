import { useState, useEffect, useCallback, Suspense, lazy } from 'react';
import { Sidebar } from './components/Sidebar';
import { Header } from './components/Header';
import { useTheme } from './hooks/useTheme';
import type { NavTab } from './components/Header';
import { useAuth } from './hooks/useAuth';
import { canOpen, isReadOnly } from './utils/permissions';
import { LoginView } from './views/LoginView';
import { BackendSettingsModal } from './components/BackendSettingsModal';
import { ChangePasswordForm } from './components/ChangePasswordForm';
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
const TemplateStudioView = lazy(() => import('./views/TemplateStudioView').then(m => ({ default: m.TemplateStudioView })));
const CampaignInsightsView = lazy(() => import('./views/CampaignInsightsView').then(m => ({ default: m.CampaignInsightsView })));
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
  const [changingPassword, setChangingPassword] = useState<boolean>(false);
  const [sidebarOpen, setSidebarOpen] = useState<boolean>(false);
  const { theme, toggleTheme } = useTheme();

  // Synchronize hash with activeTab
  useEffect(() => {
    const handleHash = () => {
      let hash = window.location.hash.replace('#', '');
      // Approval emails sent before this used #admin-approvals.
      if (hash === 'admin-approvals') hash = 'approvals';
      // 'approvals' is listed so the email link and a refresh land on the
      // queue; it still renders only for admins.
      if (['businesses', 'jobs', 'config', 'dashboard', 'whatsapp-campaign', 'whatsapp-templates', 'whatsapp-studio', 'whatsapp-history', 'whatsapp-insights', 'approvals'].includes(hash)) {
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

  // A tab the role may not open — reached by a typed address or a saved
  // link — falls back to the dashboard rather than showing a page of errors.
  const shownTab: NavTab = canOpen(user.role, activeTab) ? activeTab : 'dashboard';
  const readOnly = isReadOnly(user.role);

  return (
    <div className={`flex h-screen w-screen overflow-hidden bg-slate-950 text-slate-100 font-sans antialiased select-none ${readOnly ? 'read-only' : ''}`}>
      {/* Docked Navigation Sidebar (Fixed left, width 240px) */}
      <Sidebar
        activeTab={shownTab}
        role={user.role}
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
          activeTab={shownTab}
          isBackendConnected={isBackendConnected}
          latencyMs={latencyMs}
          onSyncBackend={syncBackend}
          isSyncing={isSyncing}
          onOpenSettings={() => setSettingsOpen(true)}
          onOpenMenu={() => setSidebarOpen(true)}
          user={user}
          onSignOut={logout}
          onChangePassword={() => setChangingPassword(true)}
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
          {shownTab === 'dashboard' && (
            <DashboardView
              stats={stats}
              discoveryStatus={discoveryStatus}
              loading={loadingStats}
              error={statsError}
              onRefresh={syncBackend}
              onNavigate={handleTabChange}
            />
          )}

          {shownTab === 'businesses' && (
            <BusinessesView
              initialSearch={searchQuery}
            />
          )}

          {shownTab === 'jobs' && (
            <JobsView
              stats={stats}
              initialFilter={jobsFilter}
              onRefreshStats={syncBackend}
            />
          )}

          {shownTab === 'config' && <ConfigView />}
          {shownTab === 'approvals' && user?.role === 'admin' && <ApprovalsView />}

          {shownTab === 'whatsapp-campaign' && <WhatsAppCampaignView />}

          {shownTab === 'whatsapp-templates' && <WhatsAppTemplatesView />}

          {shownTab === 'whatsapp-studio' && <TemplateStudioView />}

          {shownTab === 'whatsapp-history' && <WhatsAppHistoryView />}

          {shownTab === 'whatsapp-insights' && <CampaignInsightsView />}
          </Suspense>
        </main>
      </div>

      {/* Backend API URL / Connection Diagnostics Modal */}
      {changingPassword && (
        <div className="fixed inset-0 z-50 bg-black/70 flex items-center justify-center p-4">
          <div className="w-full max-w-sm bg-slate-900 border border-slate-700 rounded-lg p-5 shadow-xl select-text">
            <h2 className="text-sm font-semibold text-slate-100 mb-3">Change your password</h2>
            <ChangePasswordForm
              email={user.email}
              onCancel={() => setChangingPassword(false)}
              onDone={message => {
                // The change ended every session, this one included, so the
                // sign-in page is where the new password is first used.
                setChangingPassword(false);
                window.alert(message);
                logout();
              }}
            />
          </div>
        </div>
      )}

      <BackendSettingsModal
        isOpen={settingsOpen}
        onClose={() => setSettingsOpen(false)}
        onConfigChanged={syncBackend}
      />
    </div>
  );
}
