import React, { useCallback, useEffect, useState } from 'react';
import { clearAutopilotCooldown, fetchAutopilot, updateAutopilot } from '../api';
import type { AutopilotBatch, AutopilotRound, AutopilotSettings, AutopilotStatus } from '../api';

// The scraping autopilot: rounds of batches, one state at a time, on its own.
// This panel switches it on and off, shows what it is doing now, and holds
// its pacing. Everything shown comes from the server, which does the work
// whether or not this page is open.

const time = (iso?: string | null) =>
  iso ? new Date(iso).toLocaleTimeString('en-IN', { timeZone: 'Asia/Kolkata', hour: '2-digit', minute: '2-digit' }) : '—';
const dayTime = (iso?: string | null) =>
  iso ? new Date(iso).toLocaleString('en-IN', { timeZone: 'Asia/Kolkata', day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' }) : '—';
const place = (b: AutopilotBatch) => `${b.tehsil || b.anchor || b.pincode}${b.district ? ` · ${b.district}` : ''}`;

const PHASES: Record<string, { label: string; icon: string; cls: string }> = {
  off: { label: 'Off', icon: 'pause_circle', cls: 'text-slate-300 border-slate-600 bg-slate-800' },
  running_batch: { label: 'Scraping', icon: 'travel_explore', cls: 'text-emerald-300 border-emerald-700 bg-emerald-900/30' },
  starting_round: { label: 'Starting round', icon: 'play_circle', cls: 'text-emerald-300 border-emerald-700 bg-emerald-900/30' },
  between_batches: { label: 'Between batches', icon: 'schedule', cls: 'text-sky-300 border-sky-700 bg-sky-900/30' },
  gap_between_batches: { label: 'Between batches', icon: 'schedule', cls: 'text-sky-300 border-sky-700 bg-sky-900/30' },
  round_complete: { label: 'Round complete', icon: 'task_alt', cls: 'text-sky-300 border-sky-700 bg-sky-900/30' },
  gap_between_rounds: { label: 'Between rounds', icon: 'schedule', cls: 'text-sky-300 border-sky-700 bg-sky-900/30' },
  captcha_cooldown: { label: 'CAPTCHA cool-down', icon: 'gpp_maybe', cls: 'text-amber-300 border-amber-700 bg-amber-900/30' },
  no_internet: { label: 'No internet', icon: 'wifi_off', cls: 'text-amber-300 border-amber-700 bg-amber-900/30' },
  daily_target_reached: { label: 'Done for today', icon: 'check_circle', cls: 'text-emerald-300 border-emerald-700 bg-emerald-900/30' },
  waiting_for_other_run: { label: 'Waiting for a manual batch', icon: 'hourglass_top', cls: 'text-amber-300 border-amber-700 bg-amber-900/30' },
  no_pending_jobs: { label: 'Nothing left to scrape', icon: 'inventory', cls: 'text-slate-300 border-slate-600 bg-slate-800' },
};

export const AutopilotPanel: React.FC = () => {
  const [data, setData] = useState<AutopilotStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [showSettings, setShowSettings] = useState(false);

  const load = useCallback(() => {
    fetchAutopilot().then(d => { setData(d); setError(null); }).catch(e => setError(e.message || 'Could not load the autopilot'));
  }, []);

  useEffect(() => {
    load();
    const t = setInterval(load, 10000);
    return () => clearInterval(t);
  }, [load]);

  const change = async (changes: Partial<AutopilotSettings>) => {
    setBusy(true);
    try { setData(await updateAutopilot(changes)); setError(null); }
    catch (e: any) { setError(e.message || 'Could not save'); }
    finally { setBusy(false); }
  };

  if (!data) {
    return (
      <section className="bg-slate-900 border border-slate-800 rounded p-4 text-sm text-slate-400">
        {error || 'Loading the autopilot…'}
      </section>
    );
  }

  const { settings, state, today } = data;
  const phase = PHASES[state.phase] || { label: state.phase, icon: 'info', cls: 'text-slate-300 border-slate-600 bg-slate-800' };
  const active = data.rounds.find(r => r.status === 'ACTIVE');
  const progress = Math.min(100, (today.batches_done / Math.max(1, today.target)) * 100);

  return (
    <section className="bg-slate-900 border border-slate-800 rounded shadow-sm">
      <div className="p-4 border-b border-slate-800 flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <span className="material-symbols-outlined text-sky-400">autorenew</span>
          <div>
            <h2 className="text-sm font-semibold text-slate-100">Scraping autopilot</h2>
            <p className="text-xs text-slate-500">
              {settings.batches_per_round} batches of {settings.batch_size} per round, one state per round, a different tehsil each batch.
            </p>
          </div>
          <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded border text-[11px] font-semibold ${phase.cls}`}>
            <span className="material-symbols-outlined text-[14px]">{phase.icon}</span>{phase.label}
          </span>
        </div>
        <div className="flex items-center gap-2">
          <button onClick={() => setShowSettings(v => !v)}
            className="h-8 px-3 bg-slate-800 hover:bg-slate-700 border border-slate-700 text-slate-200 text-xs font-semibold rounded">
            {showSettings ? 'Hide pacing' : 'Pacing'}
          </button>
          <button onClick={() => change({ enabled: !settings.enabled })} disabled={busy}
            className={`h-8 px-4 text-xs font-semibold rounded disabled:opacity-50 ${settings.enabled
              ? 'bg-rose-700 hover:bg-rose-600 text-white' : 'bg-emerald-600 hover:bg-emerald-500 text-white'}`}>
            {settings.enabled ? 'Switch off' : 'Switch on'}
          </button>
        </div>
      </div>

      {error && <div className="mx-4 mt-3 p-2 rounded border border-rose-700/50 bg-rose-900/20 text-rose-200 text-xs">{error}</div>}

      <div className="p-4 grid gap-4 lg:grid-cols-3">
        {/* Today */}
        <div className="space-y-3">
          <div>
            <div className="flex items-baseline justify-between text-xs text-slate-400">
              <span>Batches today</span>
              <span className="text-slate-100 text-lg font-semibold tabular-nums">{today.batches_done} <span className="text-slate-500 text-xs font-normal">/ {today.target}</span></span>
            </div>
            <div className="mt-1 h-2 rounded bg-slate-800" role="meter" aria-valuenow={today.batches_done} aria-valuemax={today.target}>
              <div className="h-2 rounded bg-sky-500" style={{ width: `${progress}%` }} />
            </div>
            <div className="mt-1 text-[11px] text-slate-500">
              {today.batches_done >= today.target ? 'Target reached for today.'
                : !settings.enabled ? 'Switched off.'
                : today.target_eta ? `On this pace, the target is reached around ${time(today.target_eta)} IST.`
                : 'A finish time appears after the first batch today.'}
            </div>
          </div>
          <dl className="grid grid-cols-3 gap-2 text-xs">
            {[['Jobs', today.jobs], ['New businesses', today.businesses_saved], ['CAPTCHAs', today.captchas]].map(([k, v]) => (
              <div key={k as string} className="rounded border border-slate-800 bg-slate-950 p-2">
                <dt className="text-slate-500">{k}</dt>
                <dd className="text-slate-100 font-semibold tabular-nums">{v}</dd>
              </div>
            ))}
          </dl>
          <Now data={data} active={active} onClearCooldown={async () => { setData(await clearAutopilotCooldown()); }} />
        </div>

        {/* Current round */}
        <div className="lg:col-span-2">
          {active ? <RoundTable round={active} current={state.phase === 'running_batch' ? state.current_batch : undefined} /> :
            <div className="text-xs text-slate-500">No round under way.</div>}
        </div>
      </div>

      {showSettings && <Pacing settings={settings} states={Object.keys(data.pending_by_state)} onSave={change} busy={busy} />}

      <RecentRounds rounds={data.rounds.filter(r => r.status !== 'ACTIVE')} pending={data.pending_by_state} />
    </section>
  );
};

const Now: React.FC<{ data: AutopilotStatus; active?: AutopilotRound; onClearCooldown: () => void }> = ({ data, active, onClearCooldown }) => {
  const s = data.state;
  const running = active?.plan.find(b => b.batch === s.current_batch);
  let text: React.ReactNode = null;
  switch (s.phase) {
    case 'running_batch':
      text = running && `Scraping batch ${running.batch} of ${active!.batches} in ${active!.state}: ${place(running)}, ${running.jobs_finished}/${running.jobs} jobs done.`;
      break;
    case 'gap_between_batches': case 'between_batches':
      text = `Next batch at ${time(s.next_batch_at)} IST.`;
      break;
    case 'gap_between_rounds': case 'round_complete':
      text = `Next round, in a different state, at ${time(s.next_round_at)} IST.`;
      break;
    case 'captcha_cooldown':
      text = (
        <>
          Google showed a CAPTCHA. Paused until {time(s.cooldown_until)} IST (level {s.captcha_level}), then continuing more slowly.{' '}
          <button onClick={onClearCooldown} className="underline text-amber-200">End the pause now</button>
        </>
      );
      break;
    case 'no_internet':
      text = (
        <>
          The server has no internet connection. Nothing is scraped until it is back; checking again at {time(s.offline_until)} IST.{' '}
          <button onClick={onClearCooldown} className="underline text-amber-200">Check now</button>
        </>
      );
      break;
    case 'daily_target_reached':
      text = 'Daily target reached. The next round starts after midnight IST.';
      break;
    case 'waiting_for_other_run':
      text = 'A batch started by hand is running; the autopilot waits so two browsers never search at once.';
      break;
    case 'no_pending_jobs':
      text = 'No state has pending jobs left. Add PINs or categories to give it more to do.';
      break;
    case 'off':
      text = 'Switched off. Nothing runs until it is switched on.';
      break;
  }
  return (
    <div className="rounded border border-slate-800 bg-slate-950 p-3 text-xs text-slate-300 space-y-1">
      {text && <div>{text}</div>}
      {s.last_event && <div className="text-slate-500">Last: {s.last_event} <span className="text-slate-600">· {dayTime(s.last_event_at)}</span></div>}
    </div>
  );
};

const BATCH_STATUS: Record<string, string> = {
  PLANNED: 'text-slate-400', RUNNING: 'text-emerald-300', DONE: 'text-sky-300', SKIPPED: 'text-amber-300',
};

const RoundTable: React.FC<{ round: AutopilotRound; current?: number }> = ({ round, current }) => (
  <div>
    <div className="text-xs text-slate-400 mb-2">
      Current round: <span className="text-slate-100 font-semibold">{round.state}</span> · {round.batches_done} of {round.batches} batches done · planned {dayTime(round.created_at)}
    </div>
    <div className="overflow-x-auto">
      <table className="w-full text-xs">
        <thead className="text-slate-500 text-left">
          <tr>{['#', 'Tehsil · District', 'Categories', 'Jobs', 'New businesses', 'Status'].map(h => <th key={h} className="px-2 py-1 font-semibold">{h}</th>)}</tr>
        </thead>
        <tbody>
          {round.plan.map(b => (
            <tr key={b.batch} className={`border-t border-slate-800 ${b.batch === current ? 'bg-emerald-900/10' : ''}`}>
              <td className="px-2 py-1.5 text-slate-400">{b.batch}</td>
              <td className="px-2 py-1.5 text-slate-200">{place(b)}</td>
              <td className="px-2 py-1.5 text-slate-400" title={b.categories.join(', ')}>{b.categories.length}</td>
              <td className="px-2 py-1.5 tabular-nums">
                <div className="flex items-center gap-2">
                  <div className="h-1.5 w-16 rounded bg-slate-800"><div className="h-1.5 rounded bg-sky-500" style={{ width: `${(b.jobs_finished / Math.max(1, b.jobs)) * 100}%` }} /></div>
                  <span className="text-slate-300">{b.jobs_finished}/{b.jobs}</span>
                </div>
              </td>
              <td className="px-2 py-1.5 tabular-nums text-slate-300">{b.businesses_saved || '—'}</td>
              <td className={`px-2 py-1.5 font-semibold ${BATCH_STATUS[b.status] || 'text-slate-400'}`}>
                {b.status === 'RUNNING' ? 'Scraping' : b.status.toLowerCase()}{b.blocks ? ` · ${b.blocks} CAPTCHA` : ''}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  </div>
);

const RecentRounds: React.FC<{ rounds: AutopilotRound[]; pending: Record<string, number> }> = ({ rounds, pending }) => (
  <div className="px-4 pb-4 grid gap-4 lg:grid-cols-3">
    <div className="lg:col-span-2">
      <div className="text-xs font-semibold text-slate-300 mb-1">Recent rounds</div>
      {rounds.length === 0 ? <div className="text-xs text-slate-500">None yet.</div> : (
        <table className="w-full text-xs">
          <tbody>
            {rounds.slice(0, 8).map(r => (
              <tr key={r.round_id} className="border-t border-slate-800 text-slate-300">
                <td className="px-2 py-1.5 text-slate-100">{r.state}</td>
                <td className="px-2 py-1.5">{r.batches_done}/{r.batches} batches</td>
                <td className="px-2 py-1.5 text-slate-400 truncate max-w-[280px]" title={r.plan.map(place).join(' | ')}>{r.plan.map(b => b.tehsil || b.anchor).join(', ')}</td>
                <td className="px-2 py-1.5 tabular-nums">{r.plan.reduce((n, b) => n + (b.businesses_saved || 0), 0)} new</td>
                <td className="px-2 py-1.5 text-slate-500 whitespace-nowrap">{dayTime(r.created_at)} – {time(r.completed_at)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
    <div>
      <div className="text-xs font-semibold text-slate-300 mb-1">Jobs left by state</div>
      <ul className="text-xs space-y-1">
        {Object.entries(pending).sort((a, b) => b[1] - a[1]).map(([s, n]) => (
          <li key={s} className="flex justify-between border-t border-slate-800 pt-1"><span className="text-slate-300">{s}</span><span className="tabular-nums text-slate-400">{n.toLocaleString('en-IN')}</span></li>
        ))}
      </ul>
    </div>
  </div>
);

const Pacing: React.FC<{ settings: AutopilotSettings; states: string[]; onSave: (c: Partial<AutopilotSettings>) => void; busy: boolean }> = ({ settings, states, onSave, busy }) => {
  const [form, setForm] = useState<AutopilotSettings>(settings);
  useEffect(() => setForm(settings), [settings]);
  const num = (key: keyof AutopilotSettings, label: string, hint?: string, step = 1) => (
    <label className="text-xs text-slate-400 flex flex-col gap-1">
      {label}
      <input type="number" step={step} value={form[key] as number}
        onChange={e => setForm(f => ({ ...f, [key]: Number(e.target.value) }))}
        className="h-8 px-2 bg-slate-950 border border-slate-700 rounded text-slate-100 w-28" />
      {hint && <span className="text-[10px] text-slate-600">{hint}</span>}
    </label>
  );
  const { enabled, ...changes } = form;
  void enabled;
  return (
    <div className="mx-4 mb-4 p-4 rounded border border-slate-800 bg-slate-950">
      <div className="flex flex-wrap gap-4">
        {num('daily_batch_target', 'Batches per day')}
        {num('batch_size', 'Jobs per batch')}
        {num('batches_per_round', 'Batches per round')}
        {num('gap_between_rounds_minutes', 'Minutes between rounds')}
        {num('job_delay_seconds', 'Pause after each job (s)', 'plus a random extra up to…', 0.5)}
        {num('job_delay_jitter_seconds', 'Random extra (s)', undefined, 0.5)}
        <label className="text-xs text-slate-400 flex flex-col gap-1">
          Pause between batches (s)
          <span className="flex items-center gap-1">
            {[0, 1].map(i => (
              <input key={i} type="number" value={form.gap_between_batches_seconds[i]}
                onChange={e => setForm(f => {
                  const g: [number, number] = [...f.gap_between_batches_seconds] as [number, number];
                  g[i] = Number(e.target.value);
                  return { ...f, gap_between_batches_seconds: g };
                })}
                className="h-8 px-2 bg-slate-950 border border-slate-700 rounded text-slate-100 w-20" />
            ))}
          </span>
          <span className="text-[10px] text-slate-600">random, between these</span>
        </label>
        <label className="text-xs text-slate-400 flex items-center gap-2 self-center">
          <input type="checkbox" checked={form.continue_after_target}
            onChange={e => setForm(f => ({ ...f, continue_after_target: e.target.checked }))} />
          Keep going past the daily target
        </label>
        <label className="text-xs text-slate-400 flex items-center gap-2 self-center">
          <input type="checkbox" checked={form.retry_failed_jobs ?? true}
            onChange={e => setForm(f => ({ ...f, retry_failed_jobs: e.target.checked }))} />
          Try failed jobs again
        </label>
      </div>
      <div className="mt-3 text-xs text-slate-400">
        States to rotate through <span className="text-slate-600">(none ticked = all with work left)</span>
        <div className="flex flex-wrap gap-3 mt-1">
          {states.map(s => (
            <label key={s} className="flex items-center gap-1 text-slate-300">
              <input type="checkbox" checked={form.states.includes(s)}
                onChange={e => setForm(f => ({ ...f, states: e.target.checked ? [...f.states, s] : f.states.filter(x => x !== s) }))} />
              {s}
            </label>
          ))}
        </div>
      </div>
      <button onClick={() => onSave(changes)} disabled={busy}
        className="mt-4 h-8 px-4 bg-sky-600 hover:bg-sky-500 text-white text-xs font-semibold rounded disabled:opacity-50">
        Save pacing
      </button>
    </div>
  );
};
