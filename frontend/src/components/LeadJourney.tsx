import React, { useEffect, useMemo, useState } from 'react';
import { fetchJourney, fetchJourneys, type Journey, type JourneyRow, type JourneyStep } from '../api/inbox';
import { formatDateTime } from '../utils/datetime';

/**
 * A lead's journey, step by step with dates: what they did and what we did
 * next, from the campaign to the documents and the hand-over to Eko
 * Acquisition, or to the point it ended (not interested, outside our area,
 * cannot invest...). The steps are read from the chat itself, so older
 * leads have theirs too.
 */

const Icon: React.FC<{ name: string; className?: string }> = ({ name, className = '' }) =>
  <span className={`material-symbols-outlined ${className}`}>{name}</span>;
const who = (by: string) => by.includes('@') ? by.split('@')[0].replace(/[._]/g, ' ').replace(/\b\w/g, c => c.toUpperCase()) : by;

const TONE: Record<string, { dot: string; text: string }> = {
  positive: { dot: 'bg-emerald-500', text: 'text-emerald-300' },
  negative: { dot: 'bg-rose-500', text: 'text-rose-300' },
  warning: { dot: 'bg-amber-400', text: 'text-amber-300' },
  handover: { dot: 'bg-violet-500', text: 'text-violet-300' },
  planned: { dot: 'bg-sky-500', text: 'text-sky-300' },
  neutral: { dot: 'bg-slate-500', text: 'text-slate-300' },
};
const OUTCOME: Record<string, { label: string; cls: string }> = {
  handed_over: { label: 'Handed to Eko Acquisition', cls: 'border-violet-800/60 bg-violet-950 text-violet-300' },
  closed: { label: 'Ended', cls: 'border-rose-800/60 bg-rose-950 text-rose-300' },
  in_progress: { label: 'In progress', cls: 'border-sky-800/60 bg-sky-950 text-sky-300' },
};

/** The stages as a row of segments, filled as far as the lead got. */
export const FunnelBar: React.FC<{ funnel: Journey['funnel']; furthest: number; outcome: string }> = ({ funnel, furthest, outcome }) => (
  <div className="flex gap-0.5" aria-label={`Reached ${funnel[furthest]?.label || 'nothing yet'}`}>
    {funnel.map((f, i) => (
      <span key={f.key} title={`${f.label}${f.at ? ` · ${formatDateTime(f.at)}` : ''}`}
        className={`h-1.5 flex-1 rounded-full ${i <= furthest
          ? (outcome === 'handed_over' ? 'bg-violet-500' : outcome === 'closed' && i === furthest ? 'bg-rose-500' : 'bg-emerald-500')
          : 'bg-slate-800'}`} />
    ))}
  </div>
);

const Step: React.FC<{ s: JourneyStep; last: boolean }> = ({ s, last }) => {
  const tone = TONE[s.tone] || TONE.neutral;
  const stage = s.kind === 'stage';
  return (
    <li className="relative pl-6 pb-3">
      {!last && <span className="absolute left-[5px] top-3 bottom-0 w-px bg-slate-800" />}
      <span className={`absolute left-0 top-1.5 rounded-full ${tone.dot} ${stage ? 'h-[11px] w-[11px] ring-2 ring-slate-900' : 'h-[7px] w-[7px] left-[2px] top-2 opacity-70'}`} />
      {s.what && (
        <div className={stage ? `text-[13px] font-semibold ${tone.text}` : 'text-[12.5px] text-slate-300'}>
          {s.what}
          {s.at && <span className="ml-1.5 font-normal text-[11px] text-slate-500">{formatDateTime(s.at)}</span>}
        </div>
      )}
      {s.action && (
        <div className="mt-0.5 text-[12px] text-slate-400 flex gap-1">
          <Icon name="subdirectory_arrow_right" className="text-[14px] text-slate-600 mt-px" />
          <span>
            {s.action}
            {s.action_at && (!s.what || s.action_at !== s.at) && <span className="ml-1.5 text-[11px] text-slate-500">{formatDateTime(s.action_at)}</span>}
            {s.by && s.by !== 'bot' && s.kind === 'stage' && <span className="ml-1.5 text-[11px] text-slate-500">· {who(s.by)}</span>}
          </span>
        </div>
      )}
      {s.detail && <div className="mt-1 ml-5 text-[11.5px] text-slate-400 italic">{s.detail}</div>}
    </li>
  );
};

/** One lead's journey; `version` refetches it when the chat changes. */
export const JourneyTimeline: React.FC<{ phone: string; version?: string; stagesOnly?: boolean }> = ({ phone, version, stagesOnly: initial = false }) => {
  const [j, setJ] = useState<Journey | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [stagesOnly, setStagesOnly] = useState(initial);
  useEffect(() => {
    let live = true;
    fetchJourney(phone).then(r => { if (live) setJ(r); }).catch(e => { if (live) setError(e.message); });
    return () => { live = false; };
  }, [phone, version]);
  if (error) return <div className="text-[12px] text-rose-300">Could not load the journey: {error}</div>;
  if (!j) return <div className="h-24 rounded-lg bg-slate-900 animate-pulse" />;
  const steps = stagesOnly ? j.steps.filter(s => s.kind === 'stage') : j.steps;
  const outcome = OUTCOME[j.outcome] || OUTCOME.in_progress;
  return (
    <div className="space-y-3 select-text">
      <div className="flex flex-wrap items-center gap-2">
        <span className={`px-2 py-0.5 rounded-full border text-[11px] font-semibold ${outcome.cls}`}>{outcome.label}</span>
        <span className="text-[11.5px] text-slate-500">Now: {j.now.label}</span>
        <span className="flex-1" />
        <button onClick={() => setStagesOnly(!stagesOnly)} className="text-[11.5px] text-sky-300 hover:underline cursor-pointer">
          {stagesOnly ? 'Show everything' : 'Only the steps'}
        </button>
      </div>
      <FunnelBar funnel={j.funnel} furthest={j.furthest} outcome={j.outcome} />
      {steps.length ? (
        <ol>{steps.map((s, i) => <Step key={i} s={s} last={i === steps.length - 1} />)}</ol>
      ) : <div className="text-[12.5px] text-slate-500">Nothing has happened in this chat yet.</div>}
    </div>
  );
};

/** Every campaign lead's journey in short, on the Dispositions tab; a row opens its timeline. */
export const LeadJourneysPanel: React.FC = () => {
  const [rows, setRows] = useState<JourneyRow[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [open, setOpen] = useState<string | null>(null);
  const [filter, setFilter] = useState<'all' | 'in_progress' | 'handed_over' | 'closed'>('all');
  useEffect(() => { fetchJourneys().then(setRows).catch(e => setError(e.message)); }, []);
  const counts = useMemo(() => (rows || []).reduce<Record<string, number>>((a, r) => ({ ...a, [r.outcome]: (a[r.outcome] || 0) + 1 }), {}), [rows]);
  if (error) return <div className="p-4 rounded-xl border border-rose-800/60 bg-rose-950 text-rose-300 text-sm">Could not load the journeys: {error}</div>;
  if (!rows) return <div className="h-40 rounded-2xl bg-slate-900 border border-slate-800 animate-pulse" />;
  const shown = rows.filter(r => filter === 'all' || r.outcome === filter);
  const stages = rows[0]?.funnel.map(f => f.label) || [];

  return (
    <section className="rounded-2xl border border-slate-800 bg-slate-900 p-5 shadow-sm select-text">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <h3 className="text-[15px] font-semibold text-slate-100 flex items-center gap-2">
          <span className="h-8 w-8 rounded-lg bg-violet-950 text-violet-300 flex items-center justify-center"><Icon name="route" className="text-[18px]" /></span>
          Lead journeys
        </h3>
        <div className="flex flex-wrap gap-1">
          {([['all', 'All', rows.length], ['in_progress', 'In progress', counts.in_progress || 0],
             ['handed_over', 'Handed to Eko Acquisition', counts.handed_over || 0], ['closed', 'Ended', counts.closed || 0]] as const).map(([k, label, n]) => (
            <button key={k} onClick={() => setFilter(k)}
              className={`px-2.5 py-1 rounded-full border text-[11.5px] cursor-pointer ${filter === k
                ? 'border-sky-600 bg-sky-950 text-sky-200' : 'border-slate-800 text-slate-400 hover:text-slate-200'}`}>
              {label} <b className="tabular-nums">{n}</b>
            </button>
          ))}
        </div>
      </div>
      <p className="text-[12.5px] text-slate-400 mt-2">
        Each lead from a campaign, step by step: when they became interested and what we did next, each step after that,
        up to their documents and "Physical visit required", where Eko Acquisition takes over. Open a lead to see every
        date and action. Stages: {stages.join(' → ')}.
      </p>
      <ul className="mt-4 space-y-2">
        {shown.map(r => {
          const isOpen = open === r.phone;
          const outcome = OUTCOME[r.outcome] || OUTCOME.in_progress;
          return (
            <li key={r.phone} className="rounded-xl border border-slate-800 bg-slate-950/60">
              <button onClick={() => setOpen(isOpen ? null : r.phone)} className="w-full text-left px-3.5 py-2.5 cursor-pointer">
                <div className="flex flex-wrap items-center gap-x-2.5 gap-y-1">
                  <span className="text-[13px] font-semibold text-slate-100">{r.name || r.phone}</span>
                  <span className={`px-2 py-0.5 rounded-full border text-[10.5px] font-semibold ${outcome.cls}`}>{outcome.label}</span>
                  <span className="text-[11.5px] text-slate-500 truncate">{r.last ? `${r.last.what}` : ''}{r.last?.at ? ` · ${formatDateTime(r.last.at)}` : ''}</span>
                  <span className="flex-1" />
                  <Icon name={isOpen ? 'expand_less' : 'expand_more'} className="text-[18px] text-slate-500" />
                </div>
                <div className="mt-2"><FunnelBar funnel={r.funnel} furthest={r.furthest} outcome={r.outcome} /></div>
              </button>
              {isOpen && (
                <div className="px-3.5 pb-3.5 pt-1 border-t border-slate-800">
                  <div className="flex justify-end mb-2">
                    <a href={`#inbox/${r.phone.replace(/\D/g, '')}`} className="text-[11.5px] text-sky-300 hover:underline">Open the chat</a>
                  </div>
                  <JourneyTimeline phone={r.phone} />
                </div>
              )}
            </li>
          );
        })}
        {!shown.length && <li className="py-6 text-center text-[12.5px] text-slate-500 rounded-xl border border-dashed border-slate-800">No leads here yet.</li>}
      </ul>
    </section>
  );
};
