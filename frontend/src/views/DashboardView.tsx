import { SubPageButton } from '../components/SubPage';
import { formatDateTime } from '../utils/datetime';
import { MissingStepsCard } from '../components/MissingStepsCard';
import { DispositionAlertCard } from '../components/DispositionAlertCard';
import React, { useState } from 'react';
import { DiscoveryRunner } from '../components/DiscoveryRunner';
import { AutopilotPanel } from '../components/AutopilotPanel';
import { LeadsPanel } from '../components/LeadsPanel';
import { ScaleBars } from '../components/ScaleBars';
import { JobDistributionDonut } from '../components/JobDistributionDonut';
import type { NormalizedSystemStats, DiscoveryStatus, ApiError } from '../types/api';
import type { NavTab } from '../components/Header';
import { retryAllFailedJobs, triggerBatchDiscovery, stopDiscovery } from '../api';

interface DashboardViewProps {
  stats: NormalizedSystemStats | null;
  discoveryStatus: DiscoveryStatus | null;
  loading: boolean;
  error: ApiError | null;
  onRefresh: () => void;
  onNavigate: (tab: NavTab, filter?: string) => void;
}

export const DashboardView: React.FC<DashboardViewProps> = ({
  stats,
  discoveryStatus,
  loading,
  error,
  onRefresh,
  onNavigate,
}) => {
  const [runnerOpen, setRunnerOpen] = useState(false);
  const [actionLoading, setActionLoading] = useState<string | null>(null);
  const [actionMsg, setActionMsg] = useState<string | null>(null);

  const handleRetryFailed = async () => {
    setActionLoading('retry');
    setActionMsg(null);
    try {
      const res = await retryAllFailedJobs('FAILED');
      setActionMsg(res.message || `Re-queued ${res.jobs_retried} failed jobs`);
      onRefresh();
    } catch (e: any) {
      setActionMsg(e.message || 'Failed to retry jobs');
    } finally {
      setActionLoading(null);
    }
  };

  const handleTriggerPipeline = async () => {
    setActionLoading('pipeline');
    setActionMsg(null);
    try {
      const res = await triggerBatchDiscovery(25);
      setActionMsg(`Batch run #${res.run_id.slice(0, 8)}: ${res.status} (${res.jobs_completed} completed, ${res.businesses_saved} saved)`);
      onRefresh();
    } catch (e: any) {
      setActionMsg(e.message || 'Execution error');
    } finally {
      setActionLoading(null);
    }
  };

  const handleStopDiscovery = async () => {
    setActionLoading('stop');
    setActionMsg(null);
    try {
      const res = await stopDiscovery();
      setActionMsg(res.message || 'Discovery stop signal sent');
      onRefresh();
    } catch (e: any) {
      setActionMsg(e.message || 'Failed to stop discovery');
    } finally {
      setActionLoading(null);
    }
  };

  // Real backend metrics
  const totalLocations = stats?.locations_count ?? 0;
  const totalCategories = stats?.categories_count ?? 0;
  const totalJobs = stats?.total_jobs ?? 0;
  const totalBusinesses = stats?.total_businesses ?? 0;
  const validBusinesses = stats?.valid_businesses ?? 0;

  const pendingJobs = stats?.pending_jobs ?? 0;
  const runningJobs = stats?.running_jobs ?? 0;
  const completedJobs = stats?.completed_jobs ?? 0;
  const partialJobs = stats?.partial_jobs ?? 0;
  const failedJobs = stats?.failed_jobs ?? 0;
  const blockedJobs = stats?.blocked_jobs ?? 0;

  const totalCalculated = totalJobs || (pendingJobs + runningJobs + completedJobs + partialJobs + failedJobs + blockedJobs) || 1;
  const pctCompleted = ((completedJobs / totalCalculated) * 100).toFixed(1);

  const isDiscoveryRunning = discoveryStatus?.is_running || runningJobs > 0;
  const doneJobs = completedJobs + partialJobs;
  const pctDone = Math.round((doneJobs / totalCalculated) * 100);
  const R = 46, C = 2 * Math.PI * R;
  const last = stats?.last_run;
  const lastTotal = last?.jobs_total ?? 0;

  return (
    <div className="flex-1 p-4 lg:p-6 flex flex-col gap-6 overflow-y-auto select-none bg-slate-950 text-slate-100 [&>*]:shrink-0">
      {/* The headline, in Eko's deep teal (the same in both themes): what the
          scraper has found, how far through the work it is, and the buttons
          used most. */}
      <section className="relative overflow-hidden rounded-2xl shadow-md text-white"
        style={{ background: 'linear-gradient(120deg, #0a3543 0%, #16435a 55%, #1d5a6e 100%)' }}>
        <span className="material-symbols-outlined absolute -right-10 -bottom-16 text-[260px] text-white/5 pointer-events-none select-none">travel_explore</span>
        <div className="relative p-6 flex flex-wrap items-center gap-6">
          <div className="relative h-[124px] w-[124px] shrink-0">
            <svg viewBox="0 0 110 110" className="h-full w-full -rotate-90" aria-hidden="true">
              <circle cx="55" cy="55" r={R} fill="none" stroke="rgba(255,255,255,0.14)" strokeWidth="10" />
              <circle cx="55" cy="55" r={R} fill="none" stroke="#f9ab10" strokeWidth="10" strokeLinecap="round"
                strokeDasharray={`${(pctDone / 100) * C} ${C}`} className="transition-all duration-700" />
            </svg>
            <div className="absolute inset-0 flex flex-col items-center justify-center">
              <span className="text-[28px] font-bold tabular-nums leading-none">{pctDone}%</span>
              <span className="text-[11px] text-white/70 mt-0.5">jobs searched</span>
            </div>
          </div>
          <div className="flex-1 min-w-[240px]">
            <div className="text-[11px] uppercase tracking-[0.14em] font-semibold flex flex-wrap items-center gap-2" style={{ color: '#f9ab10' }}>
              Google Maps discovery
              <span className={`normal-case tracking-normal inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-[11px] font-semibold ${isDiscoveryRunning ? 'bg-emerald-400/20 text-emerald-200' : 'bg-white/10 text-white/80'}`}>
                <span className={`h-1.5 w-1.5 rounded-full ${isDiscoveryRunning ? 'bg-emerald-300 animate-pulse' : 'bg-white/50'}`} />
                {isDiscoveryRunning ? `Scraping now · ${runningJobs} running` : 'Idle'}
              </span>
            </div>
            <div className="mt-1 flex items-baseline flex-wrap gap-x-3">
              <span className="text-4xl sm:text-5xl font-semibold tabular-nums">{totalBusinesses.toLocaleString('en-IN')}</span>
              <span className="text-sm text-white/75">businesses found · <b className="text-white">{validBusinesses.toLocaleString('en-IN')}</b> valid</span>
            </div>
            <p className="text-sm text-white/70 mt-1">
              {totalLocations.toLocaleString('en-IN')} PINs × {totalCategories.toLocaleString('en-IN')} categories = {totalJobs.toLocaleString('en-IN')} searches to make.
            </p>
          </div>
          <div className="flex flex-wrap gap-2" data-edit>
            <button onClick={handleTriggerPipeline} disabled={actionLoading !== null || isDiscoveryRunning}
              className="h-10 px-4 rounded-lg text-[13px] font-bold text-[#0a3543] inline-flex items-center gap-1.5 shadow-md hover:brightness-110 disabled:opacity-50 cursor-pointer"
              style={{ background: '#f9ab10' }}>
              <span className="material-symbols-outlined text-[18px]">play_arrow</span>Run a batch
            </button>
            <button onClick={() => setRunnerOpen(true)}
              className="h-10 px-4 rounded-lg text-[13px] font-semibold bg-white/10 hover:bg-white/20 ring-1 ring-white/20 inline-flex items-center gap-1.5 cursor-pointer">
              <span className="material-symbols-outlined text-[18px]">travel_explore</span>Choose targets
            </button>
            <SubPageButton tab="agent-quality" label="Agent quality" icon="psychology"
              className="h-10 px-4 text-[13px] rounded-lg bg-violet-500/90 hover:bg-violet-500 text-white" />
          </div>
        </div>
        <div className="relative grid grid-cols-2 lg:grid-cols-4 gap-3 px-6 pb-6">
          {([
            ['COMPLETED', 'Searched', doneJobs, 'task_alt', '#6ee7b7'],
            ['PENDING', 'Waiting', pendingJobs, 'hourglass_top', '#7dd3fc'],
            ['RUNNING', 'Running now', runningJobs, 'autorenew', '#f9ab10'],
            ['FAILED', 'Failed or blocked', failedJobs + blockedJobs, 'error', '#fda4af'],
          ] as const).map(([key, label, value, icon, colour]) => (
            <button key={key} onClick={() => onNavigate('jobs', key)}
              className="text-left rounded-xl px-4 py-3 bg-white/10 hover:bg-white/15 transition cursor-pointer">
              <div className="flex items-center justify-between">
                <span className="flex items-center gap-1.5 text-white/75 text-[12px]">
                  <span className="material-symbols-outlined text-[16px]" style={{ color: colour }}>{icon}</span>{label}
                </span>
                <span className="text-[11.5px] tabular-nums text-white/60">{Math.round((value / totalCalculated) * 100)}%</span>
              </div>
              <div className="text-2xl font-semibold tabular-nums mt-1">{value.toLocaleString('en-IN')}</div>
              <div className="h-1.5 rounded-full bg-white/10 mt-2 overflow-hidden">
                <div className="h-full rounded-full" style={{ width: `${(value / totalCalculated) * 100}%`, background: colour }} />
              </div>
            </button>
          ))}
        </div>
      </section>

      {/* Leads whose recorded steps do not add up; green and quiet when all do. */}
      <MissingStepsCard />

      {/* Leads with no disposition where one is due, and action items missing or overdue. */}
      <DispositionAlertCard />

      {/* Action feedback banner */}
      {actionMsg && (
        <div className="p-3 rounded-xl bg-sky-950 border border-sky-800 text-[12.5px] text-sky-300 flex items-center justify-between gap-3">
          <span className="flex items-center gap-2"><span className="material-symbols-outlined text-[18px]">info</span>{actionMsg}</span>
          <button onClick={() => setActionMsg(null)} className="text-sky-400 hover:text-sky-200 font-bold cursor-pointer">✕</button>
        </div>
      )}

      {/* Error state */}
      {error && (
        <div className="p-4 rounded-xl bg-rose-950 border border-rose-800 text-rose-200 space-y-2">
          <div className="flex items-center gap-2 font-semibold text-sm">
            <span className="material-symbols-outlined text-rose-400 text-[18px]">error</span>
            <span>Could not load the dashboard figures</span>
          </div>
          <p className="text-xs text-rose-300">
            {error.isNetworkError ? 'The server did not answer. Check that the backend is running.' : error.message}
          </p>
          <button onClick={onRefresh}
            className="px-3 py-1.5 rounded-lg bg-slate-900 border border-rose-700 hover:bg-slate-800 text-rose-300 text-xs font-semibold cursor-pointer">
            Try again
          </button>
        </div>
      )}

      {loading && !stats && (
        <div className="grid gap-4 lg:grid-cols-3 animate-pulse">
          {[0, 1, 2].map(i => <div key={i} className="h-48 rounded-2xl bg-slate-900 border border-slate-800" />)}
        </div>
      )}

      {/* Where the jobs stand beside the size of the search. */}
      <section className="grid grid-cols-1 lg:grid-cols-12 gap-5 items-stretch">
        <div className="lg:col-span-8 rounded-2xl border border-slate-800 bg-slate-900 p-5 flex flex-col gap-4 shadow-sm">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h3 className="text-[15px] font-semibold text-slate-100 flex items-center gap-2">
              <span className="h-8 w-8 rounded-lg bg-sky-950 text-sky-300 flex items-center justify-center"><span className="material-symbols-outlined text-[18px]">donut_large</span></span>
              Where the jobs stand
            </h3>
            <span className="text-[11.5px] text-slate-500">{totalCalculated.toLocaleString('en-IN')} jobs · click a slice to open them</span>
          </div>
          <JobDistributionDonut
            total={totalCalculated}
            heroValue={`${pctCompleted}%`}
            heroLabel="Completed"
            onSliceClick={(key) => onNavigate('jobs', key)}
            slices={[
              { key: 'COMPLETED', label: 'Completed', value: completedJobs, colorVar: '--chart-good' },
              { key: 'PENDING',   label: 'Pending',   value: pendingJobs,   colorVar: '--chart-muted' },
              { key: 'PARTIAL',   label: 'Partial',   value: partialJobs,   colorVar: '--chart-warning' },
              { key: 'FAILED',    label: 'Failed',    value: failedJobs,    colorVar: '--chart-critical' },
              { key: 'BLOCKED',   label: 'Blocked',   value: blockedJobs,   colorVar: '--chart-blocked' },
            ]}
          />
        </div>

        <div className="lg:col-span-4 rounded-2xl border border-slate-800 bg-slate-900 p-5 flex flex-col gap-4 shadow-sm">
          <h3 className="text-[15px] font-semibold text-slate-100 flex items-center gap-2">
            <span className="h-8 w-8 rounded-lg bg-violet-950 text-violet-300 flex items-center justify-center"><span className="material-symbols-outlined text-[18px]">grid_view</span></span>
            Size of the search
          </h3>
          <ScaleBars
            groups={[
              {
                title: 'Search grid',
                bars: [
                  { key: 'categories', label: 'Categories', value: totalCategories, note: 'kinds of shop' },
                  { key: 'locations', label: 'Locations', value: totalLocations, note: 'target PINs' },
                ],
              },
              {
                title: 'Work & output',
                bars: [
                  { key: 'jobs', label: 'Jobs allocated', value: totalJobs,
                    note: `${totalLocations}×${totalCategories}` },
                  { key: 'businesses', label: 'Businesses found', value: totalBusinesses,
                    note: `${validBusinesses.toLocaleString()} valid`,
                    onClick: () => onNavigate('businesses') },
                ],
              },
            ]}
          />
        </div>
      </section>

      <AutopilotPanel />

      {/* The last batch, as tiles. */}
      <section className="rounded-2xl border border-slate-800 bg-slate-900 p-5 shadow-sm">
        <div className="flex flex-wrap items-center justify-between gap-3 mb-4">
          <h3 className="text-[15px] font-semibold text-slate-100 flex items-center gap-2">
            <span className="h-8 w-8 rounded-lg bg-emerald-950 text-emerald-300 flex items-center justify-center"><span className="material-symbols-outlined text-[18px]">alt_route</span></span>
            Last batch
          </h3>
          <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[11.5px] font-semibold ${isDiscoveryRunning ? 'bg-emerald-950 text-emerald-300' : 'bg-slate-800 text-slate-300'}`}>
            <span className={`h-1.5 w-1.5 rounded-full ${isDiscoveryRunning ? 'bg-emerald-400 animate-pulse' : 'bg-slate-500'}`} />
            {isDiscoveryRunning
              ? `Running · ${discoveryStatus?.jobs_processed ?? 0}/${discoveryStatus?.jobs_total ?? 0} jobs`
              : (last?.status ? last.status.charAt(0) + last.status.slice(1).toLowerCase() : 'Nothing run yet')}
          </span>
        </div>
        <div className="grid gap-3 grid-cols-2 lg:grid-cols-4">
          <div className="rounded-xl border border-slate-800 bg-slate-950 p-4">
            <div className="flex items-center gap-1.5 text-[11.5px] text-slate-400"><span className="material-symbols-outlined text-[16px] text-sky-400">schedule</span>Started</div>
            <div className="text-[14px] font-semibold text-slate-100 mt-1.5">{last?.started_at ? formatDateTime(last.started_at) : '—'}</div>
          </div>
          <div className="rounded-xl border border-slate-800 bg-slate-950 p-4">
            <div className="flex items-center gap-1.5 text-[11.5px] text-slate-400"><span className="material-symbols-outlined text-[16px] text-emerald-400">task_alt</span>Jobs done</div>
            <div className="text-2xl font-bold tabular-nums text-slate-100 mt-1">
              {last?.jobs_completed ?? 0}<span className="text-sm font-normal text-slate-500"> / {lastTotal}</span>
              {!!last?.jobs_failed && <span className="ml-2 text-[12px] font-semibold text-rose-400">{last.jobs_failed} failed</span>}
            </div>
            <div className="h-1.5 rounded-full bg-slate-800 mt-2 overflow-hidden flex">
              <div className="h-full bg-emerald-500" style={{ width: `${((last?.jobs_completed ?? 0) / Math.max(1, lastTotal)) * 100}%` }} />
              <div className="h-full bg-rose-500" style={{ width: `${((last?.jobs_failed ?? 0) / Math.max(1, lastTotal)) * 100}%` }} />
            </div>
          </div>
          <div className="rounded-xl border border-slate-800 bg-slate-950 p-4">
            <div className="flex items-center gap-1.5 text-[11.5px] text-slate-400"><span className="material-symbols-outlined text-[16px] text-emerald-400">storefront</span>New businesses</div>
            <div className="text-2xl font-bold tabular-nums text-emerald-400 mt-1">+{last?.businesses_new ?? 0}</div>
            <div className="text-[11.5px] text-slate-500 mt-0.5">{last?.businesses_updated ?? 0} updated · {last?.businesses_duplicate ?? 0} already known</div>
          </div>
          <div className="rounded-xl border border-slate-800 bg-slate-950 p-4">
            <div className="flex items-center gap-1.5 text-[11.5px] text-slate-400"><span className="material-symbols-outlined text-[16px] text-amber-400">mail</span>Emails found</div>
            <div className="text-2xl font-bold tabular-nums text-amber-400 mt-1">{last?.email_enriched ?? 0}</div>
            <div className="text-[11.5px] text-slate-500 mt-0.5">from the businesses' websites</div>
          </div>
        </div>
      </section>

      {/* Side by side: the callbacks are read while the controls are used, and
          stacking them pushed one below the fold on a laptop. */}
      <section className="grid grid-cols-1 lg:grid-cols-2 gap-5 items-start">
        <LeadsPanel />

        <div data-edit className="rounded-2xl border border-slate-800 bg-slate-900 p-5 flex flex-col gap-4 shadow-sm">
          <h3 className="text-[15px] font-semibold text-slate-100 flex items-center gap-2">
            <span className="h-8 w-8 rounded-lg bg-amber-950 text-amber-300 flex items-center justify-center"><span className="material-symbols-outlined text-[18px]">bolt</span></span>
            Quick actions
          </h3>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            {([
              { key: 'run', icon: 'play_circle', tint: 'bg-sky-950 text-sky-300', title: 'Run a batch', sub: '25 waiting jobs, now',
                onClick: handleTriggerPipeline, disabled: actionLoading !== null || isDiscoveryRunning },
              { key: 'targets', icon: 'travel_explore', tint: 'bg-emerald-950 text-emerald-300', title: 'Choose targets', sub: 'Pick places and categories',
                onClick: () => setRunnerOpen(true), disabled: false },
              isDiscoveryRunning
                ? { key: 'stop', icon: 'stop_circle', tint: 'bg-rose-950 text-rose-300', title: 'Stop scraping', sub: 'Finish the current job and stop',
                    onClick: handleStopDiscovery, disabled: actionLoading !== null }
                : { key: 'poll', icon: 'sync', tint: 'bg-amber-950 text-amber-300', title: 'Refresh', sub: 'Fetch the latest figures',
                    onClick: onRefresh, disabled: false },
              { key: 'retry', icon: 'restart_alt', tint: 'bg-violet-950 text-violet-300', title: 'Retry failed jobs', sub: `${failedJobs.toLocaleString('en-IN')} failed`,
                onClick: handleRetryFailed, disabled: actionLoading !== null || failedJobs === 0 },
              { key: 'jobs', icon: 'manage_search', tint: 'bg-slate-800 text-slate-200', title: 'Jobs Monitor', sub: 'Every job and its status',
                onClick: () => onNavigate('jobs'), disabled: false },
            ]).map(a => (
              <button key={a.key} onClick={a.onClick} disabled={a.disabled}
                className="group flex items-center gap-3 text-left rounded-xl border border-slate-800 bg-slate-950 px-3.5 py-3 hover:border-slate-700 hover:-translate-y-0.5 hover:shadow-md transition disabled:opacity-50 disabled:hover:translate-y-0 cursor-pointer disabled:cursor-not-allowed">
                <span className={`h-10 w-10 rounded-xl flex items-center justify-center shrink-0 ${a.tint}`}>
                  <span className="material-symbols-outlined text-[20px]">{a.icon}</span>
                </span>
                <span className="min-w-0 flex-1">
                  <span className="block text-[13px] font-semibold text-slate-100">{a.title}</span>
                  <span className="block text-[11.5px] text-slate-500 truncate">{a.sub}</span>
                </span>
                <span className="material-symbols-outlined text-[18px] text-slate-600 group-hover:text-slate-300 transition">chevron_right</span>
              </button>
            ))}
          </div>
        </div>
      </section>

      <DiscoveryRunner
        isOpen={runnerOpen}
        onClose={() => setRunnerOpen(false)}
        onStarted={onRefresh}
      />
    </div>
  );
};
