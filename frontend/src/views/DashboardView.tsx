import { formatDateTime } from '../utils/datetime';
import React, { useState } from 'react';
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
  const pctPending = ((pendingJobs / totalCalculated) * 100).toFixed(1);
  const pctPartial = ((partialJobs / totalCalculated) * 100).toFixed(1);
  const pctFailed = ((failedJobs / totalCalculated) * 100).toFixed(1);
  const pctBlocked = ((blockedJobs / totalCalculated) * 100).toFixed(1);

  const isDiscoveryRunning = discoveryStatus?.is_running || runningJobs > 0;

  return (
    <div className="flex-1 p-4 lg:p-6 flex flex-col gap-6 overflow-y-auto select-none bg-slate-950 text-slate-100">
      {/* View Title & Subtitle */}
      <section className="flex flex-col md:flex-row md:items-center justify-between gap-4 pb-2 border-b border-slate-800">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-2xl font-semibold text-slate-100 tracking-tight">Dashboard</h1>
            <span className="px-2 py-0.5 rounded text-[10px] font-mono-code bg-sky-950/80 border border-sky-800 text-sky-400 font-bold uppercase">
              v2.0 Orchestrator
            </span>
          </div>
          <p className="text-xs text-slate-400 mt-0.5">Overview of autonomous Google Maps discovery operations</p>
        </div>

        {/* Action / Endpoint Indicator */}
        <div className="flex items-center gap-2">
          <button
            onClick={onRefresh}
            disabled={loading}
            className="h-8 px-3 rounded bg-slate-900 border border-slate-700 hover:bg-slate-800 text-slate-200 text-xs font-mono-code font-medium flex items-center gap-2 active:scale-95 transition-all shadow-sm disabled:opacity-50 cursor-pointer"
          >
            <span className={`material-symbols-outlined text-[15px] text-sky-400 ${loading ? 'animate-spin' : ''}`}>
              refresh
            </span>
            <span>Refresh Data</span>
          </button>
          <div className="px-2.5 h-8 flex items-center gap-1.5 bg-slate-900 border border-slate-800 rounded text-xs font-mono-code text-slate-400 shadow-sm">
            <span className="material-symbols-outlined text-[14px] text-emerald-400">cloud_done</span>
            <span>
              Endpoint: <strong className="text-slate-200 font-semibold">GET /api/v1/stats</strong>
            </span>
          </div>
        </div>
      </section>

      {/* Action feedback banner */}
      {actionMsg && (
        <div className="p-3 bg-sky-950/80 border border-sky-800 rounded text-xs font-mono-code text-sky-300 flex items-center justify-between">
          <span>{actionMsg}</span>
          <button onClick={() => setActionMsg(null)} className="text-sky-400 hover:text-sky-200 font-bold cursor-pointer">✕</button>
        </div>
      )}

      {/* Error state */}
      {error && (
        <div className="p-4 bg-rose-950/70 border border-rose-800 rounded text-rose-200 space-y-2">
          <div className="flex items-center gap-2 font-semibold text-sm">
            <span className="material-symbols-outlined text-rose-400 text-[18px]">error</span>
            <span>Unable to load dashboard statistics from backend</span>
          </div>
          <p className="text-xs font-mono-code text-rose-300">
            {error.isNetworkError
              ? `Connection to FastAPI failed at ${error.endpoint || '/api/v1/stats'}. Ensure backend server is running.`
              : error.message}
          </p>
          <div className="flex gap-2 pt-1">
            <button
              onClick={onRefresh}
              className="px-3 py-1 bg-slate-900 border border-rose-700 hover:bg-slate-800 text-rose-300 text-xs font-mono-code rounded font-medium transition-colors cursor-pointer"
            >
              Retry Request
            </button>
          </div>
        </div>
      )}

      {/* Loading Skeleton */}
      {loading && !stats && (
        <div className="p-12 bg-slate-900 border border-slate-800 rounded text-center space-y-3">
          <div className="inline-block w-8 h-8 border-3 border-sky-400 border-t-transparent rounded-full animate-spin" />
          <div className="text-sm font-mono-code text-slate-300 font-medium">Fetching real backend statistics...</div>
          <div className="text-xs font-mono-code text-slate-500">Querying GET /api/v1/stats</div>
        </div>
      )}

      {/* KPI Metric Tiles Grid (4 Bento Cards) */}
      <section className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-4">
        {/* 1. Locations */}
        <div className="bg-slate-900 border border-slate-800 p-4 rounded flex flex-col justify-between relative overflow-hidden group hover:border-sky-500/50 transition-colors duration-150 shadow-sm">
          <div className="flex items-center justify-between">
            <span className="text-[10px] font-mono-code text-slate-400 uppercase tracking-wider font-semibold">
              Locations
            </span>
            <span className="material-symbols-outlined text-slate-500 text-[18px]">pin_drop</span>
          </div>
          <div className="mt-2 flex items-baseline justify-between">
            <div className="text-2xl font-mono-code text-slate-100 font-bold">
              {totalLocations.toLocaleString()}
            </div>
            <div className="text-xs font-mono-code text-emerald-400 bg-emerald-950/60 px-1.5 py-0.5 rounded border border-emerald-800/80 flex items-center gap-0.5 font-semibold">
              <span className="material-symbols-outlined text-[13px]">pin_drop</span>
              <span>Source</span>
            </div>
          </div>
          <div className="mt-1 text-xs font-mono-code text-slate-400 truncate">
            Configured target PINs
          </div>
        </div>

        {/* 2. Categories */}
        <div className="bg-slate-900 border border-slate-800 p-4 rounded flex flex-col justify-between relative overflow-hidden group hover:border-sky-500/50 transition-colors duration-150 shadow-sm">
          <div className="flex items-center justify-between">
            <span className="text-[10px] font-mono-code text-slate-400 uppercase tracking-wider font-semibold">
              Categories
            </span>
            <span className="material-symbols-outlined text-slate-500 text-[18px]">category</span>
          </div>
          <div className="mt-2 flex items-baseline justify-between">
            <div className="text-2xl font-mono-code text-slate-100 font-bold">
              {totalCategories.toLocaleString()}
            </div>
            <div className="text-xs font-mono-code text-slate-300 bg-slate-800 px-1.5 py-0.5 rounded border border-slate-700 font-medium">
              Personas
            </div>
          </div>
          <div className="mt-1 text-xs font-mono-code text-slate-400 truncate">
            Persona search categories
          </div>
        </div>

        {/* 3. Total Jobs Matrix */}
        <div className="bg-slate-900 border border-slate-800 p-4 rounded flex flex-col justify-between relative overflow-hidden group hover:border-sky-500/50 transition-colors duration-150 shadow-sm">
          <div className="flex items-center justify-between">
            <span className="text-[10px] font-mono-code text-slate-400 uppercase tracking-wider font-semibold">
              Total Jobs
            </span>
            <span className="material-symbols-outlined text-sky-400 text-[18px]">hub</span>
          </div>
          <div className="mt-2 flex items-baseline justify-between">
            <div className="text-2xl font-mono-code text-slate-100 font-bold">
              {totalJobs.toLocaleString()}
            </div>
            <div className="text-xs font-mono-code text-sky-400 bg-sky-950/60 px-1.5 py-0.5 rounded border border-sky-800/80 flex items-center gap-0.5 font-semibold">
              <span>MATRIX</span>
            </div>
          </div>
          <div className="mt-1 text-xs font-mono-code text-slate-400 truncate">
            {totalLocations} Loc × {totalCategories} Cat matrix
          </div>
        </div>

        {/* 4. Businesses Discovered */}
        <div className="bg-slate-900 border border-slate-800 p-4 rounded flex flex-col justify-between relative overflow-hidden group hover:border-emerald-500/50 transition-colors duration-150 shadow-sm">
          <div className="flex items-center justify-between">
            <span className="text-[10px] font-mono-code text-slate-400 uppercase tracking-wider font-semibold">
              Businesses Discovered
            </span>
            <span className="material-symbols-outlined text-emerald-400 text-[18px]">corporate_fare</span>
          </div>
          <div className="mt-2 flex items-baseline justify-between">
            <div className="text-2xl font-mono-code text-emerald-400 font-bold">
              {totalBusinesses.toLocaleString()}
            </div>
            <div className="text-xs font-mono-code text-emerald-400 bg-emerald-950/60 px-1.5 py-0.5 rounded border border-emerald-800/80 flex items-center gap-0.5 font-semibold">
              <span className="material-symbols-outlined text-[13px]">database</span>
              <span>{validBusinesses.toLocaleString()} Valid</span>
            </div>
          </div>
          <div className="mt-1 text-xs font-mono-code text-slate-400 truncate">
            Normalized & deduplicated in SQLite
          </div>
        </div>
      </section>

      {/* Operational Status Breakdown (6 States) */}
      <section className="flex flex-col gap-2">
        <div className="flex items-center justify-between">
          <h2 className="text-sm text-slate-200 uppercase tracking-wider flex items-center gap-2 font-bold font-mono-code">
            <span className="w-2 h-2 rounded-full bg-sky-400" />
            Operational Status Breakdown
          </h2>
          <span className="text-xs font-mono-code text-slate-400 font-medium">
            Total: {totalCalculated.toLocaleString()} allocated jobs
          </span>
        </div>

        <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-6 gap-3">
          {/* PENDING */}
          <div className="bg-slate-900 border border-slate-800 p-3 rounded flex flex-col justify-between hover:border-slate-700 transition-colors shadow-sm">
            <div className="flex items-center justify-between mb-1">
              <span className="text-[10px] font-mono-code text-slate-400 font-bold uppercase">PENDING</span>
              <span className="px-1.5 py-0.5 rounded text-[9px] font-mono-code border border-slate-700 bg-slate-800 text-slate-300 font-semibold">
                QUEUED
              </span>
            </div>
            <div className="text-xl font-mono-code text-slate-100 font-bold">{pendingJobs.toLocaleString()}</div>
            <div className="text-[11px] font-mono-code text-slate-400 mt-1">{pctPending}% of total</div>
          </div>

          {/* RUNNING */}
          <div className="bg-sky-950/40 border border-sky-800 p-3 rounded flex flex-col justify-between relative shadow-sm">
            <div className="flex items-center justify-between mb-1">
              <span className="text-[10px] font-mono-code text-sky-400 font-bold uppercase">RUNNING</span>
              <span className="flex items-center gap-1 px-1.5 py-0.5 rounded text-[9px] font-mono-code border border-sky-800 bg-sky-950 text-sky-300 font-semibold">
                <span className="w-1.5 h-1.5 rounded-full bg-sky-400 pulse-glow" />
                ACTIVE
              </span>
            </div>
            <div className="text-xl font-mono-code text-sky-300 font-bold">{runningJobs.toLocaleString()}</div>
            <div className="text-[11px] font-mono-code text-sky-400 mt-1">Playwright active</div>
          </div>

          {/* COMPLETED */}
          <div className="bg-slate-900 border border-slate-800 p-3 rounded flex flex-col justify-between hover:border-emerald-800 transition-colors shadow-sm">
            <div className="flex items-center justify-between mb-1">
              <span className="text-[10px] font-mono-code text-emerald-400 font-bold uppercase">COMPLETED</span>
              <span className="px-1.5 py-0.5 rounded text-[9px] font-mono-code border border-emerald-800 bg-emerald-950/60 text-emerald-300 font-semibold">
                DONE
              </span>
            </div>
            <div className="text-xl font-mono-code text-slate-100 font-bold">{completedJobs.toLocaleString()}</div>
            <div className="text-[11px] font-mono-code text-emerald-400 font-medium mt-1">{pctCompleted}% finished</div>
          </div>

          {/* PARTIAL */}
          <div className="bg-slate-900 border border-slate-800 p-3 rounded flex flex-col justify-between hover:border-amber-800 transition-colors shadow-sm">
            <div className="flex items-center justify-between mb-1">
              <span className="text-[10px] font-mono-code text-amber-400 font-bold uppercase">PARTIAL</span>
              <span className="px-1.5 py-0.5 rounded text-[9px] font-mono-code border border-amber-800 bg-amber-950/60 text-amber-300 font-semibold">
                CAPPED
              </span>
            </div>
            <div className="text-xl font-mono-code text-slate-100 font-bold">{partialJobs.toLocaleString()}</div>
            <div className="text-[11px] font-mono-code text-amber-400 font-medium mt-1">{pctPartial}% limit hit</div>
          </div>

          {/* FAILED */}
          <div className="bg-slate-900 border border-rose-900/60 p-3 rounded flex flex-col justify-between shadow-sm">
            <div className="flex items-center justify-between mb-1">
              <span className="text-[10px] font-mono-code text-rose-400 font-bold uppercase">FAILED</span>
              <button
                onClick={() => onNavigate('jobs', 'FAILED')}
                className="px-1.5 py-0.5 rounded text-[9px] font-mono-code border border-rose-800 bg-rose-950/80 text-rose-300 hover:bg-rose-900 hover:text-slate-100 transition-all uppercase font-semibold cursor-pointer"
              >
                Inspect
              </button>
            </div>
            <div className="text-xl font-mono-code text-rose-400 font-bold">{failedJobs.toLocaleString()}</div>
            <div className="text-[11px] font-mono-code text-rose-400 mt-1">{pctFailed}% timeout/err</div>
          </div>

          {/* BLOCKED */}
          <div className="bg-slate-900 border border-slate-800 p-3 rounded flex flex-col justify-between hover:border-purple-800 transition-colors shadow-sm">
            <div className="flex items-center justify-between mb-1">
              <span className="text-[10px] font-mono-code text-purple-400 font-bold uppercase">BLOCKED</span>
              <span className="px-1.5 py-0.5 rounded text-[9px] font-mono-code border border-purple-800 bg-purple-950/60 text-purple-300 font-semibold">
                RATE LIMIT
              </span>
            </div>
            <div className="text-xl font-mono-code text-slate-100 font-bold">{blockedJobs.toLocaleString()}</div>
            <div className="text-[11px] font-mono-code text-purple-400 font-medium mt-1">{pctBlocked}% throttled</div>
          </div>
        </div>
      </section>

      {/* Segmented Stacked Progress Track */}
      <section className="bg-slate-900 border border-slate-800 p-4 rounded flex flex-col gap-3 shadow-sm">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <span className="material-symbols-outlined text-sky-400 text-[18px]">bar_chart</span>
            <h3 className="text-sm font-semibold text-slate-100">Job Distribution Across Matrix</h3>
          </div>
          <span className="text-xs font-mono-code text-slate-400 font-medium">
            {totalCalculated.toLocaleString()} Total Jobs ({pctCompleted}% Completed)
          </span>
        </div>

        <div className="w-full h-3 bg-slate-950 rounded-sm overflow-hidden flex gap-0.5 p-0.5 border border-slate-800">
          <div
            className="h-full bg-emerald-500 rounded-xs transition-all duration-500"
            style={{ width: `${Math.max(0, Number(pctCompleted))}%` }}
            title={`Completed: ${pctCompleted}%`}
          />
          <div
            className="h-full bg-slate-600 rounded-xs transition-all duration-500"
            style={{ width: `${Math.max(0, Number(pctPending))}%` }}
            title={`Pending: ${pctPending}%`}
          />
          <div
            className="h-full bg-amber-500 rounded-xs transition-all duration-500"
            style={{ width: `${Math.max(0, Number(pctPartial))}%` }}
            title={`Partial: ${pctPartial}%`}
          />
          <div
            className="h-full bg-rose-500 rounded-xs transition-all duration-500"
            style={{ width: `${Math.max(0, Number(pctFailed))}%` }}
            title={`Failed: ${pctFailed}%`}
          />
          <div
            className="h-full bg-purple-500 rounded-xs transition-all duration-500"
            style={{ width: `${Math.max(0, Number(pctBlocked))}%` }}
            title={`Blocked: ${pctBlocked}%`}
          />
        </div>

        <div className="flex flex-wrap items-center justify-between gap-y-2 gap-x-4 pt-1 text-xs font-mono-code">
          <div className="flex items-center gap-2">
            <span className="w-2.5 h-2.5 rounded bg-emerald-500" />
            <span className="text-slate-200 font-medium">Completed:</span>
            <span className="text-slate-400 font-semibold">{completedJobs.toLocaleString()} ({pctCompleted}%)</span>
          </div>
          <div className="flex items-center gap-2">
            <span className="w-2.5 h-2.5 rounded bg-slate-500" />
            <span className="text-slate-200 font-medium">Pending:</span>
            <span className="text-slate-400 font-semibold">{pendingJobs.toLocaleString()} ({pctPending}%)</span>
          </div>
          <div className="flex items-center gap-2">
            <span className="w-2.5 h-2.5 rounded bg-amber-500" />
            <span className="text-slate-200 font-medium">Partial:</span>
            <span className="text-slate-400 font-semibold">{partialJobs.toLocaleString()} ({pctPartial}%)</span>
          </div>
          <div className="flex items-center gap-2">
            <span className="w-2.5 h-2.5 rounded bg-rose-500" />
            <span className="text-slate-200 font-medium">Failed:</span>
            <span className="text-slate-400 font-semibold">{failedJobs.toLocaleString()} ({pctFailed}%)</span>
          </div>
          <div className="flex items-center gap-2">
            <span className="w-2.5 h-2.5 rounded bg-purple-500" />
            <span className="text-slate-200 font-medium">Blocked:</span>
            <span className="text-slate-400 font-semibold">{blockedJobs.toLocaleString()} ({pctBlocked}%)</span>
          </div>
        </div>
      </section>

      {/* Split Layout: Latest Run Card (Left) & Operational Actions (Right) */}
      <section className="grid grid-cols-1 lg:grid-cols-12 gap-4 items-start">
        {/* Left: Latest Orchestration Run Card */}
        <div className="lg:col-span-7 bg-slate-900 border border-slate-800 p-4 rounded flex flex-col gap-4 shadow-sm">
          <div className="flex items-center justify-between pb-3 border-b border-slate-800">
            <div className="flex items-center gap-2">
              <span className="material-symbols-outlined text-emerald-400 text-[20px]">alt_route</span>
              <h3 className="text-sm font-semibold text-slate-100">Latest Orchestration Run</h3>
            </div>
            <div className="flex items-center gap-2">
              <span className="px-2 py-0.5 rounded text-xs font-mono-code border border-emerald-800 bg-emerald-950/60 text-emerald-300 font-semibold">
                {isDiscoveryRunning ? 'RUNNING' : (stats?.last_run?.status || 'IDLE')}
              </span>
              <span className="text-xs font-mono-code text-slate-400 font-medium">
                {stats?.last_run?.run_id ? `Run #${stats.last_run.run_id.slice(0, 8)}` : 'Engine Ready'}
              </span>
            </div>
          </div>

          {/* Real Run Metadata Bento */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs">
            <div className="p-3 bg-slate-950 rounded border border-slate-800">
              <div className="text-[10px] font-mono-code text-slate-400 uppercase flex items-center gap-1.5 font-semibold">
                <span className="material-symbols-outlined text-[14px]">schedule</span>
                Started At
              </div>
              <div className="font-mono-code text-slate-200 mt-1 font-semibold truncate">
                {stats?.last_run?.started_at ? formatDateTime(stats.last_run.started_at) : 'Ready on standby'}
              </div>
            </div>

            <div className="p-3 bg-slate-950 rounded border border-slate-800">
              <div className="text-[10px] font-mono-code text-slate-400 uppercase flex items-center gap-1.5 font-semibold">
                <span className="material-symbols-outlined text-[14px]">task_alt</span>
                Jobs Status (Last Run)
              </div>
              <div className="font-mono-code text-slate-200 mt-1 font-semibold flex items-center gap-2">
                <span className="text-emerald-400" title="Completed">{stats?.last_run?.jobs_completed ?? 0}</span> /
                <span className="text-rose-400" title="Failed">{stats?.last_run?.jobs_failed ?? 0}</span> /
                <span className="text-slate-300" title="Total">{stats?.last_run?.jobs_total ?? 0}</span>
              </div>
            </div>

            <div className="p-3 bg-slate-950 rounded border border-slate-800">
              <div className="text-[10px] font-mono-code text-slate-400 uppercase flex items-center gap-1.5 font-semibold">
                <span className="material-symbols-outlined text-[14px] text-emerald-400">domain_add</span>
                Business Extraction
              </div>
              <div className="font-mono-code mt-1 font-semibold flex gap-2">
                <span className="text-emerald-400" title="New">{stats?.last_run?.businesses_new ?? 0}</span>
                <span className="text-sky-400" title="Updated">{stats?.last_run?.businesses_updated ?? 0}</span>
                <span className="text-slate-400" title="Duplicate">{stats?.last_run?.businesses_duplicate ?? 0}</span>
              </div>
            </div>

            <div className="p-3 bg-slate-950 rounded border border-slate-800">
              <div className="text-[10px] font-mono-code text-slate-400 uppercase flex items-center gap-1.5 font-semibold">
                <span className="material-symbols-outlined text-[14px] text-amber-400">mail</span>
                Emails Found
              </div>
              <div className="font-mono-code text-amber-400 mt-1 font-semibold">
                {stats?.last_run?.email_enriched ?? 0}
              </div>
            </div>

            <div className="p-3 bg-slate-950 rounded border border-slate-800">
              <div className="text-[10px] font-mono-code text-slate-400 uppercase flex items-center gap-1.5 font-semibold">
                <span className="material-symbols-outlined text-[14px] text-sky-400">account_tree</span>
                Batch Status
              </div>
              <div className="font-mono-code text-slate-200 mt-1 font-semibold truncate">
                {isDiscoveryRunning ? `Active (${discoveryStatus?.jobs_processed ?? 0}/${discoveryStatus?.jobs_total ?? 0} jobs)` : 'Standing by for trigger'}
              </div>
            </div>
          </div>

          {/* Engine Execution Details */}
          <div className="bg-slate-950 text-slate-200 rounded p-3 font-mono-code text-xs flex flex-col gap-1 border border-slate-800">
            <div className="flex items-center justify-between pb-1 border-b border-slate-800 text-[10px] uppercase text-slate-400">
              <span>Engine Status [FastAPI + Playwright]</span>
              <span className={isDiscoveryRunning ? 'text-sky-400 font-semibold' : 'text-emerald-400 font-semibold'}>
                {isDiscoveryRunning ? 'BATCH RUNNING' : 'ONLINE'}
              </span>
            </div>
            <div className="flex items-center gap-2 pt-1 text-[11px]">
              <span className="text-slate-500">DISCOVERY</span>
              <span className="text-sky-400 font-semibold">[PLAYWRIGHT]</span>
              <span className="text-slate-300">
                {isDiscoveryRunning
                  ? `Processing job #${discoveryStatus?.current_job_id ?? 'active'} (${discoveryStatus?.jobs_processed} / ${discoveryStatus?.jobs_total})`
                  : `Total ${completedJobs.toLocaleString()} jobs completed. ${totalBusinesses.toLocaleString()} businesses persisted.`}
              </span>
            </div>
            <div className="flex items-center gap-2 text-[11px]">
              <span className="text-slate-500">DEDUPE</span>
              <span className="text-emerald-400 font-semibold">[SQLITE]</span>
              <span className="text-slate-300">Deterministic deduplication active: name + pincode + coordinates.</span>
            </div>
          </div>
        </div>

        {/* Right: Operational Actions & Engine Health */}
        <div className="lg:col-span-5 flex flex-col gap-4">
          {/* Engine Health Matrix */}
          <div className="bg-slate-900 border border-slate-800 p-4 rounded flex flex-col gap-3 shadow-sm">
            <div className="flex items-center justify-between pb-2 border-b border-slate-800">
              <div className="flex items-center gap-2">
                <span className="material-symbols-outlined text-sky-400 text-[18px]">memory</span>
                <h3 className="text-sm font-semibold text-slate-100">Engine Architecture</h3>
              </div>
              <span className="text-[10px] font-mono-code text-emerald-400 font-bold uppercase bg-emerald-950/60 px-1.5 py-0.5 rounded border border-emerald-800">
                HEALTHY
              </span>
            </div>

            <div className="flex flex-col gap-2 text-xs font-mono-code">
              <div className="flex items-center justify-between p-2 bg-slate-950 rounded border border-slate-800">
                <div className="flex items-center gap-2">
                  <span className="w-1.5 h-1.5 rounded-full bg-emerald-400" />
                  <span className="text-slate-300 font-medium">Discovery Engine:</span>
                </div>
                <span className="text-sky-400 font-semibold">
                  {isDiscoveryRunning ? 'Active Batch' : 'Idle / Ready'}
                </span>
              </div>

              <div className="flex items-center justify-between p-2 bg-slate-950 rounded border border-slate-800">
                <div className="flex items-center gap-2">
                  <span className="w-1.5 h-1.5 rounded-full bg-emerald-400" />
                  <span className="text-slate-300 font-medium">Deduplication:</span>
                </div>
                <span className="text-emerald-400 font-semibold">Active (Authoritative)</span>
              </div>

              <div className="flex items-center justify-between p-2 bg-slate-950 rounded border border-slate-800">
                <div className="flex items-center gap-2">
                  <span className="w-1.5 h-1.5 rounded-full bg-emerald-400" />
                  <span className="text-slate-300 font-medium">CSV Streaming:</span>
                </div>
                <span className="text-emerald-400 font-semibold">GET /export/businesses</span>
              </div>
            </div>
          </div>

          {/* Quick Real Operational Actions */}
          <div className="bg-slate-900 border border-slate-800 p-4 rounded flex flex-col gap-3 shadow-sm">
            <div className="flex items-center justify-between pb-2 border-b border-slate-800">
              <div className="flex items-center gap-2">
                <span className="material-symbols-outlined text-slate-400 text-[18px]">bolt</span>
                <h3 className="text-sm font-semibold text-slate-100">Operational Controls</h3>
              </div>
              <span className="text-xs font-mono-code text-slate-400 font-medium">Direct API</span>
            </div>
            <div className="grid grid-cols-2 gap-2 text-xs font-mono-code">
              <button
                onClick={handleTriggerPipeline}
                disabled={actionLoading !== null || isDiscoveryRunning}
                className="h-9 px-3 bg-slate-800 hover:bg-slate-700 border border-slate-700 hover:border-sky-500 text-slate-100 rounded font-medium flex items-center justify-center gap-2 transition-all shadow-sm disabled:opacity-50 cursor-pointer"
                title="Run batch of 25 pending discovery jobs"
              >
                <span className="material-symbols-outlined text-[16px] text-sky-400">play_circle</span>
                <span>Run Batch (25)</span>
              </button>

              {isDiscoveryRunning ? (
                <button
                  onClick={handleStopDiscovery}
                  disabled={actionLoading !== null}
                  className="h-9 px-3 bg-rose-950/70 hover:bg-rose-900/80 border border-rose-800 text-rose-300 rounded font-medium flex items-center justify-center gap-2 transition-all shadow-sm cursor-pointer"
                  title="Gracefully stop active batch"
                >
                  <span className="material-symbols-outlined text-[16px] text-rose-400">stop_circle</span>
                  <span>Stop Discovery</span>
                </button>
              ) : (
                <button
                  onClick={onRefresh}
                  className="h-9 px-3 bg-slate-800 hover:bg-slate-700 border border-slate-700 hover:border-amber-500 text-slate-200 rounded font-medium flex items-center justify-center gap-2 transition-all shadow-sm cursor-pointer"
                  title="Poll latest discovery status"
                >
                  <span className="material-symbols-outlined text-[16px] text-amber-400">sync</span>
                  <span>Poll Status</span>
                </button>
              )}

              <button
                onClick={handleRetryFailed}
                disabled={actionLoading !== null || failedJobs === 0}
                className="h-9 px-3 bg-slate-800 hover:bg-slate-700 border border-slate-700 hover:border-sky-500 text-slate-200 rounded font-medium flex items-center justify-center gap-2 transition-all shadow-sm disabled:opacity-50 cursor-pointer"
                title="Reset all FAILED jobs to PENDING"
              >
                <span className="material-symbols-outlined text-[16px] text-sky-400">restart_alt</span>
                <span>Re-queue Failed</span>
              </button>

              <button
                onClick={() => onNavigate('jobs')}
                className="h-9 px-3 bg-sky-950/40 hover:bg-sky-950/70 border border-sky-800 text-sky-300 rounded font-semibold flex items-center justify-center gap-2 transition-all shadow-sm cursor-pointer"
              >
                <span className="material-symbols-outlined text-[16px]">manage_search</span>
                <span>Jobs Monitor</span>
              </button>
            </div>
          </div>
        </div>
      </section>
    </div>
  );
};
