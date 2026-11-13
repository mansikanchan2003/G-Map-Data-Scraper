import React, { useState, useEffect } from 'react';
import {
  fetchDiscoveryTargets,
  runTargetedDiscovery,
  runCustomDiscovery,
  type DiscoveryTargets,
  type HiringFor,
} from '../api';

/** Who the search hires for. CSP is what the autopilot runs; the other two only ever run from here. */
const HIRING: { key: HiringFor; label: string; note: string; icon: string; on: string; dot: string }[] = [
  { key: 'CSP', label: 'CSP', note: 'Customer Service Point owners', icon: 'storefront',
    on: 'bg-sky-950/60 border-sky-500 text-sky-300 ring-1 ring-sky-500/40', dot: 'bg-sky-500' },
  { key: 'DC', label: 'District Coordinator', note: 'One person to lead a district', icon: 'hub',
    on: 'bg-purple-950/60 border-purple-500 text-purple-300 ring-1 ring-purple-500/40', dot: 'bg-purple-500' },
  { key: 'STATE_HEAD', label: 'State Head', note: 'One person to lead a state', icon: 'workspace_premium',
    on: 'bg-amber-950/60 border-amber-500 text-amber-300 ring-1 ring-amber-500/40', dot: 'bg-amber-500' },
];

interface Props {
  isOpen: boolean;
  onClose: () => void;
  onStarted: () => void;
}

type Mode = 'queued' | 'custom';

/**
 * Starts a discovery run against chosen locations and categories.
 *
 * Two ways in: pick from the job queue the spreadsheets generated, or type a
 * place and categories that were never in them. The second path resolves the
 * place through Google Maps, because a job cannot be built without
 * coordinates.
 */
export const DiscoveryRunner: React.FC<Props> = ({ isOpen, onClose, onStarted }) => {
  const [mode, setMode] = useState<Mode>('queued');
  const [hiringFor, setHiringFor] = useState<HiringFor>('CSP');
  const [targets, setTargets] = useState<DiscoveryTargets | null>(null);
  const [state, setState] = useState('');
  const [locations, setLocations] = useState<string[]>([]);
  const [categories, setCategories] = useState<string[]>([]);
  const [locSearch, setLocSearch] = useState('');
  const [catSearch, setCatSearch] = useState('');

  const [customPlaces, setCustomPlaces] = useState('');
  const [customCategories, setCustomCategories] = useState('');

  const [batchSize, setBatchSize] = useState(25);
  const [delay, setDelay] = useState(5);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<string | null>(null);

  useEffect(() => {
    if (!isOpen) return;
    fetchDiscoveryTargets(state || undefined, hiringFor).then(setTargets).catch(() => setTargets(null));
  }, [isOpen, state, hiringFor]);

  if (!isOpen) return null;

  const toggle = (list: string[], set: (v: string[]) => void, value: string) =>
    set(list.includes(value) ? list.filter(v => v !== value) : [...list, value]);

  const visibleLocations = (targets?.locations || []).filter(
    l => !locSearch || l.label.toLowerCase().includes(locSearch.toLowerCase())
  );
  const visibleCategories = (targets?.categories || []).filter(
    c => !catSearch || c.value.toLowerCase().includes(catSearch.toLowerCase())
  );

  // Jobs are the cross product, capped by what is actually still pending.
  const queuedJobs = (() => {
    if (!targets) return 0;
    const locs = locations.length ? targets.locations.filter(l => locations.includes(l.value)) : targets.locations;
    const pending = locs.reduce((sum, l) => sum + l.pending, 0);
    if (!categories.length) return pending;
    const catShare = categories.length / Math.max(targets.categories.length, 1);
    return Math.round(pending * catShare);
  })();

  const parseList = (text: string) =>
    text.split(/[,\n]/).map(v => v.trim()).filter(Boolean);

  const handleRun = async () => {
    setBusy(true);
    setResult(null);
    try {
      if (mode === 'queued') {
        const res = await runTargetedDiscovery({
          anchor_names: locations.length ? locations : undefined,
          categories: categories.length ? categories : undefined,
          states: !locations.length && state ? [state] : undefined,
          batch_size: batchSize,
          delay_between_jobs_seconds: delay,
          hiring_for: hiringFor,
        });
        setResult(res.message || `Started ${res.jobs_queued} job(s).`);
        if (res.status === 'started') onStarted();
      } else {
        const places = parseList(customPlaces).map(place => ({ place }));
        const cats = parseList(customCategories);
        if (!places.length || !cats.length) {
          setResult('Enter at least one place and one category.');
          return;
        }
        const res = await runCustomDiscovery({
          places,
          categories: cats,
          batch_size: batchSize,
          delay_between_jobs_seconds: delay,
          run_now: true,
          hiring_for: hiringFor,
        });
        const failed = (res.errors || []).map((e: any) => `${e.place}: ${e.error}`).join(' · ');
        setResult(
          `${res.jobs_created} job(s) created for ${res.locations.length} place(s).` +
          (res.jobs_queued ? ` ${res.jobs_queued} started.` : '') +
          (failed ? `  Not resolved — ${failed}` : '')
        );
        if (res.status === 'started') onStarted();
      }
    } catch (err: any) {
      setResult(err.message);
    } finally {
      setBusy(false);
    }
  };

  const Chip = ({ active, onClick, children, count }: any) => (
    <button
      onClick={onClick}
      className={`px-2.5 py-1 rounded text-xs border text-left transition-colors ${
        active
          ? 'bg-sky-950/50 border-sky-700 text-sky-400 font-semibold'
          : 'bg-slate-950 border-slate-800 text-slate-400 hover:border-slate-600'
      }`}
    >
      {children}
      {count !== undefined && <span className="ml-1.5 opacity-60">{count}</span>}
    </button>
  );

  return (
    <div className="fixed inset-0 z-50 bg-slate-950/80 flex items-center justify-center p-4">
      <div className="bg-slate-900 border border-slate-800 rounded-xl w-full max-w-3xl max-h-[92vh] overflow-y-auto shadow-2xl">
        <div className="px-6 py-4 border-b border-slate-800 flex items-center justify-between">
          <div>
            <h2 className="text-lg font-semibold text-slate-100">Run discovery</h2>
            <p className="text-xs text-slate-400 mt-0.5">Choose where to search and what to look for</p>
          </div>
          <button onClick={onClose} className="text-slate-500 hover:text-slate-300">
            <span className="material-symbols-outlined">close</span>
          </button>
        </div>

        {/* Who the search hires for */}
        <div className="px-6 pt-5">
          <div className="text-[10px] uppercase tracking-wider text-slate-500 font-semibold mb-2">Hiring for</div>
          <div className="grid gap-2 sm:grid-cols-3">
            {HIRING.map(h => {
              const on = hiringFor === h.key;
              return (
                <button key={h.key} type="button"
                  onClick={() => { setHiringFor(h.key); setLocations([]); setCategories([]); }}
                  className={`flex items-center gap-3 rounded-lg border px-3 py-2.5 text-left transition-colors ${
                    on ? h.on : 'bg-slate-950 border-slate-800 text-slate-400 hover:border-slate-600'}`}>
                  <span className={`h-9 w-9 shrink-0 rounded-lg flex items-center justify-center ${on ? `${h.dot} text-white` : 'bg-slate-900 text-slate-500'}`}>
                    <span className="material-symbols-outlined text-[19px]">{h.icon}</span>
                  </span>
                  <span className="min-w-0">
                    <span className="block text-sm font-semibold leading-tight">{h.label}</span>
                    <span className="block text-[11px] opacity-75 leading-tight mt-0.5">{h.note}</span>
                  </span>
                </button>
              );
            })}
          </div>
          {hiringFor !== 'CSP' && (
            <p className="mt-2 text-[11px] text-slate-400">
              Runs only when you start it here; the autopilot never runs it. Everything it finds is labelled
              <b className="text-slate-200"> {HIRING.find(h => h.key === hiringFor)!.label}</b> in Business Data, and
              CSP campaigns never message it.
            </p>
          )}
        </div>

        {/* Mode */}
        <div className="px-6 pt-4 flex gap-2">
          <button
            onClick={() => setMode('queued')}
            className={`px-4 py-2 text-sm font-semibold rounded border ${
              mode === 'queued' ? 'bg-sky-900/40 border-sky-700 text-sky-400' : 'bg-slate-950 border-slate-800 text-slate-400'
            }`}
          >
            From the queue
          </button>
          <button
            onClick={() => setMode('custom')}
            className={`px-4 py-2 text-sm font-semibold rounded border ${
              mode === 'custom' ? 'bg-emerald-900/40 border-emerald-700 text-emerald-400' : 'bg-slate-950 border-slate-800 text-slate-400'
            }`}
          >
            Somewhere new
          </button>
        </div>

        <div className="p-6 space-y-5">
          {mode === 'queued' ? (
            <>
              <div className="flex flex-col gap-1 max-w-xs">
                <label className="text-[10px] uppercase tracking-wider text-slate-500 font-semibold">State</label>
                <select
                  value={state}
                  onChange={e => { setState(e.target.value); setLocations([]); }}
                  className="bg-slate-950 border border-slate-700 rounded px-3 py-2 text-sm text-slate-200 outline-none"
                >
                  <option value="">All states</option>
                  {(targets?.states || []).map(s => <option key={s} value={s}>{s}</option>)}
                </select>
              </div>

              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <label className="text-[10px] uppercase tracking-wider text-slate-500 font-semibold">
                    Locations {locations.length > 0 && `(${locations.length} selected)`}
                  </label>
                  <input
                    value={locSearch}
                    onChange={e => setLocSearch(e.target.value)}
                    placeholder="Filter…"
                    className="bg-slate-950 border border-slate-800 rounded px-2 py-1 text-xs text-slate-300 outline-none w-40"
                  />
                </div>
                <div className="flex flex-wrap gap-1.5 max-h-36 overflow-y-auto p-2 bg-slate-950 border border-slate-800 rounded">
                  {visibleLocations.length === 0 && <span className="text-xs text-slate-500">No locations.</span>}
                  {visibleLocations.map(l => (
                    <Chip key={l.value} active={locations.includes(l.value)} count={l.pending}
                          onClick={() => toggle(locations, setLocations, l.value)}>
                      {l.label}
                    </Chip>
                  ))}
                </div>
                <p className="text-[11px] text-slate-500">Nothing selected means every location in the chosen state.</p>
              </div>

              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <label className="text-[10px] uppercase tracking-wider text-slate-500 font-semibold">
                    Categories {categories.length > 0 && `(${categories.length} selected)`}
                  </label>
                  <input
                    value={catSearch}
                    onChange={e => setCatSearch(e.target.value)}
                    placeholder="Filter…"
                    className="bg-slate-950 border border-slate-800 rounded px-2 py-1 text-xs text-slate-300 outline-none w-40"
                  />
                </div>
                <div className="flex flex-wrap gap-1.5 max-h-36 overflow-y-auto p-2 bg-slate-950 border border-slate-800 rounded">
                  {visibleCategories.map(c => (
                    <Chip key={c.value} active={categories.includes(c.value)} count={c.pending}
                          onClick={() => toggle(categories, setCategories, c.value)}>
                      {c.value}
                    </Chip>
                  ))}
                </div>
                <p className="text-[11px] text-slate-500">Nothing selected means every category.</p>
              </div>
            </>
          ) : (
            <>
              <div className="space-y-2">
                <label className="text-[10px] uppercase tracking-wider text-slate-500 font-semibold">
                  Places — pincode, town or address
                </label>
                <textarea
                  value={customPlaces}
                  onChange={e => setCustomPlaces(e.target.value)}
                  rows={3}
                  placeholder={'Rohtak\n124001\nSector 14, Gurugram'}
                  className="w-full bg-slate-950 border border-slate-700 focus:border-emerald-500 rounded px-3 py-2 text-sm text-slate-200 outline-none"
                />
                <p className="text-[11px] text-slate-500">
                  One per line, or comma separated. Each is looked up on Google Maps to find its
                  coordinates, so give enough detail to identify it.
                </p>
              </div>

              <div className="space-y-2">
                <label className="text-[10px] uppercase tracking-wider text-slate-500 font-semibold">Categories</label>
                <textarea
                  value={customCategories}
                  onChange={e => setCustomCategories(e.target.value)}
                  rows={3}
                  placeholder={'Mobile phone shop\nXerox centre'}
                  className="w-full bg-slate-950 border border-slate-700 focus:border-emerald-500 rounded px-3 py-2 text-sm text-slate-200 outline-none"
                />
                <p className="text-[11px] text-slate-500">
                  Anything Google Maps understands as a business type. New ones are added to your
                  category list; existing ones are reused.
                </p>
              </div>
            </>
          )}

          <div className="flex items-end gap-4 pt-1">
            <div className="flex flex-col gap-1">
              <label className="text-[10px] uppercase tracking-wider text-slate-500 font-semibold">Jobs this run</label>
              <input type="number" min={1} max={500} value={batchSize}
                     onChange={e => setBatchSize(Math.max(1, Number(e.target.value) || 1))}
                     className="w-24 bg-slate-950 border border-slate-700 rounded px-3 py-2 text-sm text-slate-200 outline-none" />
            </div>
            <div className="flex flex-col gap-1">
              <label className="text-[10px] uppercase tracking-wider text-slate-500 font-semibold">Gap between jobs</label>
              <div className="flex items-center gap-2">
                <input type="number" min={0} max={60} value={delay}
                       onChange={e => setDelay(Math.max(0, Number(e.target.value) || 0))}
                       className="w-20 bg-slate-950 border border-slate-700 rounded px-3 py-2 text-sm text-slate-200 outline-none" />
                <span className="text-xs text-slate-500">seconds</span>
              </div>
            </div>
            {mode === 'queued' && (
              <div className="flex-1 text-right">
                <div className="text-xs text-slate-500">Pending in this selection</div>
                <div className="text-xl font-bold text-sky-400">{queuedJobs.toLocaleString()}</div>
              </div>
            )}
          </div>

          {result && (
            <div className="bg-slate-950 border border-slate-800 rounded px-4 py-3 text-sm text-slate-300">
              {result}
            </div>
          )}

          <p className="text-[11px] text-slate-500">
            Discovery runs in the background. Watch “Latest Orchestration Run” for progress, and
            stop it any time from Operational Controls.
          </p>
        </div>

        <div className="px-6 py-4 border-t border-slate-800 flex justify-between items-center">
          <button onClick={onClose} className="px-4 py-2 text-sm text-slate-400 hover:text-slate-200 font-semibold">
            Close
          </button>
          <button
            onClick={handleRun}
            disabled={busy}
            className="px-6 py-2.5 bg-emerald-600 hover:bg-emerald-500 disabled:opacity-40 text-white text-sm font-semibold rounded shadow transition-colors flex items-center gap-2"
          >
            <span className="material-symbols-outlined text-[18px]">travel_explore</span>
            {busy ? 'Starting…' : 'Run discovery'}
          </button>
        </div>
      </div>
    </div>
  );
};
