import React, { useCallback, useEffect, useState } from 'react';
import { fetchSystemHealth } from '../api';
import type { HealthPart, HealthStatus, SystemHealth } from '../api';

// System health (22 Nov 2026): whether the website, the worker and the scraper are
// alive, so nobody has to open the server to find out. Each part reports itself
// every 30 seconds; a part silent for over two and a half minutes is "Stopped".

const LOOK: Record<HealthStatus, { label: string; icon: string; dot: string; ring: string; text: string; band: string }> = {
  ok: { label: 'Running', icon: 'check_circle', dot: 'bg-emerald-400', ring: 'border-emerald-700/60',
        text: 'text-emerald-300', band: 'linear-gradient(120deg,#0f5132 0%,#14804a 100%)' },
  warning: { label: 'Needs a look', icon: 'warning', dot: 'bg-amber-400', ring: 'border-amber-700/60',
             text: 'text-amber-300', band: 'linear-gradient(120deg,#7a4a05 0%,#b7791f 100%)' },
  stopped: { label: 'Stopped', icon: 'error', dot: 'bg-rose-500', ring: 'border-rose-700/60',
             text: 'text-rose-300', band: 'linear-gradient(120deg,#7f1d1d 0%,#be123c 100%)' },
};
const ICONS: Record<HealthPart['role'], string> = { api: 'language', worker: 'notifications_active', scraper: 'travel_explore', all: 'hub' };
const HEADLINE: Record<HealthStatus, string> = {
  ok: 'Everything is running',
  warning: 'Running, but something needs a look',
  stopped: 'A part of AutoGMap has stopped',
};

const ago = (s: number | null) =>
  s == null ? 'never' : s < 60 ? `${s}s ago` : s < 3600 ? `${Math.round(s / 60)} min ago` : `${Math.round(s / 3600)} h ago`;
const clock = (iso?: string | null) =>
  iso ? new Date(iso).toLocaleString('en-IN', { timeZone: 'Asia/Kolkata', day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' }) : '—';

const MemoryGauge: React.FC<{ used: number; limit: number }> = ({ used, limit }) => {
  const share = Math.min(1, used / Math.max(limit, 1));
  const colour = share >= 0.85 ? '#f43f5e' : share >= 0.65 ? '#f59e0b' : '#34d399';
  const R = 22, C = 2 * Math.PI * R;
  return (
    <div className="relative h-[60px] w-[60px] shrink-0" title={`${used} of ${limit} MB`}>
      <svg viewBox="0 0 56 56" className="h-full w-full -rotate-90" aria-hidden="true">
        <circle cx="28" cy="28" r={R} fill="none" strokeWidth="6" className="stroke-slate-800" />
        <circle cx="28" cy="28" r={R} fill="none" strokeWidth="6" stroke={colour} strokeLinecap="round"
          strokeDasharray={`${share * C} ${C}`} className="transition-all duration-700" />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center leading-none">
        <span className="text-[13px] font-bold tabular-nums text-slate-100">{Math.round(share * 100)}%</span>
        <span className="text-[9px] text-slate-500 mt-0.5">memory</span>
      </div>
    </div>
  );
};

const PartCard: React.FC<{ part: HealthPart }> = ({ part }) => {
  const look = LOOK[part.status];
  const [open, setOpen] = useState(false);
  return (
    <div className={`rounded-xl border ${look.ring} bg-slate-950/60 p-4 flex flex-col gap-3`}>
      <div className="flex items-start gap-3">
        <div className="h-10 w-10 rounded-lg bg-slate-800 flex items-center justify-center shrink-0">
          <span className="material-symbols-outlined text-[22px] text-slate-200">{ICONS[part.role]}</span>
        </div>
        <div className="flex-1 min-w-0">
          <div className="font-semibold text-slate-100">{part.label}</div>
          <div className="flex items-center gap-1.5 mt-0.5">
            <span className="relative flex h-2.5 w-2.5">
              {part.status === 'ok' && <span className={`absolute inline-flex h-full w-full rounded-full ${look.dot} opacity-60 animate-ping`} />}
              <span className={`relative inline-flex h-2.5 w-2.5 rounded-full ${look.dot}`} />
            </span>
            <span className={`text-[12px] font-semibold ${look.text}`}>{look.label}</span>
          </div>
        </div>
      </div>
      <div className="text-[12px] text-slate-500 -mt-1">{part.job}</div>
      <div className="flex items-center gap-3">
        {part.memory && <MemoryGauge used={part.memory.used_mb} limit={part.memory.limit_mb} />}
        <div className={`text-[13px] ${part.status === 'ok' ? 'text-slate-300' : look.text}`}>
          {part.why}
          {part.memory && <div className="text-[11px] text-slate-500 mt-0.5">{part.memory.used_mb} of {part.memory.limit_mb} MB memory</div>}
        </div>
      </div>
      {part.threads.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {part.threads.map(t => (
            <span key={t.name} className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] ${
              t.alive ? 'border-emerald-800/60 text-emerald-300 bg-emerald-950/40' : 'border-rose-800/60 text-rose-300 bg-rose-950/40'}`}>
              <span className="material-symbols-outlined text-[13px]">{t.alive ? 'check' : 'close'}</span>{t.label}
            </span>
          ))}
        </div>
      )}
      <div className="flex flex-wrap items-center justify-between gap-x-3 text-[11.5px] text-slate-500">
        <span>Last heard {ago(part.seen_seconds_ago)}</span>
        <span>Up since {clock(part.up_since)}</span>
      </div>
      {part.errors.length > 0 && (
        <div>
          <button onClick={() => setOpen(o => !o)} className="text-[12px] text-amber-300 hover:underline cursor-pointer inline-flex items-center gap-1">
            <span className="material-symbols-outlined text-[15px]">{open ? 'expand_less' : 'expand_more'}</span>
            {open ? 'Hide' : 'Show'} the last {part.errors.length} error{part.errors.length === 1 ? '' : 's'}
          </button>
          {open && (
            <ul className="mt-2 space-y-1.5 max-h-48 overflow-y-auto select-text">
              {part.errors.map((e, i) => (
                <li key={i} className="rounded-md bg-slate-900 border border-slate-800 px-2.5 py-1.5 text-[11.5px]">
                  <div className="text-slate-500">{clock(e.at)} · {e.where}</div>
                  <div className="text-slate-200 break-words">{e.text}</div>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
};

export const SystemHealthPanel: React.FC = () => {
  const [data, setData] = useState<SystemHealth | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    fetchSystemHealth().then(d => { setData(d); setError(null); })
      .catch(e => setError(e.message || 'Could not reach the website'));
  }, []);

  useEffect(() => {
    load();
    const t = setInterval(load, 20000);
    return () => clearInterval(t);
  }, [load]);

  if (!data) {
    return (
      <section className="rounded-2xl border border-slate-800 bg-slate-900 p-5 text-sm text-slate-400 animate-pulse">
        {error || 'Checking AutoGMap’s health…'}
      </section>
    );
  }
  const look = LOOK[data.overall];
  const q = data.queue;
  const run = data.last_run;
  return (
    <section id="system-health" className="rounded-2xl border border-slate-800 bg-slate-900 shadow-sm overflow-hidden scroll-mt-4">
      <div className="relative px-5 py-4 text-white flex flex-wrap items-center gap-3" style={{ background: look.band }}>
        <span className="material-symbols-outlined absolute -right-6 -bottom-10 text-[150px] text-white/10 pointer-events-none select-none">monitor_heart</span>
        <span className="material-symbols-outlined text-[30px]">{look.icon}</span>
        <div className="relative flex-1 min-w-[200px]">
          <div className="text-[11px] uppercase tracking-[0.14em] font-semibold text-white/75">System health</div>
          <div className="text-lg font-semibold">{HEADLINE[data.overall]}</div>
        </div>
        <div className="relative text-[12px] text-white/80">
          Checked {clock(data.checked_at)} · refreshes every 20s
          {error && <span className="ml-2 text-white">({error})</span>}
        </div>
      </div>

      <div className="p-5 flex flex-col gap-4">
        <div className={`grid gap-3 ${data.parts.length > 1 ? 'lg:grid-cols-2 2xl:grid-cols-3' : ''}`}>
          {data.parts.map(p => <PartCard key={p.role} part={p} />)}
        </div>

        <div className="grid gap-3 sm:grid-cols-2">
          <div className="rounded-xl border border-slate-800 bg-slate-950/60 p-4">
            <div className="flex items-center gap-2 text-[12px] uppercase tracking-wider font-semibold text-slate-400">
              <span className="material-symbols-outlined text-[17px]">queue</span>Scraping queue
            </div>
            <div className="mt-2 flex items-end gap-5">
              {[
                { n: q.queued, label: 'waiting', cls: q.queued ? 'text-sky-300' : 'text-slate-200' },
                { n: q.running, label: 'running', cls: q.running ? 'text-emerald-300' : 'text-slate-200' },
                { n: q.failed_today, label: 'failed today', cls: q.failed_today ? 'text-rose-300' : 'text-slate-200' },
              ].map(x => (
                <div key={x.label}>
                  <div className={`text-2xl font-bold tabular-nums ${x.cls}`}>{x.n}</div>
                  <div className="text-[11px] text-slate-500">{x.label}</div>
                </div>
              ))}
            </div>
            {/* Tasks wait their turn behind a running one: only a queue that waits with nothing
                running means the scraper is not picking work up. */}
            {q.queued > 0 && q.running > 0 && (
              <div className="mt-2 text-[12px] text-slate-500">The waiting ones run one after another, after the one running now.</div>
            )}
            {q.running === 0 && q.oldest_waiting_seconds != null && q.oldest_waiting_seconds > 120 && (
              <div className="mt-2 text-[12px] text-amber-300">Nothing has run for {ago(q.oldest_waiting_seconds).replace(' ago', '')} while work waits: is the scraper running?</div>
            )}
          </div>
          <div className="rounded-xl border border-slate-800 bg-slate-950/60 p-4">
            <div className="flex items-center gap-2 text-[12px] uppercase tracking-wider font-semibold text-slate-400">
              <span className="material-symbols-outlined text-[17px]">history</span>Last scraping batch
            </div>
            {run ? (
              <div className="mt-2 text-[13px] text-slate-300 space-y-1">
                <div><b className="text-slate-100">{run.status}</b> · started {clock(run.started_at)}{run.finished_at ? `, ended ${clock(run.finished_at)}` : ''}</div>
                <div>{run.jobs_completed} searches done{run.jobs_failed ? `, ${run.jobs_failed} failed` : ''} · {run.businesses_new} new businesses</div>
                <div className="text-[11.5px] text-slate-500">Started by: {run.trigger}</div>
              </div>
            ) : <div className="mt-2 text-[13px] text-slate-500">No batch yet.</div>}
          </div>
        </div>
      </div>
    </section>
  );
};
