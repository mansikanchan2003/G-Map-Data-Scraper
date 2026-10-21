import React, { useEffect, useMemo, useState } from 'react';
import { fetchJourney, fetchJourneys, type Journey, type JourneyRow, type JourneyStep } from '../api/inbox';
import { formatDateTime } from '../utils/datetime';

/**
 * A lead's journey, step by step with dates: what they did and what we did
 * next, from the campaign to the documents and the hand-over to Eko
 * Acquisition, or to the point it ended (not interested, outside our area,
 * cannot invest...). The steps are read from the chat itself, so older
 * leads have theirs too.
 *
 * On the Dispositions tab: Campaign Insights' deep-teal banner with the
 * funnel (how many leads reached each stage, and how many went on to the
 * next), the three outcomes as filters, then one card per lead whose
 * stepper opens onto a two-sided timeline: them on the left, us on the right.
 */

const Icon: React.FC<{ name: string; className?: string; style?: React.CSSProperties }> = ({ name, className = '', style }) =>
  <span className={`material-symbols-outlined ${className}`} style={style} aria-hidden="true">{name}</span>;
const who = (by: string) => by.includes('@') ? by.split('@')[0].replace(/[._]/g, ' ').replace(/\b\w/g, c => c.toUpperCase()) : by;
const initials = (text: string) => text.replace(/^\+/, '').split(/\s+/).filter(Boolean).slice(0, 2).map(w => w[0]).join('').toUpperCase();
const pct = (n: number, d: number) => (d ? Math.round((n / d) * 100) : 0);

// Each stage's icon, and the icons of the other turns a journey takes.
const STAGE_ICON: Record<string, string> = {
  campaign: 'campaign', interested: 'thumb_up', language: 'translate', pin: 'pin_drop', education: 'school',
  investment: 'currency_rupee', docs_ready: 'folder_open', uploaded: 'upload_file', handed_over: 'handshake',
  wrote_in: 'chat', guidance: 'support_agent', docs_later: 'schedule', not_served: 'wrong_location',
  not_eligible: 'person_off', not_investing: 'money_off',
};
const EVENT_ICON: Record<string, string> = {
  nudge: 'notifications', question_ack: 'help', handover: 'support_agent', answered: 'forum', team_reply: 'reply',
  to_person: 'front_hand', to_bot: 'smart_toy', ticket_solved: 'task_alt', planned: 'event_upcoming',
  to_acquisition: 'handshake', task: 'assignment', bad_pin: 'pin_drop', unknown_pin: 'pin_drop',
};
const iconOf = (s: JourneyStep) => s.key.startsWith('disposition:') ? 'label'
  : s.key.startsWith('again:') ? 'replay' : (s.kind === 'stage' ? STAGE_ICON[s.key] : EVENT_ICON[s.key]) || 'circle';

// Status colours, always with an icon and words beside them.
const TONE: Record<string, { chip: string; ring: string; text: string }> = {
  positive: { chip: 'bg-emerald-950 text-emerald-300', ring: 'ring-emerald-500/50', text: 'text-emerald-300' },
  negative: { chip: 'bg-rose-950 text-rose-300', ring: 'ring-rose-500/50', text: 'text-rose-300' },
  warning: { chip: 'bg-amber-950 text-amber-300', ring: 'ring-amber-500/50', text: 'text-amber-300' },
  handover: { chip: 'bg-violet-950 text-violet-300', ring: 'ring-violet-500/60', text: 'text-violet-300' },
  planned: { chip: 'bg-sky-950 text-sky-300', ring: 'ring-sky-500/50', text: 'text-sky-300' },
  neutral: { chip: 'bg-slate-800 text-slate-300', ring: 'ring-slate-600', text: 'text-slate-300' },
};
const OUTCOME: Record<string, { label: string; icon: string; cls: string; accent: string }> = {
  in_progress: { label: 'In progress', icon: 'directions_run', cls: 'border-sky-800/60 bg-sky-950 text-sky-300', accent: '#7dd3fc' },
  handed_over: { label: 'Handed to Eko Acquisition', icon: 'handshake', cls: 'border-violet-800/60 bg-violet-950 text-violet-300', accent: '#c4b5fd' },
  closed: { label: 'Ended', icon: 'block', cls: 'border-rose-800/60 bg-rose-950 text-rose-300', accent: '#fda4af' },
};

/** The stages as an icon stepper, filled as far as the lead got; hover a stage for its date. */
export const Stepper: React.FC<{ funnel: Journey['funnel']; furthest: number; outcome: string; size?: 'sm' | 'md' }> =
  ({ funnel, furthest, outcome, size = 'md' }) => {
  const fill = outcome === 'handed_over' ? 'bg-violet-500 text-white' : 'bg-emerald-500 text-white';
  const line = outcome === 'handed_over' ? 'bg-violet-500' : 'bg-emerald-500';
  const dim = size === 'sm' ? 'h-6 w-6 text-[13px]' : 'h-7 w-7 text-[15px]';
  return (
    <div className="flex items-center" aria-label={`Reached ${funnel[furthest]?.label || 'nothing yet'}`}>
      {funnel.map((f, i) => {
        const done = i <= furthest;
        const stopped = outcome === 'closed' && i === furthest;
        return (
          <React.Fragment key={f.key}>
            {i > 0 && <span className={`h-[3px] flex-1 min-w-[6px] ${i <= furthest ? line : 'bg-slate-800'}`} />}
            <span title={`${f.label}${f.at ? ` · ${formatDateTime(f.at)}` : ' · not yet'}`}
              className={`shrink-0 rounded-full flex items-center justify-center ${dim} ${stopped ? 'bg-rose-500 text-white'
                : done ? fill : 'bg-slate-900 text-slate-600 border border-slate-700'}`}>
              <Icon name={STAGE_ICON[f.key] || 'circle'} className="text-[inherit]" />
            </span>
          </React.Fragment>
        );
      })}
    </div>
  );
};

/** Backwards compatible name for the slim bar some screens use. */
export const FunnelBar = Stepper;

const Side: React.FC<{ title: string; at: string | null; by?: string; children: React.ReactNode; align: 'left' | 'right' }> =
  ({ title, at, by, children, align }) => (
  <div className={`min-w-0 ${align === 'left' ? 'sm:text-right' : ''}`}>
    <div className="text-[10.5px] uppercase tracking-wider text-slate-500">
      {title}{at && <> · <span className="normal-case tracking-normal">{formatDateTime(at)}</span></>}
      {by && <> · <span className="normal-case tracking-normal">{by}</span></>}
    </div>
    <div className="text-[13px] text-slate-200 leading-snug mt-0.5">{children}</div>
  </div>
);

/** One row of the two-sided timeline: what happened on the left, our action on the right, the step on the spine. */
const Row: React.FC<{ s: JourneyStep; last: boolean }> = ({ s, last }) => {
  const tone = TONE[s.tone] || TONE.neutral;
  const stage = s.kind === 'stage';
  const ours = s.by && s.by !== 'bot' ? who(s.by) : 'Bot';
  return (
    <li className="relative grid grid-cols-[40px_1fr] sm:grid-cols-[1fr_40px_1fr] gap-x-3 pb-4">
      {!last && <span className="absolute top-9 bottom-0 left-[19px] sm:left-1/2 w-px bg-slate-800 sm:-translate-x-1/2" />}
      <div className="hidden sm:block">
        {s.what && <Side title="They" at={s.at} align="left"><span className={stage ? `font-semibold ${tone.text}` : ''}>{s.what}</span></Side>}
      </div>
      <div className="flex justify-center">
        <span className={`relative z-10 rounded-full flex items-center justify-center ring-4 ring-slate-900 ${tone.chip} ${stage
          ? 'h-9 w-9 text-[18px] shadow-lg' : 'h-7 w-7 mt-1 text-[14px] opacity-90'}`}>
          <Icon name={iconOf(s)} className="text-[inherit]" />
        </span>
      </div>
      <div className="space-y-1.5 min-w-0">
        {s.what && <div className="sm:hidden"><Side title="They" at={s.at} align="right"><span className={stage ? `font-semibold ${tone.text}` : ''}>{s.what}</span></Side></div>}
        {s.action && <Side title={s.by === 'Eko Acquisition' ? 'Eko Acquisition' : 'We'} at={s.action_at !== s.at || !s.what ? s.action_at : null}
          by={stage && s.by !== 'bot' && s.by !== 'Eko Acquisition' ? ours : undefined} align="right">{s.action}</Side>}
        {s.detail && (
          <div className="inline-block text-[12px] text-slate-300 bg-slate-950/70 border border-slate-800 rounded-lg px-2.5 py-1">{s.detail}</div>
        )}
      </div>
    </li>
  );
};

/** One lead's journey; `version` refetches it when the chat changes. `compact` fits the inbox's side panel. */
export const JourneyTimeline: React.FC<{ phone: string; version?: string; stagesOnly?: boolean; compact?: boolean }> =
  ({ phone, version, stagesOnly: initial = false, compact = false }) => {
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
        <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full border text-[11px] font-semibold ${outcome.cls}`}>
          <Icon name={outcome.icon} className="text-[13px]" />{outcome.label}
        </span>
        <span className="text-[11.5px] text-slate-500">Now: {j.now.label}</span>
        <span className="flex-1" />
        <button onClick={() => setStagesOnly(!stagesOnly)} className="text-[11.5px] text-sky-300 hover:underline cursor-pointer">
          {stagesOnly ? 'Show everything' : 'Only the steps'}
        </button>
      </div>
      <Stepper funnel={j.funnel} furthest={j.furthest} outcome={j.outcome} size="sm" />
      {!steps.length && <div className="text-[12.5px] text-slate-500">Nothing has happened in this chat yet.</div>}
      {compact ? (
        <ol className="pt-1">
          {steps.map((s, i) => {
            const tone = TONE[s.tone] || TONE.neutral;
            return (
              <li key={i} className="relative pl-8 pb-3">
                {i < steps.length - 1 && <span className="absolute left-[11px] top-6 bottom-0 w-px bg-slate-800" />}
                <span className={`absolute left-0 top-0.5 h-6 w-6 rounded-full flex items-center justify-center text-[13px] ${tone.chip}`}>
                  <Icon name={iconOf(s)} className="text-[inherit]" />
                </span>
                {s.what && <div className={`text-[12.5px] ${s.kind === 'stage' ? `font-semibold ${tone.text}` : 'text-slate-300'}`}>{s.what}</div>}
                {s.action && <div className="text-[12px] text-slate-400">→ {s.action}</div>}
                <div className="text-[10.5px] text-slate-500">{formatDateTime(s.at || s.action_at || '')}</div>
              </li>
            );
          })}
        </ol>
      ) : (
        <>
          <div className="hidden sm:grid grid-cols-[1fr_40px_1fr] gap-x-3 text-[11px] uppercase tracking-[0.12em] text-slate-500 pt-1">
            <div className="text-right">What they did</div><div /><div>What we did</div>
          </div>
          <ol>{steps.map((s, i) => <Row key={i} s={s} last={i === steps.length - 1} />)}</ol>
        </>
      )}
    </div>
  );
};

/** Every campaign lead's journey, on the Dispositions tab. */
export const LeadJourneysPanel: React.FC = () => {
  const [rows, setRows] = useState<JourneyRow[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [open, setOpen] = useState<string | null>(null);
  const [filter, setFilter] = useState<'all' | 'in_progress' | 'handed_over' | 'closed'>('all');
  const [stageFilter, setStageFilter] = useState<number | null>(null);
  useEffect(() => { fetchJourneys().then(setRows).catch(e => setError(e.message)); }, []);
  const counts = useMemo(() => (rows || []).reduce<Record<string, number>>((a, r) => ({ ...a, [r.outcome]: (a[r.outcome] || 0) + 1 }), {}), [rows]);

  if (error) return <div className="p-4 rounded-xl border border-rose-800/60 bg-rose-950 text-rose-300 text-sm">Could not load the journeys: {error}</div>;
  if (!rows) return <div className="h-56 rounded-2xl bg-slate-900 border border-slate-800 animate-pulse" />;

  const funnel = rows[0]?.funnel || [];
  // How many leads reached each stage; the campaign stage counts everyone listed.
  const reached = funnel.map((_, i) => rows.filter(r => r.furthest >= i).length);
  const top = Math.max(1, ...reached);
  const shown = rows.filter(r => (filter === 'all' || r.outcome === filter) && (stageFilter === null || r.furthest === stageFilter));

  return (
    <div className="space-y-4 select-text">
      <section className="rounded-2xl overflow-hidden shadow-md text-white"
        style={{ background: 'linear-gradient(120deg, #0a3543 0%, #16435a 55%, #1d5a6e 100%)' }}>
        <div className="p-6 pb-4 flex flex-wrap items-end justify-between gap-4">
          <div>
            <div className="text-[11px] uppercase tracking-[0.14em] font-semibold flex items-center gap-2" style={{ color: '#f9ab10' }}>
              <Icon name="route" className="text-[15px]" />Lead journeys
            </div>
            <div className="mt-1 flex items-baseline gap-3">
              <span className="text-4xl sm:text-5xl font-semibold tabular-nums">{rows.length}</span>
              <span className="text-sm text-white/75">leads on their way · <b className="text-white">{counts.handed_over || 0}</b> handed to Eko Acquisition</span>
            </div>
            <p className="text-sm text-white/70 mt-1 max-w-2xl">
              From the campaign to the documents, every step dated with what we did next. Click a stage to see the leads who stopped there.
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            {(['in_progress', 'handed_over', 'closed'] as const).map(k => {
              const o = OUTCOME[k];
              const on = filter === k;
              return (
                <button key={k} onClick={() => setFilter(on ? 'all' : k)}
                  className={`text-left rounded-lg px-3.5 py-2.5 min-w-[130px] transition-all cursor-pointer ${on ? 'bg-white/20 ring-2 ring-[#f9ab10]' : 'bg-white/10 hover:bg-white/15'}`}>
                  <div className="flex items-center gap-1.5 text-white/75 text-[11.5px]"><Icon name={o.icon} className="text-[15px]" style={{ color: o.accent }} />{o.label}</div>
                  <div className="text-2xl font-semibold tabular-nums">{counts[k] || 0}</div>
                </button>
              );
            })}
          </div>
        </div>

        {/* The funnel: a column per stage, as tall as the leads who reached it, and the share who went on. */}
        <div className="px-6 pb-6 overflow-x-auto">
          <div className="grid gap-1.5 min-w-[640px]" style={{ gridTemplateColumns: `repeat(${funnel.length}, minmax(0, 1fr))` }}>
            {funnel.map((f, i) => {
              const n = reached[i];
              const on = stageFilter === i;
              const stoppedHere = rows.filter(r => r.furthest === i).length;
              return (
                <button key={f.key} onClick={() => setStageFilter(on ? null : i)}
                  title={`${n} reached ${f.label}; ${stoppedHere} stopped here`}
                  className={`group flex flex-col items-center gap-1.5 rounded-lg px-1 pt-2 pb-2 cursor-pointer transition-colors ${on ? 'bg-white/15 ring-2 ring-[#f9ab10]' : 'hover:bg-white/10'}`}>
                  <span className="text-[17px] font-semibold tabular-nums">{n}</span>
                  <div className="w-full h-20 flex items-end justify-center">
                    <div className="w-[70%] rounded-t-md transition-all"
                      style={{ height: `${Math.max(6, (n / top) * 100)}%`,
                        background: f.key === 'handed_over' ? 'linear-gradient(180deg,#c4b5fd,#7c3aed)' : 'linear-gradient(180deg,#6ee7b7,#059669)',
                        opacity: n ? 1 : 0.25 }} />
                  </div>
                  <Icon name={STAGE_ICON[f.key]} className="text-[18px] text-white/80" />
                  <span className="text-[10.5px] leading-tight text-center text-white/75 h-7">{f.label}</span>
                  <span className="text-[10px] tabular-nums text-white/50">{i > 0 ? `${pct(n, reached[i - 1])}% went on` : ' '}</span>
                </button>
              );
            })}
          </div>
        </div>
      </section>

      {(filter !== 'all' || stageFilter !== null) && (
        <div className="flex items-center gap-2 text-[12.5px] text-slate-400">
          Showing {shown.length} {shown.length === 1 ? 'lead' : 'leads'}
          {filter !== 'all' && <> · {OUTCOME[filter].label.toLowerCase()}</>}
          {stageFilter !== null && <> · stopped at {funnel[stageFilter]?.label}</>}
          <button onClick={() => { setFilter('all'); setStageFilter(null); }} className="text-sky-300 hover:underline cursor-pointer">Show all</button>
        </div>
      )}

      <ul className="grid gap-3">
        {shown.map(r => {
          const isOpen = open === r.phone;
          const o = OUTCOME[r.outcome] || OUTCOME.in_progress;
          return (
            <li key={r.phone} className={`rounded-2xl border bg-slate-900 shadow-sm transition-colors ${isOpen ? 'border-sky-800' : 'border-slate-800 hover:border-slate-700'}`}>
              <button onClick={() => setOpen(isOpen ? null : r.phone)} className="w-full text-left p-4 cursor-pointer">
                <div className="flex flex-wrap items-center gap-3">
                  <span className="h-10 w-10 rounded-full bg-slate-800 text-slate-200 text-[13px] font-bold flex items-center justify-center shrink-0">
                    {initials(r.name || r.phone)}
                  </span>
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="text-[14px] font-semibold text-slate-100">{r.name || r.phone}</span>
                      <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full border text-[10.5px] font-semibold ${o.cls}`}>
                        <Icon name={o.icon} className="text-[12px]" />{o.label}
                      </span>
                    </div>
                    <div className="text-[12px] text-slate-500 truncate">
                      {r.last ? r.last.what : 'Nothing yet'}{r.last?.at ? ` · ${formatDateTime(r.last.at)}` : ''}
                    </div>
                  </div>
                  <Icon name={isOpen ? 'expand_less' : 'expand_more'} className="text-[20px] text-slate-500" />
                </div>
                <div className="mt-3"><Stepper funnel={r.funnel} furthest={r.furthest} outcome={r.outcome} /></div>
              </button>
              {isOpen && (
                <div className="px-4 pb-4 pt-3 border-t border-slate-800">
                  <div className="flex justify-end mb-1">
                    <a href={`#inbox/${r.phone.replace(/\D/g, '')}`} className="inline-flex items-center gap-1 text-[12px] text-sky-300 hover:underline">
                      <Icon name="chat" className="text-[14px]" />Open the chat
                    </a>
                  </div>
                  <JourneyTimeline phone={r.phone} />
                </div>
              )}
            </li>
          );
        })}
        {!shown.length && (
          <li className="py-10 flex flex-col items-center gap-2 text-center rounded-2xl border border-dashed border-slate-800">
            <Icon name="route" className="text-[28px] text-slate-600" />
            <span className="text-[13px] text-slate-500">No leads here yet.</span>
          </li>
        )}
      </ul>
    </div>
  );
};
