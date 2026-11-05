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
  too_many_failures: { label: 'Stopped: batches failing', icon: 'error', cls: 'text-rose-300 border-rose-700 bg-rose-900/30' },
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
      <section className="rounded-2xl border border-slate-800 bg-slate-900 p-5 text-sm text-slate-400 animate-pulse">
        {error || 'Loading the autopilot…'}
      </section>
    );
  }

  const { settings, state, today } = data;
  const phase = PHASES[state.phase] || { label: state.phase, icon: 'info', cls: 'text-slate-300 border-slate-600 bg-slate-800' };
  const active = data.rounds.find(r => r.status === 'ACTIVE');
  const progress = Math.min(100, (today.batches_done / Math.max(1, today.target)) * 100);
  const R = 42, C = 2 * Math.PI * R;
  const on = settings.enabled;

  return (
    <section className="rounded-2xl border border-slate-800 bg-slate-900 overflow-hidden shadow-sm">
      {/* The banner: on in Eko teal, off in slate (white text in both themes). */}
      <div className="relative overflow-hidden p-5 text-white"
        style={{ background: on ? 'linear-gradient(120deg, #0a3543 0%, #0f5c5a 55%, #138a6e 100%)' : 'linear-gradient(120deg, #1e293b 0%, #334155 100%)' }}>
        <span className="material-symbols-outlined absolute -right-6 -top-8 text-[180px] text-white/5 pointer-events-none select-none">autorenew</span>
        <div className="relative flex flex-wrap items-center gap-5">
          {/* Today's batches against the target, as a ring. */}
          <div className="relative h-[104px] w-[104px] shrink-0">
            <svg viewBox="0 0 100 100" className="h-full w-full -rotate-90" role="meter" aria-valuenow={today.batches_done} aria-valuemax={today.target}>
              <circle cx="50" cy="50" r={R} fill="none" stroke="rgba(255,255,255,0.15)" strokeWidth="9" />
              <circle cx="50" cy="50" r={R} fill="none" stroke="#f9ab10" strokeWidth="9" strokeLinecap="round"
                strokeDasharray={`${(progress / 100) * C} ${C}`} className="transition-all duration-700" />
            </svg>
            <div className="absolute inset-0 flex flex-col items-center justify-center">
              <span className="text-[26px] font-bold tabular-nums leading-none">{today.batches_done}</span>
              <span className="text-[11px] text-white/70">of {today.target} today</span>
            </div>
          </div>
          <div className="flex-1 min-w-[220px]">
            <div className="text-[11px] uppercase tracking-[0.14em] font-semibold flex flex-wrap items-center gap-2" style={{ color: '#f9ab10' }}>
              Scraping autopilot
              <span className="normal-case tracking-normal inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-white/15 text-white text-[11px] font-semibold">
                {on && state.phase === 'running_batch' && <span className="h-1.5 w-1.5 rounded-full bg-emerald-300 animate-pulse" />}
                <span className="material-symbols-outlined text-[14px]">{phase.icon}</span>{phase.label}
              </span>
            </div>
            <div className="text-[20px] font-semibold leading-snug mt-1">
              {today.batches_done >= today.target ? "Today's batches are done"
                : !on ? 'Switched off'
                : `${today.target - today.batches_done} batches to go today`}
            </div>
            <p className="text-[12.5px] text-white/75 mt-0.5">
              {settings.batch_size} jobs a batch · {settings.batches_per_round} batches a round, one state a round, a different tehsil each batch
              {on && today.target_eta && today.batches_done < today.target ? ` · done around ${time(today.target_eta)} IST` : ''}
            </p>
          </div>
          <div className="flex items-center gap-2" data-edit>
            <button onClick={() => setShowSettings(v => !v)}
              className="h-9 px-3.5 rounded-lg bg-white/10 hover:bg-white/20 ring-1 ring-white/20 text-white text-xs font-semibold inline-flex items-center gap-1.5 cursor-pointer">
              <span className="material-symbols-outlined text-[16px]">tune</span>{showSettings ? 'Hide pacing' : 'Pacing'}
            </button>
            <button onClick={() => change({ enabled: !on })} disabled={busy}
              className={`h-9 px-4 rounded-lg text-xs font-bold inline-flex items-center gap-1.5 shadow-md disabled:opacity-50 cursor-pointer transition ${on
                ? 'bg-white text-rose-700 hover:bg-rose-50' : 'text-[#0a3543] hover:brightness-110'}`}
              style={on ? undefined : { background: '#f9ab10' }}>
              <span className="material-symbols-outlined text-[16px]">{on ? 'pause' : 'play_arrow'}</span>
              {on ? 'Switch off' : 'Switch on'}
            </button>
          </div>
        </div>
        <div className="relative grid grid-cols-3 gap-3 mt-4">
          {([['Jobs today', today.jobs, 'work', '#7dd3fc'], ['New businesses', today.businesses_saved, 'storefront', '#6ee7b7'],
             ['CAPTCHAs', today.captchas, 'gpp_maybe', '#fcd34d']] as const).map(([k, v, icon, colour]) => (
            <div key={k} className="rounded-xl bg-white/10 px-3.5 py-2.5">
              <div className="flex items-center gap-1.5 text-[11px] text-white/70">
                <span className="material-symbols-outlined text-[15px]" style={{ color: colour }}>{icon}</span>{k}
              </div>
              <div className="text-xl font-semibold tabular-nums mt-0.5">{(v ?? 0).toLocaleString('en-IN')}</div>
            </div>
          ))}
        </div>
      </div>

      {error && <div className="mx-5 mt-4 p-2.5 rounded-lg border border-rose-800/60 bg-rose-950 text-rose-300 text-xs">{error}</div>}

      <div className="p-5 space-y-5">
        <Now data={data} active={active} onClearCooldown={async () => { setData(await clearAutopilotCooldown()); }} />
        {active ? <RoundTable round={active} current={state.phase === 'running_batch' ? state.current_batch : undefined} /> : (
          <div className="flex items-center gap-2 px-4 py-3 rounded-xl border border-dashed border-slate-800 text-[12.5px] text-slate-500">
            <span className="material-symbols-outlined text-[18px]">hourglass_empty</span>No round under way.
          </div>
        )}
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
          <button data-edit onClick={onClearCooldown} className="underline text-amber-200">End the pause now</button>
        </>
      );
      break;
    case 'too_many_failures':
      text = 'Too many batches failed completely today, so it has stopped until midnight IST. Failed batches are not counted as part of the day; check the Jobs Monitor for why they failed.';
      break;
    case 'no_internet':
      text = (
        <>
          The server has no internet connection. Nothing is scraped until it is back; checking again at {time(s.offline_until)} IST.{' '}
          <button data-edit onClick={onClearCooldown} className="underline text-amber-200">Check now</button>
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
    <div className="flex gap-3 rounded-xl border border-sky-800/60 bg-sky-950 p-3.5 text-[12.5px]">
      <span className="h-8 w-8 rounded-lg bg-sky-900 text-sky-300 flex items-center justify-center shrink-0">
        <span className="material-symbols-outlined text-[18px]">{(PHASES[s.phase] || { icon: 'info' }).icon}</span>
      </span>
      <div className="min-w-0 space-y-1">
        {text && <div className="text-slate-100 font-medium leading-snug">{text}</div>}
        {s.last_event && <div className="text-slate-400">Last: {s.last_event} <span className="text-slate-500">· {dayTime(s.last_event_at)}</span></div>}
      </div>
    </div>
  );
};

const BATCH_STATUS: Record<string, { label: string; chip: string; bar: string; icon: string }> = {
  PLANNED: { label: 'Planned', chip: 'bg-slate-800 text-slate-300', bar: 'bg-slate-500', icon: 'schedule' },
  RUNNING: { label: 'Scraping', chip: 'bg-emerald-950 text-emerald-300', bar: 'bg-emerald-500', icon: 'travel_explore' },
  DONE: { label: 'Done', chip: 'bg-sky-950 text-sky-300', bar: 'bg-sky-500', icon: 'check_circle' },
  SKIPPED: { label: 'Skipped', chip: 'bg-amber-950 text-amber-300', bar: 'bg-amber-400', icon: 'block' },
};

/** The round under way: one card per batch, the running one lit up. */
const RoundTable: React.FC<{ round: AutopilotRound; current?: number }> = ({ round, current }) => (
  <div>
    <div className="flex flex-wrap items-baseline justify-between gap-2 mb-3">
      <h3 className="text-[14px] font-semibold text-slate-100 flex items-center gap-2">
        <span className="material-symbols-outlined text-[18px] text-emerald-400">map</span>
        This round: {round.state}
      </h3>
      <span className="text-[11.5px] text-slate-500">{round.batches_done} of {round.batches} batches done · planned {dayTime(round.created_at)}</span>
    </div>
    <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
      {round.plan.map(b => {
        const st = BATCH_STATUS[b.status] || BATCH_STATUS.PLANNED;
        const live = b.batch === current;
        const pctDone = (b.jobs_finished / Math.max(1, b.jobs)) * 100;
        return (
          <div key={b.batch} title={b.categories.join(', ')}
            className={`rounded-xl border p-3 transition ${live ? 'border-emerald-600 bg-emerald-950 shadow-lg ring-2 ring-emerald-500/30' : 'border-slate-800 bg-slate-950'}`}>
            <div className="flex items-center justify-between">
              <span className="h-7 w-7 rounded-lg bg-slate-800 text-slate-200 text-[12px] font-bold flex items-center justify-center">{b.batch}</span>
              <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10.5px] font-semibold ${st.chip}`}>
                {live && <span className="h-1.5 w-1.5 rounded-full bg-emerald-400 animate-pulse" />}
                <span className="material-symbols-outlined text-[13px]">{st.icon}</span>{st.label}
              </span>
            </div>
            <div className="mt-2.5 text-[13px] font-semibold text-slate-100 truncate">{b.tehsil || b.anchor || b.pincode}</div>
            <div className="text-[11px] text-slate-500 truncate">{b.district || '—'} · {b.categories.length} categories</div>
            <div className="mt-2.5 h-1.5 rounded-full bg-slate-800 overflow-hidden">
              <div className={`h-full rounded-full ${st.bar} transition-all`} style={{ width: `${pctDone}%` }} />
            </div>
            <div className="mt-1.5 flex justify-between text-[11px] tabular-nums">
              <span className="text-slate-400">{b.jobs_finished}/{b.jobs} jobs</span>
              <span className="text-emerald-400 font-semibold">{b.businesses_saved ? `+${b.businesses_saved}` : ''}</span>
            </div>
            {!!b.blocks && <div className="mt-1 text-[10.5px] text-amber-300">{b.blocks} CAPTCHA</div>}
          </div>
        );
      })}
    </div>
  </div>
);

const RecentRounds: React.FC<{ rounds: AutopilotRound[]; pending: Record<string, number> }> = ({ rounds, pending }) => {
  const left = Object.entries(pending).sort((a, b) => b[1] - a[1]);
  const max = Math.max(1, ...left.map(([, n]) => n));
  return (
    <div className="px-5 pb-5 grid gap-5 lg:grid-cols-3">
      <div className="lg:col-span-2 rounded-xl border border-slate-800 bg-slate-950 p-4">
        <div className="text-[12.5px] font-semibold text-slate-200 mb-2.5 flex items-center gap-1.5">
          <span className="material-symbols-outlined text-[17px] text-violet-400">history</span>Recent rounds
        </div>
        {rounds.length === 0 ? <div className="text-xs text-slate-500">None yet.</div> : (
          <ul className="space-y-2">
            {rounds.slice(0, 6).map(r => {
              const found = r.plan.reduce((n, b) => n + (b.businesses_saved || 0), 0);
              return (
                <li key={r.round_id} className="flex items-center gap-3 rounded-lg px-3 py-2 bg-slate-900 border border-slate-800">
                  <span className="h-8 w-8 rounded-lg bg-violet-950 text-violet-300 flex items-center justify-center shrink-0">
                    <span className="material-symbols-outlined text-[17px]">location_city</span>
                  </span>
                  <div className="min-w-0 flex-1">
                    <div className="text-[12.5px] font-semibold text-slate-100">{r.state} <span className="font-normal text-slate-500">· {r.batches_done}/{r.batches} batches</span></div>
                    <div className="text-[11px] text-slate-500 truncate" title={r.plan.map(place).join(' | ')}>{r.plan.map(b => b.tehsil || b.anchor).join(', ')}</div>
                  </div>
                  <div className="text-right shrink-0">
                    <div className="text-[12.5px] font-bold tabular-nums text-emerald-400">+{found}</div>
                    <div className="text-[10.5px] text-slate-500 whitespace-nowrap">{dayTime(r.created_at)}</div>
                  </div>
                </li>
              );
            })}
          </ul>
        )}
      </div>
      <div className="rounded-xl border border-slate-800 bg-slate-950 p-4">
        <div className="text-[12.5px] font-semibold text-slate-200 mb-2.5 flex items-center gap-1.5">
          <span className="material-symbols-outlined text-[17px] text-amber-400">pending_actions</span>Jobs left by state
        </div>
        <ul className="space-y-2.5">
          {left.map(([s, n]) => (
            <li key={s}>
              <div className="flex justify-between text-[12px]"><span className="text-slate-200">{s}</span><span className="tabular-nums font-semibold text-slate-100">{n.toLocaleString('en-IN')}</span></div>
              <div className="h-1.5 rounded-full bg-slate-800 mt-1 overflow-hidden"><div className="h-full rounded-full bg-amber-400" style={{ width: `${(n / max) * 100}%` }} /></div>
            </li>
          ))}
          {!left.length && <li className="text-xs text-slate-500">Nothing left.</li>}
        </ul>
      </div>
    </div>
  );
};

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
    <div className="mx-5 mb-5 p-4 rounded-xl border border-slate-800 bg-slate-950">
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
