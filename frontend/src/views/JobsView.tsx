import React, { useState, useEffect } from 'react';
import type { JobItem, PaginatedResponse, NormalizedSystemStats, ApiError } from '../types/api';
import { fetchJobs, retryJob, runJob, retryAllFailedJobs } from '../api';
import { formatDateTime, localTimeZone } from '../utils/datetime';
import { StatusBadge } from '../components/StatusBadge';

interface JobsViewProps {
  stats: NormalizedSystemStats | null;
  initialFilter?: string;
  onRefreshStats?: () => void;
}

export const JobsView: React.FC<JobsViewProps> = ({
  stats,
  initialFilter = 'All',
  onRefreshStats,
}) => {
  const [jobs, setJobs] = useState<JobItem[]>([]);
  const [total, setTotal] = useState<number>(0);
  const [page, setPage] = useState<number>(1);
  const [pageSize] = useState<number>(100);
  const [totalPages, setTotalPages] = useState<number>(1);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<ApiError | null>(null);

  // Filters & Selected Job
  const [statusFilter, setStatusFilter] = useState<string>(initialFilter);
  const [selectedJob, setSelectedJob] = useState<JobItem | null>(null);
  const [actionProcessingId, setActionProcessingId] = useState<string | null>(null);
  const [actionFeedback, setActionFeedback] = useState<string | null>(null);
  const [retryingAll, setRetryingAll] = useState<boolean>(false);
  const [jumpPage, setJumpPage] = useState<string>('');

  const loadJobs = async (targetPage = page, status = statusFilter) => {
    setLoading(true);
    setError(null);
    try {
      const res: PaginatedResponse<JobItem> = await fetchJobs({
        page: targetPage,
        page_size: pageSize,
        status: status !== 'All' ? status : undefined,
      });
      setJobs(res.items);
      setTotal(res.total);
      setPage(res.page);
      setTotalPages(res.total_pages || Math.max(1, Math.ceil(res.total / pageSize)));

      if (res.items.length > 0 && !selectedJob) {
        setSelectedJob(res.items[0]);
      }
    } catch (err: any) {
      setError(err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadJobs(1, statusFilter);
  }, [statusFilter]);

  const handleRetrySingle = async (jobId: string) => {
    setActionProcessingId(jobId);
    setActionFeedback(null);
    try {
      const res = await retryJob(jobId);
      setActionFeedback(`Job #${jobId.slice(0, 8)}: ${res.message || 'Queued for retry'}`);
      loadJobs(page, statusFilter);
      if (onRefreshStats) onRefreshStats();
    } catch (e: any) {
      setActionFeedback(`Failed to retry #${jobId.slice(0, 8)}: ${e.message}`);
    } finally {
      setActionProcessingId(null);
    }
  };

  const handleRunSingle = async (jobId: string) => {
    setActionProcessingId(jobId);
    setActionFeedback(null);
    try {
      const res = await runJob(jobId);
      setActionFeedback(`Job #${jobId.slice(0, 8)}: ${res.message || 'Execution finished'}`);
      loadJobs(page, statusFilter);
      if (onRefreshStats) onRefreshStats();
    } catch (e: any) {
      setActionFeedback(`Failed to run #${jobId.slice(0, 8)}: ${e.message}`);
    } finally {
      setActionProcessingId(null);
    }
  };

  const handleRetryAllFailed = async () => {
    setRetryingAll(true);
    setActionFeedback(null);
    try {
      const res = await retryAllFailedJobs('FAILED');
      setActionFeedback(res.message || `Re-queued ${res.jobs_retried} failed jobs`);
      loadJobs(page, statusFilter);
      if (onRefreshStats) onRefreshStats();
    } catch (e: any) {
      setActionFeedback(`Retry failed: ${e.message}`);
    } finally {
      setRetryingAll(false);
    }
  };

  const handlePageChange = (newPage: number) => {
    if (newPage >= 1 && newPage <= totalPages && newPage !== page) {
      setPage(newPage);
      loadJobs(newPage, statusFilter);
    }
  };

  const handleJump = () => {
    const num = parseInt(jumpPage, 10);
    if (!isNaN(num) && num >= 1 && num <= totalPages) {
      handlePageChange(num);
      setJumpPage('');
    }
  };

  const startRecord = total > 0 ? (page - 1) * pageSize + 1 : 0;
  const endRecord = total > 0 ? Math.min(page * pageSize, total) : 0;

  // Accurate counts from normalized system stats
  const totalScrapes = stats?.total_jobs ?? total;
  const runningNodes = stats?.running_jobs ?? 0;
  const completedNominal = stats?.completed_jobs ?? 0;
  const partialBatches = stats?.partial_jobs ?? 0;
  const failedJobsCount = stats?.failed_jobs ?? 0;
  const rateBlocked = stats?.blocked_jobs ?? 0;

  return (
    <div className="flex-1 flex flex-col min-w-0 h-full bg-slate-950 text-slate-100 select-none overflow-hidden">
      {/* Content Header & Top Summary */}
      <div className="px-6 py-4 border-b border-slate-800 bg-slate-900 flex flex-col gap-4 shrink-0">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div>
            <div className="flex items-center gap-3">
              <h1 className="text-2xl font-semibold text-slate-100 tracking-tight">Jobs Monitor</h1>
              <span className="px-2 py-0.5 bg-sky-950/80 border border-sky-800 text-sky-400 font-mono-code text-xs rounded flex items-center gap-1.5 font-medium">
                <span className="h-1.5 w-1.5 rounded-full bg-sky-400 pulse-glow" />
                FastAPI Orchestration Queue
              </span>
            </div>
            <p className="text-xs text-slate-400 mt-0.5">
              Live status, execution results, and retry management for Playwright discovery jobs
            </p>
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={() => loadJobs(page)}
              disabled={loading}
              className="h-8 px-3 bg-slate-800 hover:bg-slate-700 border border-slate-700 text-slate-200 text-xs font-mono-code rounded flex items-center gap-1.5 transition-all shadow-sm cursor-pointer active:scale-95 disabled:opacity-50"
            >
              <span className={`material-symbols-outlined text-[16px] text-slate-400 ${loading ? 'animate-spin' : ''}`}>
                refresh
              </span>
              <span>Refresh</span>
            </button>

            <button
              onClick={handleRetryAllFailed}
              disabled={retryingAll || failedJobsCount === 0}
              className="h-8 px-3.5 bg-sky-600 hover:bg-sky-500 text-white font-mono-code text-xs font-semibold rounded flex items-center gap-1.5 transition-all shadow-sm cursor-pointer active:scale-95 disabled:opacity-50"
              title="Reset all eligible FAILED jobs to PENDING"
            >
              <span className="material-symbols-outlined text-[16px]">
                {retryingAll ? 'sync' : 'restart_alt'}
              </span>
              <span>
                {retryingAll ? 'Retrying...' : `Retry Failed Jobs (${failedJobsCount})`}
              </span>
            </button>
          </div>
        </div>

        {/* Action feedback notification */}
        {actionFeedback && (
          <div className="p-2 bg-sky-950/80 border border-sky-800 rounded text-xs font-mono-code text-sky-300 flex items-center justify-between">
            <span>{actionFeedback}</span>
            <button onClick={() => setActionFeedback(null)} className="text-sky-400 hover:text-sky-200 font-bold cursor-pointer">
              ✕
            </button>
          </div>
        )}

        {/* 6 Metric KPI Tiles */}
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
          <div className="p-2.5 bg-slate-950 border border-slate-800 rounded flex flex-col justify-between">
            <span className="text-[10px] font-mono-code text-slate-400 uppercase font-semibold">Total Jobs</span>
            <span className="text-lg font-mono-code text-slate-100 font-bold mt-1">{totalScrapes.toLocaleString()}</span>
          </div>
          <div className="p-2.5 bg-sky-950/40 border border-sky-800 rounded flex flex-col justify-between">
            <span className="text-[10px] font-mono-code text-sky-400 uppercase font-semibold flex items-center gap-1">
              <span className="w-1.5 h-1.5 rounded-full bg-sky-400 pulse-glow" />
              Running
            </span>
            <span className="text-lg font-mono-code text-sky-200 font-bold mt-1">{runningNodes.toLocaleString()}</span>
          </div>
          <div className="p-2.5 bg-emerald-950/40 border border-emerald-800 rounded flex flex-col justify-between">
            <span className="text-[10px] font-mono-code text-emerald-400 uppercase font-semibold">Completed</span>
            <span className="text-lg font-mono-code text-emerald-200 font-bold mt-1">{completedNominal.toLocaleString()}</span>
          </div>
          <div className="p-2.5 bg-amber-950/40 border border-amber-800 rounded flex flex-col justify-between">
            <span className="text-[10px] font-mono-code text-amber-400 uppercase font-semibold">Partial</span>
            <span className="text-lg font-mono-code text-amber-200 font-bold mt-1">{partialBatches.toLocaleString()}</span>
          </div>
          <div className="p-2.5 bg-rose-950/40 border border-rose-800 rounded flex flex-col justify-between">
            <span className="text-[10px] font-mono-code text-rose-400 uppercase font-semibold">Failed</span>
            <span className="text-lg font-mono-code text-rose-200 font-bold mt-1">{failedJobsCount.toLocaleString()}</span>
          </div>
          <div className="p-2.5 bg-purple-950/40 border border-purple-800 rounded flex flex-col justify-between">
            <span className="text-[10px] font-mono-code text-purple-400 uppercase font-semibold">Blocked</span>
            <span className="text-lg font-mono-code text-purple-200 font-bold mt-1">{rateBlocked.toLocaleString()}</span>
          </div>
        </div>

        {/* Status Filter Tabs */}
        <div className="flex items-center gap-1 overflow-x-auto pb-1 lg:pb-0">
          {[
            { id: 'All', label: 'All Jobs' },
            { id: 'PENDING', label: 'Pending' },
            { id: 'RUNNING', label: 'Running' },
            { id: 'COMPLETED', label: 'Completed' },
            { id: 'PARTIAL', label: 'Partial' },
            { id: 'FAILED', label: 'Failed' },
            { id: 'BLOCKED', label: 'Blocked' },
          ].map((tab) => {
            const active = statusFilter === tab.id;
            return (
              <button
                key={tab.id}
                onClick={() => setStatusFilter(tab.id)}
                className={`px-3 py-1 text-xs font-mono-code rounded transition-colors cursor-pointer whitespace-nowrap ${
                  active
                    ? 'bg-sky-600 text-white font-bold shadow-sm'
                    : 'bg-slate-950 text-slate-400 hover:bg-slate-800 hover:text-slate-200 border border-slate-800'
                }`}
              >
                {tab.label}
              </button>
            );
          })}
        </div>
      </div>

      {/* Error state */}
      {error && (
        <div className="m-4 p-4 bg-rose-950/70 border border-rose-800 rounded text-rose-200 space-y-2">
          <div className="flex items-center gap-2 font-semibold text-sm">
            <span className="material-symbols-outlined text-rose-400">error</span>
            <span>Unable to load job queue</span>
          </div>
          <p className="text-xs font-mono-code text-rose-300">
            {error.isNetworkError
              ? `Backend connection error at ${error.endpoint || '/api/v1/jobs'}. Ensure FastAPI is running.`
              : error.message}
          </p>
          <button
            onClick={() => loadJobs(page)}
            className="px-3 py-1 bg-slate-900 border border-rose-700 hover:bg-slate-800 text-rose-300 text-xs font-mono-code rounded font-semibold cursor-pointer"
          >
            Retry
          </button>
        </div>
      )}

      {/* DENSE ENTERPRISE JOBS TABLE */}
      <div className="flex-1 overflow-auto relative bg-slate-950 border-b border-slate-800">
        <table className="w-full text-left border-collapse select-text">
          <thead className="sticky top-0 z-20 bg-slate-900 border-b-2 border-slate-800">
            <tr className="h-9">
              <th className="px-3 text-[10px] font-mono-code uppercase tracking-wider text-slate-400 font-bold border-r border-slate-800 min-w-[120px]">
                Job ID
              </th>
              <th className="px-3 text-[10px] font-mono-code uppercase tracking-wider text-slate-400 font-bold border-r border-slate-800 min-w-[170px]">
                Category
              </th>
              <th className="px-3 text-[10px] font-mono-code uppercase tracking-wider text-slate-400 font-bold border-r border-slate-800 min-w-[170px]">
                Location (PIN / Coords)
              </th>
              <th className="px-3 text-[10px] font-mono-code uppercase tracking-wider text-slate-400 font-bold border-r border-slate-800 text-center min-w-[120px]">
                Status
              </th>
              <th className="px-3 text-[10px] font-mono-code uppercase tracking-wider text-slate-400 font-bold border-r border-slate-800 text-right min-w-[110px]">
                Found
              </th>
              <th className="px-3 text-[10px] font-mono-code uppercase tracking-wider text-slate-400 font-bold border-r border-slate-800 text-right min-w-[110px]">
                Saved
              </th>
              <th className="px-3 text-[10px] font-mono-code uppercase tracking-wider text-slate-400 font-bold border-r border-slate-800 min-w-[140px]">
                Created At
              </th>
              <th className="px-3 text-[10px] font-mono-code uppercase tracking-wider text-slate-400 font-bold text-center min-w-[130px]">
                Actions
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-800 text-xs font-mono-code">
            {loading ? (
              <tr>
                <td colSpan={8} className="py-16 text-center text-slate-400 bg-slate-950">
                  <div className="flex flex-col items-center justify-center gap-2">
                    <span className="w-6 h-6 border-2 border-sky-400 border-t-transparent rounded-full animate-spin" />
                    <span>Loading jobs from queue...</span>
                  </div>
                </td>
              </tr>
            ) : jobs.length === 0 ? (
              <tr>
                <td colSpan={8} className="py-16 text-center text-slate-400 bg-slate-950">
                  <div className="flex flex-col items-center justify-center gap-2">
                    <span className="material-symbols-outlined text-[32px] text-slate-500">task</span>
                    <span className="font-semibold text-slate-300">No jobs match the current filter.</span>
                    <span className="text-xs text-slate-500">Select "All Jobs" or run batch discovery.</span>
                  </div>
                </td>
              </tr>
            ) : (
              jobs.map((job) => {
                const isSelected = selectedJob?.job_id === job.job_id;
                const isBusy = actionProcessingId === job.job_id;

                // Safe primitive extraction from nested objects
                const categoryName = job.category?.category_name || job.search_query || '—';
                const locationLabel = job.location
                  ? `${job.location.pincode} (${job.location.latitude?.toFixed(2)}, ${job.location.longitude?.toFixed(2)})`
                  : '—';

                return (
                  <tr
                    key={job.job_id}
                    onClick={() => setSelectedJob(job)}
                    className={`h-9 hover:bg-slate-900/60 transition-colors cursor-pointer ${
                      isSelected ? 'bg-sky-950/50 border-l-2 border-l-sky-500' : 'bg-slate-950/40'
                    }`}
                  >
                    <td className="px-3 border-r border-slate-800 font-semibold text-sky-400">
                      #{job.job_id.slice(0, 8)}
                    </td>
                    <td className="px-3 border-r border-slate-800 text-slate-200 truncate max-w-[170px]" title={categoryName}>
                      {categoryName}
                    </td>
                    <td className="px-3 border-r border-slate-800 text-slate-400 truncate max-w-[170px]" title={locationLabel}>
                      {locationLabel}
                    </td>
                    <td className="px-3 border-r border-slate-800 text-center">
                      <StatusBadge status={job.status} showDot={job.status === 'RUNNING'} />
                    </td>
                    <td className="px-3 border-r border-slate-800 text-right text-slate-300">
                      {job.listings_found ?? '—'}
                    </td>
                    <td className="px-3 border-r border-slate-800 text-right font-semibold text-emerald-400">
                      {job.businesses_saved ?? '—'}
                    </td>
                    <td className="px-3 border-r border-slate-800 text-slate-400 text-[11px] truncate max-w-[140px]">
                      {formatDateTime(job.created_at)}
                    </td>
                    <td className="px-3 text-center" onClick={(e) => e.stopPropagation()}>
                      <div className="flex items-center justify-center gap-1.5">
                        <button
                          onClick={() => setSelectedJob(job)}
                          className="px-2 py-0.5 bg-slate-800 hover:bg-slate-700 text-slate-300 border border-slate-700 rounded text-[10px] uppercase font-semibold cursor-pointer"
                          title="Inspect job details"
                        >
                          Details
                        </button>

                        {job.status === 'FAILED' || job.status === 'BLOCKED' ? (
                          <button
                            onClick={() => handleRetrySingle(job.job_id)}
                            disabled={isBusy}
                            className="px-2 py-0.5 bg-sky-600 hover:bg-sky-500 text-white rounded text-[10px] uppercase font-semibold transition-colors disabled:opacity-50 cursor-pointer"
                          >
                            {isBusy ? '...' : 'Retry'}
                          </button>
                        ) : job.status === 'PENDING' ? (
                          <button
                            onClick={() => handleRunSingle(job.job_id)}
                            disabled={isBusy}
                            className="px-2 py-0.5 bg-emerald-600 hover:bg-emerald-500 text-white rounded text-[10px] uppercase font-semibold transition-colors disabled:opacity-50 cursor-pointer"
                          >
                            {isBusy ? '...' : 'Run'}
                          </button>
                        ) : null}
                      </div>
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>

      {/* BOTTOM CONSOLE DRAWER: REAL JOB INSPECTOR */}
      <div className="h-36 bg-slate-950 border-t border-slate-800 text-slate-300 p-3 font-mono-code text-xs flex flex-col shrink-0">
        <div className="flex items-center justify-between pb-1.5 border-b border-slate-800 text-[10px] uppercase">
          <div className="flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-emerald-400" />
            <span className="font-bold text-slate-200">
              Job Inspector — {selectedJob ? `Job #${selectedJob.job_id.slice(0, 8)} (${selectedJob.category?.category_name || selectedJob.search_query})` : 'No job selected'}
            </span>
          </div>
          <span className="text-slate-500">FastAPI Playwright Task</span>
        </div>
        <div className="flex-1 overflow-y-auto pt-1.5 space-y-1 text-[11px]">
          {selectedJob ? (
            <>
              <div className="text-slate-300 flex flex-wrap gap-x-4">
                <span><strong>Status:</strong> <span className="text-sky-400">{selectedJob.status}</span></span>
                <span><strong>Attempts:</strong> {selectedJob.attempt_count}</span>
                <span><strong>Listings Found:</strong> {selectedJob.listings_found ?? 0}</span>
                <span><strong>Businesses Saved:</strong> {selectedJob.businesses_saved ?? 0}</span>
              </div>
              <div className="text-slate-400">
                <span><strong>Target:</strong> "{selectedJob.category?.category_name || selectedJob.search_query}" at PIN {selectedJob.location?.pincode || '—'} ({selectedJob.location?.latitude?.toFixed(4)}, {selectedJob.location?.longitude?.toFixed(4)})</span>
              </div>
              {selectedJob.error_message ? (
                <div className="text-rose-400">
                  <span className="text-rose-500 font-bold">[ERROR]</span> {selectedJob.error_message}
                </div>
              ) : (
                <div className="text-slate-500">
                  <span className="text-emerald-500">[STATUS]</span> Job recorded in database. Created: {formatDateTime(selectedJob.created_at)} ({localTimeZone()}).
                </div>
              )}
            </>
          ) : (
            <div className="text-slate-500">Select any job from the table above to view real task parameters and status.</div>
          )}
        </div>
      </div>

      {/* SERVER-SIDE PAGINATION FOOTER */}
      <footer className="h-11 bg-slate-900 border-t border-slate-800 px-4 flex items-center justify-between text-xs font-mono-code shrink-0">
        <div className="text-slate-400">
          Showing <span className="font-bold text-slate-100">{startRecord} - {endRecord}</span> of{' '}
          <span className="font-bold text-slate-100">{total.toLocaleString()}</span> jobs • Server-side: {pageSize}/page
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={() => handlePageChange(page - 1)}
            disabled={page <= 1 || loading}
            className="h-7 px-2.5 bg-slate-800 hover:bg-slate-700 text-slate-300 border border-slate-700 rounded flex items-center gap-1 disabled:opacity-40 cursor-pointer"
          >
            <span className="material-symbols-outlined text-[14px]">chevron_left</span>
            <span>Prev</span>
          </button>

          <span className="text-slate-200 font-semibold px-1">
            Page {page} of {totalPages}
          </span>

          <button
            onClick={() => handlePageChange(page + 1)}
            disabled={page >= totalPages || loading}
            className="h-7 px-2.5 bg-slate-800 hover:bg-slate-700 text-slate-300 border border-slate-700 rounded flex items-center gap-1 disabled:opacity-40 cursor-pointer"
          >
            <span>Next</span>
            <span className="material-symbols-outlined text-[14px]">chevron_right</span>
          </button>

          <div className="hidden sm:flex items-center gap-1.5 ml-2 pl-2 border-l border-slate-800">
            <span className="text-[10px] text-slate-400 uppercase">Go to:</span>
            <input
              type="text"
              value={jumpPage}
              onChange={(e) => setJumpPage(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && handleJump()}
              placeholder={String(page)}
              className="h-7 w-12 bg-slate-950 border border-slate-700 text-slate-200 text-center text-xs rounded focus:border-sky-500 focus:outline-none"
            />
            <button
              onClick={handleJump}
              className="h-7 px-2 bg-slate-800 hover:bg-slate-700 border border-slate-700 text-slate-300 text-[10px] rounded uppercase font-semibold cursor-pointer"
            >
              Jump
            </button>
          </div>
        </div>
      </footer>
    </div>
  );
};
