import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { fetchJourney, fetchJourneys, type Journey, type JourneyRow } from '../api/inbox';
import { formatDateTime } from '../utils/datetime';

/**
 * Every lead's journey, laid out so it can be read at a glance (the user,
 * 2026-10-22): where each lead is now, when they started, the last thing
 * that happened and the last thing we did. Opening a lead shows its steps as
 * a plain table: when, what they did, what we did. Opened from the
 * Applications tab, at #applications/journey.
 */

const Icon: React.FC<{ name: string; className?: string }> = ({ name, className = '' }) =>
  <span className={`material-symbols-outlined ${className}`} aria-hidden="true">{name}</span>;
const initials = (text: string) => text.replace(/^\+/, '').split(/\s+/).filter(Boolean).slice(0, 2).map(w => w[0]).join('').toUpperCase() || '?';
const csvCell = (v: unknown) => `"${String(v ?? '').replace(/"/g, '""')}"`;
const daysSince = (iso: string | null) => iso ? Math.max(0, Math.floor((Date.now() - new Date(iso).getTime()) / 86400000)) : null;
const who = (by: string) => by.includes('@') ? by.split('@')[0].replace(/[._]/g, ' ').replace(/\b\w/g, c => c.toUpperCase()) : by;

type Filter = 'all' | 'in_progress' | 'handed_over' | 'closed';
const OUTCOME: Record<string, { label: string; icon: string; chip: string; tint: string; ring: string; hint: string }> = {
  in_progress: { label: 'In progress', icon: 'directions_run', chip: 'bg-sky-950 border-sky-800/60 text-sky-300',
    tint: 'bg-sky-950 text-sky-300', ring: 'ring-sky-500', hint: 'Still going through the steps' },
  handed_over: { label: 'Handed to Eko Acquisition', icon: 'handshake', chip: 'bg-violet-950 border-violet-800/60 text-violet-300',
    tint: 'bg-violet-950 text-violet-300', ring: 'ring-violet-500', hint: 'Documents in: Physical visit required' },
  closed: { label: 'Ended', icon: 'block', chip: 'bg-rose-950 border-rose-800/60 text-rose-300',
    tint: 'bg-rose-950 text-rose-300', ring: 'ring-rose-500', hint: 'Not interested, not eligible, outside our area…' },
};

/** Progress as dashes, like the Applications list: one per step, filled as far as they got. */
const Dashes: React.FC<{ done: number; total: number; outcome: string }> = ({ done, total, outcome }) => (
  <div className="flex gap-1" aria-label={`${done} of ${total} steps`}>
    {Array.from({ length: total }, (_, i) => (
      <span key={i} className={`h-1.5 w-5 rounded-full ${i < done
        ? (outcome === 'handed_over' ? 'bg-violet-500' : outcome === 'closed' && i === done - 1 ? 'bg-rose-500' : 'bg-sky-500')
        : 'bg-slate-800'}`} />
    ))}
  </div>
);

/** One lead's steps as a plain table: when, what they did, what we did. */
const Steps: React.FC<{ phone: string }> = ({ phone }) => {
  const [j, setJ] = useState<Journey | null>(null);
  const [all, setAll] = useState(false);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => { fetchJourney(phone).then(setJ).catch(e => setError(e.message)); }, [phone]);
  if (error) return <div className="text-sm text-rose-300">Could not load the steps: {error}</div>;
  if (!j) return <div className="h-24 rounded-lg bg-slate-900 animate-pulse" />;
  const steps = all ? j.steps : j.steps.filter(s => s.kind === 'stage');
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-3">
        {/* The stages as a strip of chips: reached ones filled, with their dates. */}
        {j.funnel.map((f, i) => (
          <span key={f.key} title={f.at ? formatDateTime(f.at) : 'Not yet'}
            className={`inline-flex items-center gap-1 px-2 py-1 rounded-md text-[11.5px] border ${i <= j.furthest
              ? 'bg-emerald-950 border-emerald-800/60 text-emerald-300' : 'border-slate-800 text-slate-500'}`}>
            <Icon name={i <= j.furthest ? 'check_circle' : 'radio_button_unchecked'} className="text-[14px]" />{f.label}
          </span>
        ))}
      </div>
      <div className="overflow-x-auto rounded-lg border border-slate-800">
        <table className="w-full text-[13px]">
          <thead>
            <tr className="bg-slate-900 text-[11px] uppercase tracking-wider text-slate-500 text-left">
              <th className="px-3 py-2 w-[170px] font-semibold">When</th>
              <th className="px-3 py-2 font-semibold">What they did</th>
              <th className="px-3 py-2 font-semibold">What we did</th>
            </tr>
          </thead>
          <tbody>
            {steps.map((s, i) => (
              <tr key={i} className={`border-t border-slate-800 align-top ${s.kind === 'stage' ? '' : 'text-slate-400'}`}>
                <td className="px-3 py-2 whitespace-nowrap tabular-nums text-slate-400">{formatDateTime(s.at || s.action_at || '')}</td>
                <td className={`px-3 py-2 ${s.kind === 'stage' ? 'font-semibold text-slate-100' : ''}`}>{s.what || '—'}</td>
                <td className="px-3 py-2">
                  {s.action || '—'}
                  {s.by && s.by !== 'bot' && s.kind === 'stage' && <span className="text-slate-500"> · {who(s.by)}</span>}
                  {s.detail && <div className="text-[12px] text-slate-500 mt-0.5">{s.detail}</div>}
                </td>
              </tr>
            ))}
            {!steps.length && <tr><td colSpan={3} className="px-3 py-4 text-center text-slate-500">Nothing yet.</td></tr>}
          </tbody>
        </table>
      </div>
      <button onClick={() => setAll(!all)} className="text-[12.5px] text-sky-300 hover:underline cursor-pointer">
        {all ? 'Show only the main steps' : `Show every message and action (${j.steps.length})`}
      </button>
    </div>
  );
};

export const LeadJourneyView: React.FC<{ onBack: () => void }> = ({ onBack }) => {
  const [rows, setRows] = useState<JourneyRow[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState<Filter>('all');
  const [where, setWhere] = useState<string | null>(null);
  const [q, setQ] = useState('');
  const [open, setOpen] = useState<string | null>(null);

  const load = useCallback(() => {
    setLoading(true);
    fetchJourneys().then(r => { setRows(r); setError(null); }).catch(e => setError(e.message)).finally(() => setLoading(false));
  }, []);
  useEffect(() => { load(); }, [load]);

  const counts = useMemo(() => (rows || []).reduce<Record<string, number>>((a, r) => ({ ...a, [r.outcome]: (a[r.outcome] || 0) + 1 }), {}), [rows]);
  // Where the leads are now, most first: the plain answer to "where do people stop?".
  const byWhere = useMemo(() => {
    const m = new Map<string, number>();
    (rows || []).forEach(r => m.set(r.where, (m.get(r.where) || 0) + 1));
    return [...m.entries()].sort((a, b) => b[1] - a[1]);
  }, [rows]);
  const shown = (rows || []).filter(r =>
    (filter === 'all' || r.outcome === filter) && (!where || r.where === where) &&
    (!q || `${r.name || ''} ${r.phone} ${r.place || ''} ${r.pincode || ''}`.toLowerCase().includes(q.toLowerCase())));
  const top = Math.max(1, ...byWhere.map(([, n]) => n));

  const download = () => {
    const head = ['Name', 'Phone', 'Place', 'PIN', 'Outcome', 'Where now', 'Steps done', 'Started', 'Last thing that happened', 'When', 'Last thing we did', 'When'];
    const lines = shown.map(r => [r.name, r.phone, r.place, r.pincode, OUTCOME[r.outcome]?.label, r.where, `${r.steps_done}/${r.steps_total}`,
      r.started_at ? formatDateTime(r.started_at) : '', r.last?.what, r.last?.at ? formatDateTime(r.last.at) : '',
      r.our_last?.text, r.our_last?.at ? formatDateTime(r.our_last.at) : ''].map(csvCell).join(','));
    const blob = new Blob(['﻿' + [head.map(csvCell).join(','), ...lines].join('\n')], { type: 'text/csv;charset=utf-8' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = `lead-journeys-${new Date().toISOString().slice(0, 10)}.csv`;
    a.click();
    URL.revokeObjectURL(a.href);
  };

  return (
    <div className="flex-1 overflow-y-auto bg-slate-950 text-slate-100">
      <div className="px-6 pt-6 pb-2 max-w-[1500px] mx-auto flex flex-wrap items-end justify-between gap-4">
        <div>
          <button onClick={onBack} className="text-[12.5px] text-sky-300 hover:underline flex items-center gap-1 mb-1 cursor-pointer">
            <Icon name="arrow_back" className="text-[16px]" />Applications
          </button>
          <h1 className="text-2xl font-semibold tracking-tight text-slate-100">Lead Journey</h1>
          <p className="text-sm text-slate-500 mt-1">Every lead from a campaign: where they are now, what happened last, and what we did. Open a lead for its steps, with dates.</p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <button onClick={download} disabled={!shown.length}
            className="h-9 px-3.5 rounded-lg border border-slate-800 bg-slate-900 hover:bg-slate-800 text-sm font-medium text-slate-300 flex items-center gap-1.5 shadow-sm disabled:opacity-50">
            <Icon name="download" className="text-[18px]" />Download CSV
          </button>
          <button onClick={load} className="h-9 px-3.5 rounded-lg border border-slate-800 bg-slate-900 hover:bg-slate-800 text-sm font-medium text-slate-300 flex items-center gap-1.5 shadow-sm">
            <Icon name="sync" className={`text-[18px] ${loading ? 'animate-spin' : ''}`} />Refresh
          </button>
        </div>
      </div>

      <div className="px-6 py-4 max-w-[1500px] mx-auto space-y-5">
        {error && <div className="p-3 rounded-lg border border-rose-800/60 bg-rose-950 text-rose-300 text-sm">{error}</div>}

        {/* The totals; each one filters the list. */}
        <div className="grid grid-cols-2 xl:grid-cols-4 gap-3">
          <button onClick={() => setFilter('all')}
            className={`text-left p-4 rounded-xl border bg-slate-900 shadow-sm transition-all ${filter === 'all' ? 'border-transparent ring-2 ring-slate-400' : 'border-slate-800 hover:border-slate-700 hover:-translate-y-0.5'}`}>
            <div className="flex items-center justify-between">
              <span className="h-9 w-9 rounded-lg flex items-center justify-center bg-slate-800 text-slate-300"><Icon name="groups" className="text-[20px]" /></span>
              <span className="text-2xl font-bold text-slate-100 tabular-nums">{rows ? rows.length : '—'}</span>
            </div>
            <div className="text-sm font-semibold text-slate-100 mt-3">All leads</div>
            <div className="text-[11.5px] text-slate-500 mt-0.5">Everyone who answered a campaign</div>
          </button>
          {(['in_progress', 'handed_over', 'closed'] as const).map(k => {
            const o = OUTCOME[k];
            return (
              <button key={k} onClick={() => setFilter(filter === k ? 'all' : k)}
                className={`text-left p-4 rounded-xl border bg-slate-900 shadow-sm transition-all ${filter === k ? `border-transparent ring-2 ${o.ring}` : 'border-slate-800 hover:border-slate-700 hover:-translate-y-0.5'}`}>
                <div className="flex items-center justify-between">
                  <span className={`h-9 w-9 rounded-lg flex items-center justify-center ${o.tint}`}><Icon name={o.icon} className="text-[20px]" /></span>
                  <span className="text-2xl font-bold text-slate-100 tabular-nums">{rows ? counts[k] || 0 : '—'}</span>
                </div>
                <div className="text-sm font-semibold text-slate-100 mt-3">{o.label}</div>
                <div className="text-[11.5px] text-slate-500 mt-0.5">{o.hint}</div>
              </button>
            );
          })}
        </div>

        {/* Where everyone is now: one bar per place in the journey; a bar filters the list. */}
        {byWhere.length > 0 && (
          <section className="rounded-xl border border-slate-800 bg-slate-900 shadow-sm p-5">
            <div className="flex items-center justify-between mb-3">
              <h2 className="text-sm font-semibold text-slate-100 flex items-center gap-2"><Icon name="insights" className="text-[18px] text-sky-400" />Where leads are now</h2>
              {where && <button onClick={() => setWhere(null)} className="text-[12px] text-sky-300 hover:underline cursor-pointer">Show all</button>}
            </div>
            <div className="grid gap-x-8 gap-y-2 md:grid-cols-2">
              {byWhere.map(([label, n]) => (
                <button key={label} onClick={() => setWhere(where === label ? null : label)}
                  className={`grid grid-cols-[minmax(140px,1fr)_2fr_36px] items-center gap-3 text-left text-[13px] rounded-md px-1.5 py-1 cursor-pointer ${where === label ? 'bg-slate-800' : 'hover:bg-slate-800/60'}`}>
                  <span className="text-slate-300 truncate">{label}</span>
                  <span className="h-2.5 rounded-full bg-slate-800 overflow-hidden">
                    <span className={`block h-full rounded-full ${label === OUTCOME.handed_over.label ? 'bg-violet-500' : /not|cannot|outside/i.test(label) ? 'bg-rose-500' : 'bg-sky-500'}`}
                      style={{ width: `${(n / top) * 100}%` }} />
                  </span>
                  <span className="text-right font-semibold tabular-nums text-slate-100">{n}</span>
                </button>
              ))}
            </div>
          </section>
        )}

        <section className="rounded-xl border border-slate-800 bg-slate-900 shadow-sm overflow-hidden">
          <div className="flex flex-wrap items-center gap-3 px-4 py-3 border-b border-slate-800">
            <div className="relative flex-1 min-w-[220px] max-w-md">
              <Icon name="search" className="absolute left-2.5 top-2 text-[18px] text-slate-500" />
              <input value={q} onChange={e => setQ(e.target.value)} placeholder="Search name, phone, place or PIN"
                className="w-full h-9 pl-9 pr-3 rounded-lg border border-slate-800 bg-slate-950 text-sm text-slate-200 outline-none focus:border-sky-600" />
            </div>
            <span className="text-[12.5px] text-slate-500">{shown.length} {shown.length === 1 ? 'lead' : 'leads'}</span>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-[13px] min-w-[1050px]">
              <thead>
                <tr className="bg-slate-950/60 text-[11px] uppercase tracking-wider text-slate-500 text-left">
                  <th className="px-4 py-2.5 font-semibold">Lead</th>
                  <th className="px-4 py-2.5 font-semibold">Where they are now</th>
                  <th className="px-4 py-2.5 font-semibold">Last thing that happened</th>
                  <th className="px-4 py-2.5 font-semibold">Last thing we did</th>
                  <th className="px-4 py-2.5 font-semibold">Outcome</th>
                  <th className="px-2 py-2.5" />
                </tr>
              </thead>
              <tbody>
                {shown.map(r => {
                  const o = OUTCOME[r.outcome] || OUTCOME.in_progress;
                  const isOpen = open === r.phone;
                  const days = daysSince(r.started_at);
                  return (
                    <React.Fragment key={r.phone}>
                      <tr onClick={() => setOpen(isOpen ? null : r.phone)}
                        className={`border-t border-slate-800 align-top cursor-pointer ${isOpen ? 'bg-slate-800/40' : 'hover:bg-slate-800/30'}`}>
                        <td className="px-4 py-3">
                          <div className="flex items-start gap-3">
                            <span className="h-9 w-9 rounded-full bg-slate-800 text-slate-200 text-[12px] font-bold flex items-center justify-center shrink-0">{initials(r.name || r.phone)}</span>
                            <div className="min-w-0">
                              <div className="font-semibold text-slate-100 truncate max-w-[220px]">{r.name || r.phone}</div>
                              <div className="text-[12px] text-slate-400 tabular-nums">{r.phone}</div>
                              {(r.place || r.pincode) && <div className="text-[11.5px] text-slate-500">{[r.pincode, r.place].filter(Boolean).join(' · ')}</div>}
                            </div>
                          </div>
                        </td>
                        <td className="px-4 py-3">
                          <div className="font-semibold text-slate-100">{r.where}</div>
                          <div className="mt-1.5"><Dashes done={r.steps_done} total={r.steps_total} outcome={r.outcome} /></div>
                          <div className="text-[11.5px] text-slate-500 mt-1">
                            {r.started_at ? <>Interested {formatDateTime(r.started_at)}{days !== null && <> · {days === 0 ? 'today' : `${days} day${days === 1 ? '' : 's'} ago`}</>}</> : "Hasn't tapped Interested yet"}
                          </div>
                        </td>
                        <td className="px-4 py-3 max-w-[300px]">
                          <div className="text-slate-200">{r.last?.what || '—'}</div>
                          {r.last?.at && <div className="text-[11.5px] text-slate-500 mt-0.5">{formatDateTime(r.last.at)}</div>}
                        </td>
                        <td className="px-4 py-3 max-w-[300px]">
                          <div className="text-slate-200">{r.our_last?.text || '—'}</div>
                          {r.our_last?.at && <div className="text-[11.5px] text-slate-500 mt-0.5">{formatDateTime(r.our_last.at)}</div>}
                          {r.next && <div className="text-[11.5px] text-sky-300 mt-1 flex items-start gap-1"><Icon name="event_upcoming" className="text-[14px]" />{r.next.text}</div>}
                        </td>
                        <td className="px-4 py-3">
                          <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full border text-[11px] font-semibold whitespace-nowrap ${o.chip}`}>
                            <Icon name={o.icon} className="text-[13px]" />{o.label}
                          </span>
                          <div className="text-[11.5px] text-slate-500 mt-1">Now: {r.now.label}</div>
                        </td>
                        <td className="px-2 py-3">
                          <span className="h-8 w-8 rounded-full border border-slate-700 flex items-center justify-center text-slate-400">
                            <Icon name={isOpen ? 'expand_less' : 'expand_more'} className="text-[18px]" />
                          </span>
                        </td>
                      </tr>
                      {isOpen && (
                        <tr className="bg-slate-950/40">
                          <td colSpan={6} className="px-4 py-4">
                            <div className="flex justify-end mb-2">
                              <a href={`#inbox/${r.phone.replace(/\D/g, '')}`} className="inline-flex items-center gap-1 text-[12.5px] text-sky-300 hover:underline">
                                <Icon name="chat" className="text-[15px]" />Open the chat
                              </a>
                            </div>
                            <Steps phone={r.phone} />
                          </td>
                        </tr>
                      )}
                    </React.Fragment>
                  );
                })}
                {rows && !shown.length && (
                  <tr><td colSpan={6} className="px-4 py-10 text-center text-slate-500">No leads here.</td></tr>
                )}
              </tbody>
            </table>
          </div>
        </section>
      </div>
    </div>
  );
};
