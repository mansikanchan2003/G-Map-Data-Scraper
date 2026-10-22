import React, { useCallback, useEffect, useState } from 'react';
import { fetchFollowUpBoard, type FollowUpBoard, type FollowUpItem } from '../api/inbox';
import { MarkDone } from './ActionQueue';
import { formatDateTime } from '../utils/datetime';

/**
 * What the dispositions set in motion: the nudges coming up (standing in for
 * the calls the sheet asks for), the tasks for the team and the District
 * Coordinator, and how the latest nudges went. Shows which ways of reaching
 * people are on, so it is plain that calls become nudges for now.
 */

const Icon: React.FC<{ name: string; className?: string }> = ({ name, className = '' }) =>
  <span className={`material-symbols-outlined ${className}`}>{name}</span>;
const chat = (phone: string) => `#inbox/${phone.replace(/\D/g, '')}`;
const nice = (key: string) => key.replace(/_/g, ' ').replace(/^\w/, c => c.toUpperCase());

const OWNER: Record<string, { label: string; cls: string }> = {
  bot: { label: 'Bot', cls: 'bg-sky-950 text-sky-300' },
  human: { label: 'Team', cls: 'bg-violet-950 text-violet-300' },
  dc: { label: 'District Coordinator', cls: 'bg-amber-950 text-amber-300' },
};
const STATUS: Record<string, { label: string; cls: string; icon: string }> = {
  scheduled: { label: 'Scheduled', cls: 'text-sky-300', icon: 'schedule' },
  waiting: { label: 'Waiting', cls: 'text-amber-300', icon: 'hourglass_top' },
  sent: { label: 'Sent', cls: 'text-sky-300', icon: 'send' },
  replied: { label: 'Replied', cls: 'text-emerald-300', icon: 'mark_chat_read' },
  no_answer: { label: 'No answer (RNR)', cls: 'text-amber-300', icon: 'phone_missed' },
  failed: { label: 'Not delivered', cls: 'text-rose-300', icon: 'error' },
  cancelled: { label: 'Not needed', cls: 'text-slate-500', icon: 'do_not_disturb_on' },
  done: { label: 'Done', cls: 'text-emerald-300', icon: 'task_alt' },
};
const LANG: Record<string, string> = {
  en: 'English', hi: 'Hindi', hinglish: 'Hinglish', gu: 'Gujarati', pa: 'Punjabi', mr: 'Marathi', bn: 'Bengali',
  ta: 'Tamil', te: 'Telugu', kn: 'Kannada', ml: 'Malayalam', or: 'Odia',
};

const Row: React.FC<{ f: FollowUpItem; when: string; children?: React.ReactNode }> = ({ f, when, children }) => {
  const st = STATUS[f.status] || STATUS.scheduled;
  const owner = OWNER[f.owner] || OWNER.bot;
  return (
    <li className="rounded-xl border border-slate-800 bg-slate-950/60 p-3">
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
        <a href={chat(f.phone)} className="text-[13px] font-semibold text-sky-300 hover:underline">{f.name || f.phone}</a>
        {f.disposition_label && <span className="px-2 py-0.5 rounded-full border border-slate-700 text-[11px] text-slate-300">{f.disposition_label}</span>}
        <span className={`px-2 py-0.5 rounded-full text-[10.5px] font-semibold ${owner.cls}`}>{owner.label}</span>
        <span className="flex-1" />
        <span className={`inline-flex items-center gap-1 text-[11.5px] ${st.cls}`}><Icon name={st.icon} className="text-[14px]" />{st.label}</span>
      </div>
      <div className="mt-1 text-[12.5px] text-slate-300">
        {f.task || (f.wants === 'eko_acquisition_api'
          ? <>Hand-over to Eko Acquisition <span className="text-slate-500">(their API)</span></>
          : <>{nice(f.purpose)} nudge{f.wants === 'whatsapp_call' && <span className="text-slate-500"> (for a call)</span>}</>)}
      </div>
      <div className="mt-0.5 text-[11.5px] text-slate-500 flex flex-wrap gap-x-3">
        <span>{when}</span>
        {f.language && <span>in {LANG[f.language] || f.language}</span>}
        {f.attempt > 1 && <span>attempt {f.attempt}</span>}
      </div>
      {f.note && f.status !== 'scheduled' && <div className="mt-1 text-[11.5px] text-slate-400">{f.note}</div>}
      {children}
    </li>
  );
};

export const FollowUpsPanel: React.FC<{ days?: number }> = ({ days = 7 }) => {
  const [b, setB] = useState<FollowUpBoard | null>(null);
  const [error, setError] = useState<string | null>(null);
  const load = useCallback(() => fetchFollowUpBoard(days).then(setB).catch(e => setError(e.message)), [days]);
  useEffect(() => { load(); }, [load]);

  if (error) return <div className="p-4 rounded-xl border border-rose-800/60 bg-rose-950 text-rose-300 text-sm">Could not load the follow-ups: {error}</div>;
  if (!b) return <div className="h-40 rounded-2xl bg-slate-900 border border-slate-800 animate-pulse" />;

  const tiles: [string, string, number, string][] = [
    ['schedule', 'Coming up', b.counts.scheduled, 'text-sky-300'],
    ['hourglass_top', 'Waiting for a template', b.counts.waiting, 'text-amber-300'],
    ['assignment', 'Tasks open', b.counts.tasks, 'text-violet-300'],
    ['mark_chat_read', 'Replied', b.counts.replied, 'text-emerald-300'],
    ['phone_missed', 'No answer', b.counts.no_answer, 'text-amber-300'],
    ['error', 'Not delivered', b.counts.failed, 'text-rose-300'],
  ];

  return (
    <section className="rounded-2xl border border-slate-800 bg-slate-900 p-5 shadow-sm select-text">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <h3 className="text-[15px] font-semibold text-slate-100 flex items-center gap-2">
          <span className="h-8 w-8 rounded-lg bg-sky-950 text-sky-300 flex items-center justify-center"><Icon name="notifications_active" className="text-[18px]" /></span>
          Follow-ups
        </h3>
        <div className="flex flex-wrap gap-2">
          {b.channels.map(c => (
            <span key={c.name} title={c.note}
              className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full border text-[11.5px] ${c.on
                ? 'border-emerald-800/60 bg-emerald-950 text-emerald-300' : 'border-slate-700 bg-slate-950 text-slate-400'}`}>
              <Icon name={c.name === 'whatsapp_call' ? 'call' : c.name === 'eko_acquisition_api' ? 'handshake' : 'chat'} className="text-[14px]" />
              {c.label}: {c.on ? 'on' : c.name === 'eko_acquisition_api' ? 'not set up yet' : 'coming soon'}
            </span>
          ))}
        </div>
      </div>
      <p className="text-[12.5px] text-slate-400 mt-2">
        Each disposition does what the sheet says. Where it asks for a call, a WhatsApp nudge goes instead, in the language of
        the person's last message, until WhatsApp calling is switched on. No reply in a day is recorded as RNR and tried again
        the next day; a message that cannot be delivered is Unreachable. After 3 tries it is left to the team.
      </p>

      <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-6 gap-2.5 mt-4">
        {tiles.map(([icon, label, n, cls]) => (
          <div key={label} className="rounded-xl border border-slate-800 bg-slate-950/60 px-3 py-2.5">
            <div className={`flex items-center gap-1.5 text-[11.5px] ${cls}`}><Icon name={icon} className="text-[15px]" />{label}</div>
            <div className="text-xl font-semibold tabular-nums text-slate-100 mt-0.5">{n}</div>
          </div>
        ))}
      </div>

      <div className="grid gap-4 xl:grid-cols-3 mt-4">
        <div>
          <h4 className="text-[12px] uppercase tracking-wider text-slate-500 mb-2">Tasks for the team and the DC</h4>
          {b.tasks.length ? (
            <ul className="space-y-2">
              {b.tasks.map(f => (
                <Row key={f.id} f={f} when={`Since ${formatDateTime(f.due_at)}`}>
                  <MarkDone id={f.id} outcomes={b.outcomes} onDone={load} />
                </Row>
              ))}
            </ul>
          ) : <Empty icon="task_alt" text="No open tasks." />}
        </div>
        <div>
          <h4 className="text-[12px] uppercase tracking-wider text-slate-500 mb-2">Coming up</h4>
          {b.coming.length ? (
            <ul className="space-y-2">
              {b.coming.map(f => <Row key={f.id} f={f} when={`Due ${formatDateTime(f.due_at)}`} />)}
            </ul>
          ) : <Empty icon="event_available" text="Nothing scheduled." />}
        </div>
        <div>
          <h4 className="text-[12px] uppercase tracking-wider text-slate-500 mb-2">Latest</h4>
          {b.recent.length ? (
            <ul className="space-y-2">
              {b.recent.map(f => <Row key={f.id} f={f} when={formatDateTime(f.sent_at || f.done_at || f.due_at)} />)}
            </ul>
          ) : <Empty icon="history" text={`No nudges in the last ${days} days.`} />}
        </div>
      </div>
    </section>
  );
};

const Empty: React.FC<{ icon: string; text: string }> = ({ icon, text }) => (
  <div className="py-6 flex flex-col items-center gap-1.5 text-center rounded-xl border border-dashed border-slate-800">
    <Icon name={icon} className="text-[24px] text-slate-600" />
    <span className="text-[12.5px] text-slate-500">{text}</span>
  </div>
);
