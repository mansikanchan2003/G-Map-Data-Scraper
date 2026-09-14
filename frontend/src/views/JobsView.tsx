import { useEffect, useState, useCallback } from 'react';
import { JobsService } from '../api';
import { Loader2, RefreshCw, ChevronLeft, ChevronRight, AlertCircle } from 'lucide-react';

export default function JobsView() {
  const [data, setData] = useState<any>({ items: [], total: 0, page: 1, total_pages: 1 });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  
  const [page, setPage] = useState(1);
  const [statusFilter, setStatusFilter] = useState('');
  const [isRetrying, setIsRetrying] = useState(false);

  const loadData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await JobsService.getJobs(page, 100, statusFilter || undefined);
      setData(res);
    } catch (err: any) {
      setError(err.message || 'Failed to load jobs');
    } finally {
      setLoading(false);
    }
  }, [page, statusFilter]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const handleRetryAll = async () => {
    if (!window.confirm("Are you sure you want to reset all eligible FAILED/PARTIAL jobs to PENDING?")) return;
    
    setIsRetrying(true);
    try {
      await JobsService.retryAll('FAILED');
      await loadData();
    } catch (err: any) {
      alert("Failed to retry jobs: " + err.message);
    } finally {
      setIsRetrying(false);
    }
  };

  const getStatusBadgeClass = (status: string) => {
    switch(status) {
      case 'COMPLETED': return 'badge-success';
      case 'PENDING': return 'badge-info';
      case 'RUNNING': return 'badge-warning';
      case 'FAILED':
      case 'BLOCKED': return 'badge-error';
      default: return 'badge-neutral';
    }
  };

  return (
    <div className="flex-col gap-6 w-full max-w-7xl mx-auto h-full relative">
      <header className="flex justify-between items-center mb-6">
        <div>
          <h1>Jobs Monitor</h1>
          <p>Track autonomous discovery operations</p>
        </div>
        <div className="flex gap-4">
          <button className="btn btn-secondary" onClick={loadData}>
            <RefreshCw size={16} /> Refresh
          </button>
          <button 
            className="btn btn-danger" 
            onClick={handleRetryAll}
            disabled={isRetrying}
          >
            {isRetrying ? <Loader2 className="animate-spin" size={16} /> : <AlertCircle size={16} />}
            Retry Failed Jobs
          </button>
        </div>
      </header>

      {/* Filters */}
      <div className="glass-card mb-6 flex items-end gap-4">
        <div className="input-group w-64">
          <label className="input-label">Filter by Status</label>
          <select 
            className="input-field" 
            value={statusFilter}
            onChange={e => {setStatusFilter(e.target.value); setPage(1);}}
          >
            <option value="">All Statuses</option>
            <option value="PENDING">Pending</option>
            <option value="RUNNING">Running</option>
            <option value="COMPLETED">Completed</option>
            <option value="PARTIAL">Partial</option>
            <option value="FAILED">Failed</option>
            <option value="BLOCKED">Blocked</option>
          </select>
        </div>
      </div>

      {error && (
        <div className="glass-card border-red-500 text-red-500 mb-6">
          <p>{error}</p>
        </div>
      )}

      {/* Data Table */}
      <div className="glass-card p-0 overflow-hidden flex-1 flex flex-col min-h-[500px]">
        <div className="table-container flex-1 overflow-y-auto">
          {loading ? (
            <div className="flex h-64 items-center justify-center">
              <Loader2 className="animate-spin text-cyan" size={32} />
            </div>
          ) : data.items.length === 0 ? (
            <div className="flex h-64 items-center justify-center text-muted">
              No jobs found.
            </div>
          ) : (
            <table>
              <thead>
                <tr>
                  <th>Job ID</th>
                  <th>Category</th>
                  <th>Location (Lat/Lng)</th>
                  <th>Status</th>
                  <th>Found / Saved</th>
                  <th>Created At</th>
                </tr>
              </thead>
              <tbody>
                {data.items.map((job: any) => (
                  <tr key={job.job_id}>
                    <td className="font-mono text-xs text-muted">{job.job_id}</td>
                    <td className="font-medium text-cyan">{job.category?.category_name || '-'}</td>
                    <td className="text-sm">
                      {job.location?.latitude?.toFixed(4)}, {job.location?.longitude?.toFixed(4)}
                    </td>
                    <td>
                      <span className={`badge ${getStatusBadgeClass(job.status)}`}>
                        {job.status}
                      </span>
                    </td>
                    <td className="text-sm">
                      {job.listings_found !== null ? job.listings_found : '-'}{' / '}
                      <span className="text-success">{job.businesses_saved !== null ? job.businesses_saved : '-'}</span>
                    </td>
                    <td className="text-sm text-muted">
                      {new Date(job.created_at).toLocaleString()}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>

        {/* Pagination Footer */}
        <div className="p-4 border-t border-[rgba(255,255,255,0.08)] flex justify-between items-center bg-[rgba(15,23,42,0.8)]">
          <div className="text-sm text-muted">
            Showing <span className="text-primary font-medium">{data.items.length > 0 ? (data.page - 1) * data.page_size + 1 : 0}</span> to <span className="text-primary font-medium">{Math.min(data.page * data.page_size, data.total)}</span> of <span className="text-primary font-medium">{data.total.toLocaleString()}</span> jobs
          </div>
          <div className="flex items-center gap-4">
            <span className="text-sm text-muted">Page {data.page} of {data.total_pages || 1}</span>
            <div className="flex gap-2">
              <button 
                className="btn btn-secondary px-2 py-1" 
                disabled={!data.has_prev}
                onClick={() => setPage(p => Math.max(1, p - 1))}
              >
                <ChevronLeft size={18} /> Prev
              </button>
              <button 
                className="btn btn-secondary px-2 py-1" 
                disabled={!data.has_next}
                onClick={() => setPage(p => p + 1)}
              >
                Next <ChevronRight size={18} />
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
