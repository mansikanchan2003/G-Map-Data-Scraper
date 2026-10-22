import React, { useCallback, useEffect, useState } from 'react';
import { completeFollowUpTask, fetchActionQueue, type ActionQueue as Queue, type QueueBucket, type QueueItem } from '../api/inbox';
import { formatDateTime } from '../utils/datetime';

/**
 * Every open action item across the leads, in one queue: the bot's nudges,
 * the team's and the District Coordinator's tasks, the hand-over to Eko
 * Acquisition and questions waiting for the team. Filtered by owner and
 * split into overdue (by the Dashboard alert's rules), due today and
 * upcoming. A task is marked done with how it ended: an outcome is required.
 */

const Icon: React.FC<{ name: string; className?: string }> = ({ name, className = '' }) =>
  <span className={`material-symbols-outlined ${className}`}>{name}</span>;
const chat = (phone: string) => `#inbox/${phone.replace(/\D/g, '')}`;

const OWNER_STYLE: Record<string, string> = {
  bot: 'bg-sky-950 text-sky-300',
  human: 'bg-violet-950 text-violet-300',
  dc: 'bg-amber-950 text-amber-300',
  eko_acquisition_api: 'bg-emerald-950 text-emerald-300',
};
const BUCKETS: { key: QueueBucket; label: string; icon: string; cls: string; empty: string }[] = [
  { key: 'overdue', label: 'Overdue', icon: 'running_with_errors', cls: 'text-rose-300', empty: 'Nothing overdue.' },
  { key: 'today', label: 'Today', icon: 'today', cls: 'text-amber-300', empty: 'Nothing due today.' },
  { key: 'upcoming', label: 'Upcoming', icon: 'event_upcoming', cls: 'text-sky-300', empty: 'Nothing planned ahead.' },
];

/** Marking a task done: how it ended is required, a note is optional. */
export const MarkDone: React.FC<{ id: string; outcomes: string[]; onDone: () => void }> = ({ id, outcomes, onDone }) => {
  const [open, setOpen] = useState(false);
  const [outcome, setOutcome] = useState('');
  const [note, setNote] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const save = async () => {
    setBusy(true);
    setError(null);
    try { await completeFollowUpTask(id, outcome, note.trim() || undefined); setOpen(false); onDone(); }
    catch (e: any) { setError(e.message); }
    finally { setBusy(false); }
  };

  if (!open) return (
    <button onClick={() => setOpen(true)}
      className="mt-2 inline-flex items-center gap-1 px-2.5 py-1 rounded-lg border border-emerald-700 bg-emerald-950 text-emerald-300 text-[12px] font-semibold hover:bg-emerald-900 cursor-pointer">
      <Icon name="task_alt" className="text-[15px]" />Mark done
    </button>
  );
  return (
    <div className="mt-2 rounded-lg border border-slate-800 bg-slate-900 p-2.5 space-y-2">
      <div className="text-[11.5px] text-slate-400">How did it end?</div>
      <div className="flex flex-wrap gap-1.5">
        {outcomes.map(o => (
          <button key={o} onClick={() => setOutcome(o)}
            className={`px-2.5 py-1 rounded-full border text-[11.5px] cursor-pointer ${outcome === o
              ? 'border-emerald-600 bg-emerald-950 text-emerald-300' : 'border-slate-700 text-slate-300 hover:border-slate-500'}`}>
            {o}
          </button>
        ))}
      </div>
      <input value={note} onChange={e => setNote(e.target.value)} maxLength={400} placeholder="Note (optional)"
        className="w-full h-8 px-2.5 rounded-lg border border-slate-700 bg-slate-950 text-[12.5px] text-slate-200 placeholder:text-slate-600" />
      {error && <div className="text-[11.5px] text-rose-300">{error}</div>}
      <div className="flex gap-2">
        <button onClick={save} disabled={!outcome || busy}
          className="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg border border-emerald-700 bg-emerald-950 text-emerald-300 text-[12px] font-semibold hover:bg-emerald-900 cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed">
          <Icon name="check" className="text-[15px]" />{busy ? 'Saving…' : 'Save'}
        </button>
        <button onClick={() => { setOpen(false); setOutcome(''); setNote(''); }}
          className="px-2.5 py-1 rounded-lg text-[12px] text-slate-400 hover:text-slate-200 cursor-pointer">Cancel</button>
      </div>
    </div>
  );
};

const Item: React.FC<{ i: QueueItem; outcomes: string[]; onDone: () => void }> = ({ i, outcomes, onDone }) => (
  <li className="rounded-xl border border-slate-800 bg-slate-950/60 p-3">
    <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
      <a href={chat(i.phone)} className="text-[13px] font-semibold text-sky-300 hover:underline">{i.name || i.phone}</a>
      {i.disposition_label && <span className="px-2 py-0.5 rounded-full border border-slate-700 text-[11px] text-slate-300">{i.disposition_label}</span>}
    </div>
    <div className="mt-1 text-[12.5px] text-slate-200">{i.text}</div>
    <div className="mt-1.5 flex flex-wrap items-center gap-x-2 gap-y-1 text-[11.5px] text-slate-500">
      <span className={`px-2 py-0.5 rounded-full text-[10.5px] font-semibold ${OWNER_STYLE[i.owner] || OWNER_STYLE.bot}`}>{i.owner_label}</span>
      <span>{i.source === 'ticket' ? 'Asked' : 'Due'} {formatDateTime(i.due_at)}</span>
    </div>
    {i.result && <div className="mt-1 text-[11.5px] text-slate-400">{i.result}</div>}
    {i.can_mark_done && <MarkDone id={i.id} outcomes={outcomes} onDone={onDone} />}
    {i.source === 'ticket' && (
      <a href={chat(i.phone)}
        className="mt-2 inline-flex items-center gap-1 px-2.5 py-1 rounded-lg border border-sky-800 bg-sky-950 text-sky-300 text-[12px] font-semibold hover:bg-sky-900">
        <Icon name="forum" className="text-[15px]" />Answer in the chat
      </a>
    )}
  </li>
);

export const ActionQueue: React.FC = () => {
  const [owner, setOwner] = useState('');
  const [q, setQ] = useState<Queue | null>(null);
  const [error, setError] = useState<string | null>(null);
  const load = useCallback(() => fetchActionQueue(owner || undefined).then(setQ).catch(e => setError(e.message)), [owner]);
  useEffect(() => { load(); }, [load]);

  if (error) return <div className="p-4 rounded-xl border border-rose-800/60 bg-rose-950 text-rose-300 text-sm">Could not load the action items: {error}</div>;
  if (!q) return <div className="h-40 rounded-2xl bg-slate-900 border border-slate-800 animate-pulse" />;

  const all = q.owners.reduce((n, o) => n + o.count, 0);
  const chips = [{ key: '', label: 'All', count: all }, ...q.owners];

  return (
    <section className="rounded-2xl border border-slate-800 bg-slate-900 p-5 shadow-sm select-text">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <h3 className="text-[15px] font-semibold text-slate-100 flex items-center gap-2">
          <span className="h-8 w-8 rounded-lg bg-violet-950 text-violet-300 flex items-center justify-center"><Icon name="checklist" className="text-[18px]" /></span>
          Action items
        </h3>
        <div className="flex flex-wrap gap-1.5">
          {chips.map(c => (
            <button key={c.key || 'all'} onClick={() => setOwner(c.key)}
              className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full border text-[11.5px] cursor-pointer ${owner === c.key
                ? 'border-sky-600 bg-sky-950 text-sky-200' : 'border-slate-700 bg-slate-950 text-slate-400 hover:text-slate-200'}`}>
              {c.label}<span className="tabular-nums text-slate-500">{c.count}</span>
            </button>
          ))}
        </div>
      </div>
      <p className="text-[12.5px] text-slate-400 mt-2">
        Every open step across the leads. Overdue goes by the Dashboard alert's rules: a nudge an hour past due, one waiting
        for a template a day, a team task open 2 days, a question unanswered a day. A task is marked done with how it ended.
      </p>
      <div className="grid gap-4 lg:grid-cols-3 mt-4">
        {BUCKETS.map(b => (
          <div key={b.key}>
            <h4 className={`text-[12px] uppercase tracking-wider mb-2 flex items-center gap-1.5 ${b.cls}`}>
              <Icon name={b.icon} className="text-[16px]" />{b.label}
              <span className="ml-1 px-1.5 rounded-full bg-slate-800 text-slate-300 text-[10.5px] tabular-nums">{q.counts[b.key]}</span>
            </h4>
            {q[b.key].length ? (
              <ul className="space-y-2">
                {q[b.key].map(i => <Item key={i.id} i={i} outcomes={q.outcomes} onDone={load} />)}
              </ul>
            ) : (
              <div className="py-6 flex flex-col items-center gap-1.5 text-center rounded-xl border border-dashed border-slate-800">
                <Icon name="task_alt" className="text-[24px] text-slate-600" />
                <span className="text-[12.5px] text-slate-500">{b.empty}</span>
              </div>
            )}
          </div>
        ))}
      </div>
    </section>
  );
};
