import React, { useEffect, useMemo, useState } from 'react';
import type { CallPlan, QueueItem } from '../api/inbox';
import { formatDateTime } from '../utils/datetime';

/**
 * Call plans (services/call_plan): when to call a lead after the bot's last
 * message and why then, and what to talk about: the goal, the points, what
 * we already know, their own questions, what to avoid, and what to record
 * after the call. The same plan is handed to the AI calling agent once it is
 * connected.
 *
 * - CallGrid: every call due, as a grid of small cards, soonest first (the
 *   ones past their time on top); a card opens the whole plan in a pop-up
 *   (the user, 2026-11-05: the long column read badly).
 * - CallPlanCard: one lead's whole plan, on their journey and in the pop-up.
 *
 * Every label is in Hinglish, as the team speaks (the user, 2026-11-04).
 * The banner keeps Eko's own teal and gold in either theme, like the goal
 * banner; the rest uses the theme ramps the light theme redefines.
 */

const Icon: React.FC<{ name: string; className?: string }> = ({ name, className = '' }) =>
  <span className={`material-symbols-outlined ${className}`} aria-hidden="true">{name}</span>;

const TEAL = 'linear-gradient(120deg, #0a3543 0%, #16435a 55%, #1d5a6e 100%)';
const GOLD = '#f9ab10';

const initials = (name: string) =>
  name.replace(/^\+/, '').split(/\s+/).filter(Boolean).slice(0, 2).map(w => w[0]).join('').toUpperCase() || '?';

/** "Abhi" when due, else "Aaj 2:00 PM", "Kal 11:00 AM" or the date. */
const whenLabel = (iso?: string, overdue?: boolean) => {
  if (!iso) return '—';
  if (overdue) return 'Abhi';
  const at = new Date(iso);
  const day = (d: Date) => d.toLocaleDateString('en-CA', { timeZone: 'Asia/Kolkata' });
  const time = at.toLocaleTimeString('en-IN', { hour: 'numeric', minute: '2-digit', hour12: true, timeZone: 'Asia/Kolkata' });
  const today = new Date();
  const tomorrow = new Date(Date.now() + 86400000);
  if (day(at) === day(today)) return `Aaj ${time}`;
  if (day(at) === day(tomorrow)) return `Kal ${time}`;
  return formatDateTime(iso);
};

// Tiles of the plan: each with its own colour family from the theme ramps.
const TILE = {
  points: { icon: 'record_voice_over', title: 'Kya baat karni hai', ring: 'border-sky-800/60', head: 'bg-sky-950 text-sky-300', mark: 'chevron_right' },
  known: { icon: 'verified', title: 'Pehle se pata hai', sub: 'dobara na poochhein', ring: 'border-violet-800/60', head: 'bg-violet-950 text-violet-300', mark: 'check' },
  asked: { icon: 'forum', title: 'Unhone poochha tha', ring: 'border-amber-800/60', head: 'bg-amber-950 text-amber-300', mark: 'chat' },
  avoid: { icon: 'block', title: 'Yeh na karein', ring: 'border-rose-800/60', head: 'bg-rose-950 text-rose-300', mark: 'close' },
} as const;

const Tile: React.FC<{ kind: keyof typeof TILE; items: string[] }> = ({ kind, items }) => {
  const t = TILE[kind];
  return (
    <section className={`rounded-xl border ${t.ring} bg-slate-900 overflow-hidden min-w-0`}>
      <div className={`px-3.5 py-2 flex items-center gap-2 text-[11.5px] font-semibold uppercase tracking-wider ${t.head}`}>
        <Icon name={t.icon} className="text-[16px]" />{t.title}
        {'sub' in t && <span className="normal-case tracking-normal font-normal opacity-80">({t.sub})</span>}
      </div>
      <ul className="p-3.5 space-y-1.5">
        {items.map((x, i) => (
          <li key={i} className="flex gap-2 text-[13px] leading-relaxed text-slate-200">
            <Icon name={t.mark} className="text-[15px] mt-[3px] text-slate-500 shrink-0" /><span>{x}</span>
          </li>
        ))}
      </ul>
    </section>
  );
};

const RECORD = [
  ['if_yes', 'thumb_up', 'Haan', 'text-emerald-300 bg-emerald-950 border-emerald-800/60'],
  ['if_no', 'thumb_down', 'Nahi', 'text-rose-300 bg-rose-950 border-rose-800/60'],
  ['no_answer', 'phone_missed', 'Call nahi utha', 'text-amber-300 bg-amber-950 border-amber-800/60'],
  ['later', 'schedule', 'Baad mein', 'text-sky-300 bg-sky-950 border-sky-800/60'],
] as const;

/** One lead's whole call plan: a banner with when and why, the goal, then the plan's tiles. */
export const CallPlanCard: React.FC<{ plan: CallPlan; onClose?: () => void }> = ({ plan, onClose }) => {
  if (!plan.call) {
    return (
      <div className="rounded-xl border border-slate-800 bg-slate-900 p-3.5 flex items-center gap-3 text-[13px] text-slate-400">
        <span className="h-9 w-9 rounded-lg bg-slate-800 text-slate-400 flex items-center justify-center"><Icon name="phone_disabled" className="text-[19px]" /></span>
        <span><b className="text-slate-200">Abhi call ki zaroorat nahi.</b> {String(plan.why)}</span>
      </div>
    );
  }
  const why = Array.isArray(plan.why) ? plan.why : [plan.why];
  return (
    <div className="rounded-2xl overflow-hidden border border-slate-800 bg-slate-950 shadow-lg">
      <header className="relative px-5 py-4 text-white" style={{ background: TEAL }}>
        <div className="flex items-start gap-3.5">
          <span className="h-12 w-12 rounded-2xl flex items-center justify-center text-[#0a3543] font-bold text-[16px] shrink-0 shadow"
            style={{ background: GOLD }}>{initials(plan.name)}</span>
          <div className="min-w-0 flex-1">
            <div className="text-[11px] uppercase tracking-[0.14em] font-semibold" style={{ color: GOLD }}>Call kab aur kya baat karni hai</div>
            <div className="text-[19px] font-semibold leading-tight mt-0.5 truncate">{plan.name}</div>
            <div className="flex flex-wrap items-center gap-2 mt-2.5">
              <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-white/15 text-[12.5px] font-semibold">
                <Icon name="call" className="text-[15px]" />{plan.call_at ? formatDateTime(plan.call_at) : '—'}
              </span>
              {plan.after_message && <span className="text-[12px] text-white/75">hamare last message ke {plan.after_message} baad</span>}
              {plan.overdue && (
                <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-[11.5px] font-bold text-[#0a3543]" style={{ background: GOLD }}>
                  <span className="h-1.5 w-1.5 rounded-full bg-[#0a3543] animate-pulse" />Abhi call karein
                </span>
              )}
              {plan.language && (
                <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full bg-white/10 text-[11.5px] font-semibold text-white/90">
                  <Icon name="translate" className="text-[14px]" />{plan.language} mein baat karein
                </span>
              )}
            </div>
          </div>
          {onClose && (
            <button onClick={onClose} aria-label="Band karein"
              className="h-8 w-8 rounded-lg bg-white/10 hover:bg-white/20 flex items-center justify-center cursor-pointer shrink-0">
              <Icon name="close" className="text-[19px]" />
            </button>
          )}
        </div>
        <ul className="mt-3 space-y-0.5 text-[12px] text-white/75">
          {why.map((w, i) => <li key={i} className="flex gap-1.5"><Icon name="schedule" className="text-[14px] mt-[1px]" />{w}</li>)}
        </ul>
      </header>

      <div className="p-4 space-y-3.5">
        <section className="rounded-xl border border-emerald-800/60 bg-emerald-950 p-3.5">
          <div className="text-[11px] uppercase tracking-wider font-semibold text-emerald-300 flex items-center gap-1.5">
            <Icon name="flag" className="text-[15px]" />Call ka maqsad
          </div>
          <div className="text-[15px] font-semibold text-slate-100 mt-1">{plan.goal}</div>
          {plan.opening && (
            <div className="mt-2 rounded-lg bg-slate-950/60 border border-emerald-800/40 px-3 py-2 text-[13px] text-slate-300 italic flex gap-2">
              <Icon name="format_quote" className="text-[16px] text-emerald-400 not-italic" />{plan.opening}
            </div>
          )}
        </section>

        <div className="grid gap-3.5 md:grid-cols-2">
          {!!plan.points?.length && <Tile kind="points" items={plan.points} />}
          <div className="space-y-3.5 min-w-0">
            {!!plan.known?.length && <Tile kind="known" items={plan.known} />}
            {!!plan.their_questions?.length && <Tile kind="asked" items={plan.their_questions.map(q => `“${q}”`)} />}
          </div>
        </div>
        {!!plan.avoid?.length && <Tile kind="avoid" items={plan.avoid} />}

        {plan.record && (
          <section>
            <div className="text-[11px] uppercase tracking-wider font-semibold text-slate-400 flex items-center gap-1.5 mb-2">
              <Icon name="fact_check" className="text-[15px]" />Call ke baad record karein
            </div>
            <div className="grid gap-2 sm:grid-cols-2">
              {RECORD.map(([key, icon, label, cls]) => (
                <div key={key} className={`rounded-lg border px-3 py-2 flex gap-2 text-[12.5px] ${cls}`}>
                  <Icon name={icon} className="text-[16px] mt-[1px]" />
                  <span><b>{label}:</b> <span className="text-slate-300">{plan.record![key]}</span></span>
                </div>
              ))}
            </div>
          </section>
        )}
      </div>
    </div>
  );
};

/** The whole plan in a pop-up; Escape or a click outside closes it. */
export const CallPlanModal: React.FC<{ plan: CallPlan; onClose: () => void }> = ({ plan, onClose }) => {
  useEffect(() => {
    const key = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', key);
    return () => window.removeEventListener('keydown', key);
  }, [onClose]);
  return (
    <div className="fixed inset-0 z-50 flex items-start sm:items-center justify-center bg-slate-950/80 backdrop-blur-sm p-3 sm:p-6 overflow-y-auto"
      onClick={onClose} role="dialog" aria-modal="true" aria-label={`Call plan: ${plan.name}`}>
      <div className="w-full max-w-3xl my-auto" onClick={e => e.stopPropagation()}>
        <CallPlanCard plan={plan} onClose={onClose} />
        <div className="mt-3 flex justify-end">
          <a href={`#inbox/${plan.phone.replace(/\D/g, '')}`}
            className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-lg text-[13px] font-semibold text-[#0a3543] shadow hover:opacity-90"
            style={{ background: GOLD }}>
            <Icon name="forum" className="text-[17px]" />Chat kholein aur disposition record karein
          </a>
        </div>
      </div>
    </div>
  );
};

// Small cards: the time decides the accent.
const URGENCY = {
  now: { bar: 'bg-rose-500', chip: 'bg-rose-950 text-rose-300 border-rose-800/60', icon: 'notifications_active' },
  today: { bar: 'bg-amber-400', chip: 'bg-amber-950 text-amber-300 border-amber-800/60', icon: 'today' },
  later: { bar: 'bg-sky-500', chip: 'bg-sky-950 text-sky-300 border-sky-800/60', icon: 'event_upcoming' },
};

const urgency = (p: CallPlan) => {
  if (p.overdue) return 'now' as const;
  const day = (d: Date) => d.toLocaleDateString('en-CA', { timeZone: 'Asia/Kolkata' });
  return p.call_at && day(new Date(p.call_at)) === day(new Date()) ? 'today' as const : 'later' as const;
};

/** Every call due, as a grid of small cards, soonest first; a card opens its plan. */
export const CallGrid: React.FC<{ items: QueueItem[] }> = ({ items }) => {
  const [open, setOpen] = useState<CallPlan | null>(null);
  const plans = useMemo(() => items.map(i => i.call_plan!).filter(Boolean)
    .sort((a, b) => Number(!!b.overdue) - Number(!!a.overdue) || (a.call_at || '').localeCompare(b.call_at || '')), [items]);
  const counts = { now: 0, today: 0, later: 0 };
  plans.forEach(p => { counts[urgency(p)] += 1; });

  return (
    <section className="rounded-2xl border border-slate-800 bg-slate-900 overflow-hidden shadow-sm">
      <header className="px-5 py-4 text-white flex flex-wrap items-center gap-3" style={{ background: TEAL }}>
        <span className="h-10 w-10 rounded-xl flex items-center justify-center text-[#0a3543]" style={{ background: GOLD }}>
          <Icon name="phone_in_talk" className="text-[22px]" />
        </span>
        <div className="min-w-0 flex-1">
          <h3 className="text-[16px] font-semibold leading-tight">Calls to make</h3>
          <p className="text-[12px] text-white/75">Har lead ka apna time aur baat karne ke points. Card par click karke poora plan dekhein.</p>
        </div>
        <div className="flex gap-2 w-full sm:w-auto">
          {([['now', 'Abhi'], ['today', 'Aaj'], ['later', 'Aage']] as const).map(([k, label]) => (
            <span key={k} className="flex-1 sm:flex-none px-3 py-1.5 rounded-lg bg-white/10 text-center min-w-[64px]">
              <div className="text-[18px] font-bold tabular-nums leading-none">{counts[k]}</div>
              <div className="text-[10.5px] text-white/70 mt-0.5">{label}</div>
            </span>
          ))}
        </div>
      </header>

      {plans.length ? (
        <div className="p-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4">
          {plans.map(p => {
            const u = URGENCY[urgency(p)];
            return (
              <button key={p.phone} onClick={() => setOpen(p)}
                className="group relative text-left rounded-xl border border-slate-800 bg-slate-950/60 hover:bg-slate-950 hover:border-slate-600 hover:shadow-md transition p-3.5 pl-4 cursor-pointer overflow-hidden">
                <span className={`absolute left-0 top-0 bottom-0 w-1 ${u.bar}`} />
                <div className="flex items-center gap-2.5">
                  <span className="h-9 w-9 rounded-full flex items-center justify-center text-[12px] font-bold text-white shrink-0"
                    style={{ background: TEAL }}>{initials(p.name)}</span>
                  <div className="min-w-0 flex-1">
                    <div className="text-[13.5px] font-semibold text-slate-100 truncate">{p.name}</div>
                    <div className="text-[11px] text-slate-500 truncate">{p.disposition || 'Abhi koi disposition nahi'}</div>
                  </div>
                  <span className={`shrink-0 inline-flex items-center gap-1 px-2 py-0.5 rounded-full border text-[11px] font-semibold ${u.chip}`}>
                    <Icon name={u.icon} className="text-[13px]" />{whenLabel(p.call_at, p.overdue)}
                  </span>
                </div>
                <p className="mt-2.5 text-[12.5px] text-slate-300 leading-snug"
                  style={{ display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical', overflow: 'hidden' }}>
                  {p.goal}
                </p>
                <div className="mt-2.5 flex items-center justify-between gap-2">
                  {p.language && (
                    <span className="inline-flex items-center gap-1 text-[11px] text-slate-400">
                      <Icon name="translate" className="text-[13px]" />{p.language}
                    </span>
                  )}
                  <span className="inline-flex items-center gap-0.5 text-[11.5px] font-semibold text-sky-300 group-hover:translate-x-0.5 transition">
                    Plan dekhein<Icon name="arrow_forward" className="text-[14px]" />
                  </span>
                </div>
              </button>
            );
          })}
        </div>
      ) : (
        <div className="py-10 flex flex-col items-center gap-2 text-center">
          <Icon name="task_alt" className="text-[30px] text-emerald-400" />
          <span className="text-[13px] text-slate-400">Abhi koi call baaki nahi.</span>
        </div>
      )}
      {open && <CallPlanModal plan={open} onClose={() => setOpen(null)} />}
    </section>
  );
};
