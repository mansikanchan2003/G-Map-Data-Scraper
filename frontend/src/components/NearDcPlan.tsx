import React from 'react';
import type { NearDcPlan as Plan, NearDcDay, Stage } from '../api/insights';

/**
 * CSPs near DCs, day by day (19 Nov 2026): the shops at the 40 SBI-allocated CSP centres in the
 * DCs' districts, two campaigns a day (Haryana at 10:30 AM, Punjab at 12:30 PM), with the
 * centres each one covers, how many people, which kinds of business, and what to expect.
 * Teal, the colour of the CSPs near DCs label everywhere else in the app.
 */

const Icon: React.FC<{ name: string; className?: string }> = ({ name, className = '' }) =>
  <span className={`material-symbols-outlined ${className}`} aria-hidden="true">{name}</span>;
const num = (v: number) => v.toLocaleString('en-IN');
const tenth = (v: number) => (v >= 10 ? Math.round(v).toLocaleString('en-IN') : v.toFixed(1));
const STEPS: { key: Stage; label: string; colour: string }[] = [
  { key: 'engaged', label: 'Reply or tap', colour: '#2dd4bf' },
  { key: 'interested', label: 'Start applying', colour: '#34d399' },
  { key: 'qualified', label: 'Qualify', colour: '#a78bfa' },
  { key: 'lead', label: 'Leads', colour: '#f9ab10' },
];
const BANNER = 'linear-gradient(120deg, #053b3a 0%, #0f5e5a 55%, #14857d 100%)';

const DayCard: React.FC<{ d: NearDcDay; first: boolean; cap: number }> = ({ d, first, cap }) => {
  const [day, ...rest] = d.label.split(', ');
  return (
    <div className={`rounded-xl border p-3.5 min-w-0 flex flex-col ${first
      ? 'border-teal-500/60 ring-1 ring-teal-500/30 bg-teal-500/5' : 'border-slate-800 bg-slate-950/60'}`}>
      <div className="flex items-center justify-between gap-2">
        <div className="min-w-0">
          <div className={`text-[11px] uppercase tracking-wider font-bold ${first ? 'text-teal-400' : 'text-slate-500'}`}>{day}</div>
          <div className="text-[12px] text-slate-400">{rest.join(', ')}</div>
        </div>
        <span className="shrink-0 inline-flex items-center gap-1 rounded-full bg-slate-800 px-2 py-0.5 text-[11px] font-semibold text-slate-200 tabular-nums">
          <Icon name="group" className="text-[14px]" />{num(d.people)}
        </span>
      </div>
      <div className="mt-2.5 space-y-3 flex-1">
        {(d.campaigns || []).map(c => {
          const slots = d.slots.filter(s => s.time === c.time);
          const state = slots[0]?.state || '';
          return (
            <div key={c.time} className="space-y-2">
              <div className="flex items-center justify-between gap-2 rounded-lg bg-teal-500/10 border border-teal-500/30 px-2 py-1">
                <span className="inline-flex items-center gap-1 text-[12px] font-bold text-teal-300"><Icon name="schedule" className="text-[15px]" />{c.time}</span>
                <span className="text-[11px] text-slate-300 font-semibold truncate">{state}</span>
                <span className="text-[11px] text-slate-400 tabular-nums">{num(c.people)}</span>
              </div>
              {slots.map((s, i) => (
                <div key={`${c.time}-${s.code || i}`} className="min-w-0">
                  <div className="flex items-baseline gap-1.5 min-w-0">
                    <Icon name="share_location" className="text-[15px] text-teal-400 self-center" />
                    <span className="text-[13px] font-semibold text-slate-100 truncate">{s.centre}</span>
                    {s.pincode && <span className="text-[11px] text-slate-500 shrink-0">{s.pincode}</span>}
                  </div>
                  <div className="text-[11px] text-slate-500 truncate">{[s.subdistrict, s.district].filter(Boolean).join(', ') || s.state} · {num(s.people)} people</div>
                  <div className="mt-1 flex flex-wrap gap-1">
                    {s.kinds.slice(0, 3).map(k => (
                      <span key={k.category} className="rounded-full border border-slate-700 bg-slate-900 px-1.5 py-px text-[10.5px] text-slate-300 truncate max-w-full">
                        {k.category} · {num(k.people)}
                      </span>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          );
        })}
      </div>
      <div className="mt-3 pt-2.5 border-t border-slate-800 space-y-1">
        {STEPS.map(st => (
          <div key={st.key} className="flex items-center gap-2 text-[11px]">
            <span className="w-[84px] shrink-0 text-slate-400 truncate">{st.label}</span>
            <div className="flex-1 h-1.5 rounded-full bg-slate-800 overflow-hidden">
              <div className="h-full rounded-full" style={{ width: `${Math.min(100, Math.max(3, (d.expect[st.key] / Math.max(cap * 0.05, 1)) * 100))}%`, background: st.colour }} />
            </div>
            <span className={`w-8 text-right tabular-nums font-semibold ${st.key === 'lead' ? 'text-amber-400' : 'text-slate-200'}`}>{tenth(d.expect[st.key])}</span>
          </div>
        ))}
      </div>
    </div>
  );
};

export const NearDcPlanCard: React.FC<{ plan: Plan | null | undefined }> = ({ plan: p }) => {
  if (!p) return null;
  const states = Object.entries(p.left_by_state || {});
  const withPeople = p.centres.filter(c => c.left > 0);
  return (
    <section className="rounded-2xl overflow-hidden border border-slate-800 bg-slate-900 shadow-sm">
      <div className="px-5 py-4 text-white" style={{ background: BANNER }}>
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="flex items-start gap-3 min-w-0">
            <span className="h-10 w-10 rounded-xl bg-white/15 flex items-center justify-center shrink-0"><Icon name="share_location" className="text-[22px]" /></span>
            <div className="min-w-0">
              <div className="text-[11px] uppercase tracking-wider text-white/70 font-semibold">CSPs near DCs plan · next 7 days</div>
              <h3 className="text-xl font-semibold leading-tight mt-0.5">Two campaigns a day around the SBI CSP centres</h3>
              <p className="text-[13px] text-white/80 mt-1 max-w-2xl">
                Shops at the 40 SBI-allocated CSP centres in the DCs' districts. Send{' '}
                <b className="text-white">Haryana at {p.send_times.haryana}</b> and <b className="text-white">Punjab at {p.send_times.punjab}</b>,
                up to {num(p.cap)} people each; no campaign on Sunday. In Choose campaign audience, pick <b className="text-white">CSPs near DCs</b> and the state.
              </p>
            </div>
          </div>
          <div className="grid grid-cols-3 gap-2 shrink-0">
            {[{ k: 'To message', v: num(p.left), icon: 'groups' },
              { k: 'This week', v: num(p.week_people), icon: 'send' },
              { k: 'Leads expected', v: tenth(p.week_expect.lead), icon: 'star' }].map(t => (
              <div key={t.k} className="rounded-xl bg-white/10 px-3 py-2 min-w-[96px]">
                <div className="flex items-center gap-1 text-[10.5px] uppercase tracking-wider text-white/70"><Icon name={t.icon} className="text-[14px]" />{t.k}</div>
                <div className="text-[20px] font-bold tabular-nums leading-tight mt-0.5">{t.v}</div>
              </div>
            ))}
          </div>
        </div>
        {states.length > 0 && (
          <div className="mt-3 flex flex-wrap gap-2">
            {states.map(([s, n]) => (
              <span key={s} className="rounded-full bg-white/15 px-2.5 py-0.5 text-[12px] font-semibold">{s}: {num(n)} left</span>
            ))}
          </div>
        )}
      </div>
      <div className="p-4">
        {p.days.length ? (
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
            {p.days.map((d, i) => <DayCard key={d.date} d={d} first={i === 0} cap={p.cap} />)}
          </div>
        ) : (
          <div className="text-sm text-slate-400 p-2">Everyone found near the centres has been messaged. Run more CSPs near DCs jobs to find new shops.</div>
        )}
        {withPeople.length > 0 && (
          <details className="mt-4 group">
            <summary className="cursor-pointer select-none text-[12.5px] font-semibold text-slate-300 hover:text-slate-100 inline-flex items-center gap-1">
              <Icon name="list" className="text-[16px]" /> Every centre with people left ({withPeople.length} of {p.centres.length})
            </summary>
            <div className="mt-2 overflow-x-auto">
              <table className="w-full text-[12.5px]">
                <thead className="text-[10.5px] uppercase tracking-wider text-slate-500">
                  <tr>{['Centre', 'CISBI code', 'PIN', 'Sub-district', 'District', 'State', 'People left'].map(h => <th key={h} className="text-left px-2 py-1.5 font-semibold">{h}</th>)}</tr>
                </thead>
                <tbody className="[&>tr]:border-t [&>tr]:border-slate-800">
                  {withPeople.map(c => (
                    <tr key={`${c.code}-${c.centre}`}>
                      <td className="px-2 py-1.5 text-slate-100 font-medium">{c.centre}</td>
                      <td className="px-2 py-1.5 text-slate-400">{(c.code || '').replace('CISBI ', '')}</td>
                      <td className="px-2 py-1.5 text-slate-300 tabular-nums">{c.pincode || '—'}</td>
                      <td className="px-2 py-1.5 text-slate-300">{c.subdistrict || '—'}</td>
                      <td className="px-2 py-1.5 text-slate-300">{c.district || '—'}</td>
                      <td className="px-2 py-1.5 text-slate-300">{c.state || '—'}</td>
                      <td className="px-2 py-1.5 text-slate-100 font-semibold tabular-nums">{num(c.left)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </details>
        )}
      </div>
    </section>
  );
};
