import React, { useState } from 'react';
import type { CallPlan } from '../api/inbox';
import { formatDateTime } from '../utils/datetime';

/**
 * One lead's call plan (services/call_plan): when to call after the bot's
 * last message and why then, and what to talk about: the goal, the points,
 * what we already know, their own questions, what to avoid, and what to
 * record after the call. The same plan is handed to the AI calling agent
 * once it is connected.
 *
 * Every label is in Hinglish, as the team speaks (the user, 2026-11-04).
 *
 * Colours come from the theme ramps the light theme redefines, so it reads
 * in both themes.
 */

const Icon: React.FC<{ name: string; className?: string }> = ({ name, className = '' }) =>
  <span className={`material-symbols-outlined ${className}`} aria-hidden="true">{name}</span>;

const Section: React.FC<{ icon: string; title: string; tint: string; children: React.ReactNode }> = ({ icon, title, tint, children }) => (
  <div className="min-w-0">
    <div className={`text-[11px] uppercase tracking-wider font-semibold flex items-center gap-1.5 mb-1.5 ${tint}`}>
      <Icon name={icon} className="text-[15px]" />{title}
    </div>
    {children}
  </div>
);

const List: React.FC<{ items: string[]; mark?: string; cls?: string }> = ({ items, mark = 'check', cls = 'text-slate-200' }) => (
  <ul className="space-y-1">
    {items.map((t, i) => (
      <li key={i} className={`flex gap-1.5 text-[12.5px] leading-relaxed ${cls}`}>
        <Icon name={mark} className="text-[14px] mt-[3px] text-slate-500 shrink-0" /><span>{t}</span>
      </li>
    ))}
  </ul>
);

export const CallPlanCard: React.FC<{ plan: CallPlan; compact?: boolean }> = ({ plan, compact = false }) => {
  const [open, setOpen] = useState(!compact);
  if (!plan.call) {
    return (
      <div className="rounded-lg border border-slate-800 bg-slate-900 p-3 flex items-center gap-2.5 text-[12.5px] text-slate-400">
        <Icon name="phone_disabled" className="text-[18px] text-slate-500" />
        <span><b className="text-slate-300">Abhi call ki zaroorat nahi.</b> {String(plan.why)}</span>
      </div>
    );
  }
  const why = Array.isArray(plan.why) ? plan.why : [plan.why];
  return (
    <div className="rounded-xl border border-amber-800/60 bg-slate-900 overflow-hidden">
      <div className="flex flex-wrap items-center gap-3 px-3.5 py-3 bg-amber-950">
        <span className="h-9 w-9 rounded-lg bg-amber-400 text-slate-950 flex items-center justify-center shrink-0">
          <Icon name="call" className="text-[20px]" />
        </span>
        <div className="min-w-0 flex-1">
          <div className="text-[11px] uppercase tracking-wider font-semibold text-amber-300">Call kab aur kya baat karni hai</div>
          <div className="text-[15px] font-semibold text-slate-100 leading-snug">
            <span className="whitespace-nowrap">{plan.call_at ? formatDateTime(plan.call_at) : '—'}</span>
            {plan.after_message && <span className="block text-[12px] font-normal text-slate-400">hamare last message ke {plan.after_message} baad</span>}
          </div>
        </div>
        <div className={`flex flex-wrap items-center gap-2 ${compact ? 'w-full' : ''}`}>
        {plan.overdue && <span className="px-2 py-0.5 rounded-full text-[10.5px] font-semibold bg-rose-950 text-rose-300 border border-rose-800/60">Abhi call karein</span>}
        {plan.language && (
          <span className="px-2 py-0.5 rounded-full text-[10.5px] font-semibold bg-slate-950 text-slate-300 border border-slate-700 inline-flex items-center gap-1">
            <Icon name="translate" className="text-[13px]" />{plan.language} mein baat karein
          </span>
        )}
        {compact && (
          <button onClick={() => setOpen(!open)} className="text-[12px] text-amber-300 hover:underline cursor-pointer inline-flex items-center gap-0.5">
            {open ? 'Band karein' : 'Kya bolna hai'}<Icon name={open ? 'expand_less' : 'expand_more'} className="text-[16px]" />
          </button>
        )}
        </div>
      </div>
      {open && (
        <div className="p-3.5 space-y-3.5">
          <div className="text-[12px] text-slate-400 space-y-0.5">
            {why.map((w, i) => <div key={i} className="flex gap-1.5"><Icon name="schedule" className="text-[14px] mt-[2px] text-slate-500" />{w}</div>)}
          </div>
          <div className="rounded-lg border border-emerald-800/60 bg-emerald-950 px-3 py-2.5">
            <div className="text-[11px] uppercase tracking-wider font-semibold text-emerald-300">Call ka maqsad</div>
            <div className="text-[14px] font-semibold text-slate-100 mt-0.5">{plan.goal}</div>
            {plan.opening && <div className="text-[12.5px] text-slate-300 mt-1 italic">“{plan.opening}”</div>}
          </div>
          <div className={`grid gap-3.5 ${compact ? '' : 'md:grid-cols-2'}`}>
            {!!plan.points?.length && <Section icon="record_voice_over" title="Kya baat karni hai" tint="text-sky-300"><List items={plan.points} mark="chevron_right" /></Section>}
            <div className="space-y-3.5 min-w-0">
              {!!plan.known?.length && <Section icon="verified" title="Pehle se pata hai (dobara na poochhein)" tint="text-violet-300"><List items={plan.known} /></Section>}
              {!!plan.their_questions?.length && (
                <Section icon="help" title="Unhone poochha tha" tint="text-amber-300"><List items={plan.their_questions.map(q => `“${q}”`)} mark="chat" /></Section>
              )}
            </div>
          </div>
          {!!plan.avoid?.length && <Section icon="block" title="Yeh na karein" tint="text-rose-300"><List items={plan.avoid} mark="close" cls="text-slate-300" /></Section>}
          {plan.record && (
            <Section icon="fact_check" title="Call ke baad record karein" tint="text-slate-400">
              <div className={`grid gap-1.5 text-[12px] ${compact ? '' : 'sm:grid-cols-2'}`}>
                {([['thumb_up', 'Haan', plan.record.if_yes], ['thumb_down', 'Nahi', plan.record.if_no],
                  ['phone_missed', 'Call nahi utha', plan.record.no_answer], ['schedule', 'Baad mein', plan.record.later]] as const).map(([icon, k, v]) => (
                  <div key={k} className="rounded-md border border-slate-800 bg-slate-950/60 px-2.5 py-1.5 flex gap-1.5">
                    <Icon name={icon} className="text-[14px] mt-[2px] text-slate-500" />
                    <span><b className="text-slate-300">{k}:</b> <span className="text-slate-400">{v}</span></span>
                  </div>
                ))}
              </div>
            </Section>
          )}
        </div>
      )}
    </div>
  );
};
