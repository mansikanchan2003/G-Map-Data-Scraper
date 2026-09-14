import { useEffect, useState } from 'react';
import { SystemService } from '../api';
import { Server, CheckCircle, AlertTriangle, PlayCircle, Loader2 } from 'lucide-react';

export default function DashboardView() {
  const [stats, setStats] = useState<any>(null);
  const [health, setHealth] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function loadData() {
      try {
        const [healthData, statsData] = await Promise.all([
          SystemService.getHealth(),
          SystemService.getStats()
        ]);
        setHealth(healthData);
        setStats(statsData);
      } catch (err: any) {
        setError(err.message || 'Failed to load dashboard data');
      } finally {
        setLoading(false);
      }
    }
    loadData();
  }, []);

  if (loading) return (
    <div className="flex h-full items-center justify-center">
      <Loader2 className="animate-spin text-cyan" size={48} />
    </div>
  );

  if (error) return (
    <div className="glass-card border-red-500 text-red-500">
      <h2 className="flex items-center gap-2"><AlertTriangle /> System Error</h2>
      <p>{error}</p>
    </div>
  );

  const pendingJobs = stats?.jobs?.pending || 0;
  const isHealthy = health?.status === 'healthy';

  return (
    <div className="flex-col gap-6 w-full max-w-6xl mx-auto">
      <header className="flex justify-between items-center mb-6">
        <div>
          <h1>System Dashboard</h1>
          <p>Autonomous Google Maps Data Collection Engine</p>
        </div>
        <div className={`badge ${isHealthy ? 'badge-success' : 'badge-error'} text-lg py-2 px-4`}>
          {isHealthy ? <><Server size={18} className="mr-2"/> System Online</> : 'System Offline'}
        </div>
      </header>

      {/* KPI Row 1 */}
      <div className="flex gap-6 mb-6">
        <div className="glass-card flex-1">
          <h3 className="text-muted text-sm font-semibold uppercase tracking-wider mb-2">Total Businesses</h3>
          <div className="text-4xl font-bold text-gradient">{stats?.businesses?.total?.toLocaleString() || 0}</div>
          <div className="mt-2 text-sm text-success">
            {stats?.businesses?.valid?.toLocaleString() || 0} Valid Records
          </div>
        </div>

        <div className="glass-card flex-1">
          <h3 className="text-muted text-sm font-semibold uppercase tracking-wider mb-2">Total Jobs</h3>
          <div className="text-4xl font-bold">{stats?.jobs?.total?.toLocaleString() || 0}</div>
          <div className="mt-2 text-sm text-cyan flex justify-between">
            <span>{stats?.locations_count} Locations</span>
            <span>× {stats?.categories_count} Categories</span>
          </div>
        </div>
        
        <div className="glass-card flex-1">
          <h3 className="text-muted text-sm font-semibold uppercase tracking-wider mb-2">Pending Jobs</h3>
          <div className="text-4xl font-bold text-warning">{pendingJobs.toLocaleString()}</div>
          <div className="mt-2 text-sm text-muted">Awaiting next batch run</div>
        </div>
      </div>

      {/* KPI Row 2 (Job Breakdown & Last Run) */}
      <div className="flex gap-6">
        <div className="glass-card flex-[2]">
          <h3 className="mb-4">Job Distribution</h3>
          <div className="flex justify-between items-center bg-[rgba(0,0,0,0.2)] p-4 rounded-lg mb-2">
            <span className="flex items-center gap-2"><CheckCircle size={16} className="text-success" /> Completed</span>
            <span className="font-bold">{stats?.jobs?.completed?.toLocaleString() || 0}</span>
          </div>
          <div className="flex justify-between items-center bg-[rgba(0,0,0,0.2)] p-4 rounded-lg mb-2">
            <span className="flex items-center gap-2"><PlayCircle size={16} className="text-cyan" /> Running</span>
            <span className="font-bold">{stats?.jobs?.running?.toLocaleString() || 0}</span>
          </div>
          <div className="flex justify-between items-center bg-[rgba(0,0,0,0.2)] p-4 rounded-lg mb-2">
            <span className="flex items-center gap-2"><AlertTriangle size={16} className="text-warning" /> Partial</span>
            <span className="font-bold">{stats?.jobs?.partial?.toLocaleString() || 0}</span>
          </div>
          <div className="flex justify-between items-center bg-[rgba(0,0,0,0.2)] p-4 rounded-lg">
            <span className="flex items-center gap-2"><AlertTriangle size={16} className="text-error" /> Failed / Blocked</span>
            <span className="font-bold">{(stats?.jobs?.failed || 0) + (stats?.jobs?.blocked || 0)}</span>
          </div>
        </div>

        <div className="glass-card flex-1">
          <h3 className="mb-4">Latest Orchestration Run</h3>
          {stats?.last_run ? (
            <div className="flex-col gap-4">
              <div>
                <div className="text-xs text-muted uppercase">Status</div>
                <div className="font-bold text-lg">{stats.last_run.status}</div>
              </div>
              <div>
                <div className="text-xs text-muted uppercase">Started At</div>
                <div className="font-bold">{new Date(stats.last_run.started_at).toLocaleString()}</div>
              </div>
              <div>
                <div className="text-xs text-muted uppercase">Jobs Completed</div>
                <div className="font-bold text-cyan">{stats.last_run.jobs_completed}</div>
              </div>
              <div>
                <div className="text-xs text-muted uppercase">New Businesses Found</div>
                <div className="font-bold text-success">{stats.last_run.businesses_new}</div>
              </div>
            </div>
          ) : (
            <div className="text-muted mt-4">No recent runs recorded.</div>
          )}
        </div>
      </div>
    </div>
  );
}
