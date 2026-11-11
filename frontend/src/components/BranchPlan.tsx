import React from 'react';
import type { BranchDay, BranchPlan as Plan, Stage } from '../api/insights';

/**
 * A campaign a day for the next week, around our SBI branches (11 Nov 2026):
 * for each day, the branch whose area to message, how many people and which
 * kinds of business, and what the agent expects at each step. Below, every
 * branch with the people left near it and how its earlier campaigns did.
 *
 * The banner keeps the app's deep teal in both themes; the rest uses the
 * theme ramps.
 */

const Icon: React.FC<{ name: string; className?: string }> = ({ name, className = '' }) =>
  <span className={`material-symbols-outlined ${className}`} aria-hidden="true">{name}</span>;

const num = (v: number) => v.toLocaleString('en-IN');
const tenth = (v: number) => (v >= 10 ? Math.round(v).toLocaleString('en-IN') : v.toFixed(1));
const pct = (v: number) => `${(v * 100).toFixed(v < 0.01 ? 2 : 1)}%`;

const STEPS: { key: Stage; label: string; colour: string }[] = [
  { key: 'engaged', label: 'Reply or tap', colour: '#38bdf8' },
  { key: 'interested', label: 'Start applying', colour: '#34d399' },
  { key: 'qualified', label: 'Qualify', colour: '#a78bfa' },
  { key: 'lead', label: 'Leads', colour: '#f9ab10' },
];
const TEAL = 'linear-gradient(120deg, #0a3543 0%, #16435a 55%, #1d5a6e 100%)';

/** One day's card: date, branch(es), people, and the expected funnel. */
const DayCard: React.FC<{ d: BranchDay; first: boolean; daily: number }> = ({ d, first, daily }) => {
  const [day, ...rest] = d.label.split(', ');
  return (
    <div className={`rounded-xl border p-3.5 min-w-0 flex flex-col ${first
      ? 'border-amber-500/60 bg-amber-50/5 ring-1 ring-amber-500/30' : 'border-slate-800 bg-slate-950/60'}`}>
      <div className="flex items-center justify-between gap-2">
        <div className="min-w-0">
          <div className={`text-[11px] uppercase tracking-wider font-bold ${first ? 'text-amber-400' : 'text-slate-500'}`}>{day}</div>
          <div className="text-[12px] text-slate-400">{rest.join(', ')}</div>
        </div>
        <span className="shrink-0 inline-flex items-center gap-1 rounded-full bg-slate-800 px-2 py-0.5 text-[11px] font-semibold text-slate-200 tabular-nums">
          <Icon name="group" className="text-[14px]" />{num(d.people)}
        </span>
      </div>
      <div className="mt-2.5 space-y-2 flex-1">
        {d.slots.map(s => (
          <div key={s.branch_code} className="min-w-0">
            <div className="flex items-baseline gap-1.5 min-w-0">
              <Icon name="account_balance" className="text-[15px] text-sky-400 self-center" />
              <span className="text-[13.5px] font-semibold text-slate-100 truncate">{s.branch_name}</span>
              <span className="text-[11px] text-slate-500 shrink-0">{s.pincode}</span>
            </div>
            <div className="text-[11px] text-slate-500 truncate">
              {s.district || '—'} · {num(s.people)} people
            </div>
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
      <div className="mt-3 pt-2.5 border-t border-slate-800 space-y-1">
        {STEPS.map(st => (
          <div key={st.key} className="flex items-center gap-2 text-[11px]">
            <span className="w-[84px] shrink-0 text-slate-400 truncate">{st.label}</span>
            <div className="flex-1 h-1.5 rounded-full bg-slate-800 overflow-hidden">
              <div className="h-full rounded-full" style={{
                width: `${Math.min(100, Math.max(3, (d.expect[st.key] / Math.max(daily * 0.25, 1)) * 100))}%`, background: st.colour,
              }} />
            </div>
            <span className={`w-8 text-right tabular-nums font-semibold ${st.key === 'lead' ? 'text-amber-400' : 'text-slate-200'}`}>
              {tenth(d.expect[st.key])}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
};

export const BranchPlanCard: React.FC<{ plan: Plan | null | undefined }> = ({ plan: p }) => {
  if (!p) return null;
  const leads = p.week_expect.lead;
  const maxLeft = Math.max(1, ...p.branches.map(b => b.left));
  return (
    <section className="rounded-xl border border-slate-800 bg-slate-900 shadow-sm overflow-hidden">
      {/* Banner */}
      <div className="px-5 py-4 text-white" style={{ background: TEAL }}>
        <div className="flex flex-col lg:flex-row lg:items-center gap-4">
          <div className="flex items-start gap-3 flex-1 min-w-0">
            <span className="h-10 w-10 shrink-0 rounded-xl bg-white/15 flex items-center justify-center">
              <Icon name="account_balance" className="text-[22px]" />
            </span>
            <div className="min-w-0">
              <div className="text-[11px] uppercase tracking-[0.14em] font-semibold" style={{ color: '#f9ab10' }}>SBI branch plan · next 7 days</div>
              <h3 className="text-xl font-semibold leading-tight mt-0.5">One campaign a day, around our branches</h3>
              <p className="text-[12.5px] text-white/75 mt-1 max-w-2xl">
                Each shop counts for its nearest SBI branch within {p.max_km} km. Branches whose people answered come
                first; a day with too few people left near one branch tops up from the next. Send at <b className="text-white">{p.send_time}</b>.
              </p>
            </div>
          </div>
          <div className="grid grid-cols-3 gap-2 shrink-0 lg:w-[420px]">
            {[
              { k: 'Each day', v: num(p.daily), sub: 'people', icon: 'send' },
              { k: 'This week', v: num(p.week_people), sub: `of ${num(p.left_near_branches)} left`, icon: 'groups' },
              { k: 'Leads expected', v: tenth(leads), sub: 'this week', icon: 'workspace_premium' },
            ].map(t => (
              <div key={t.k} className="rounded-xl bg-white/10 px-3 py-2.5 min-w-0">
                <div className="flex items-center gap-1 text-[10.5px] text-white/70"><Icon name={t.icon} className="text-[14px]" />{t.k}</div>
                <div className="text-xl font-semibold tabular-nums mt-0.5">{t.v}</div>
                <div className="text-[10.5px] text-white/60 truncate">{t.sub}</div>
              </div>
            ))}
          </div>
        </div>
      </div>

      <div className="p-5 space-y-5">
        {p.days.length ? (
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4 2xl:grid-cols-7">
            {p.days.map((d, i) => <DayCard key={d.date} d={d} first={i === 0} daily={p.daily} />)}
          </div>
        ) : (
          <div className="rounded-lg border border-dashed border-slate-700 p-6 text-center text-sm text-slate-400">
            Nobody is left to message within {p.max_km} km of our SBI branches. Add scraping targets near them.
          </div>
        )}

        <p className="text-[12px] text-slate-400 leading-relaxed">
          <Icon name="info" className="text-[15px] text-sky-400 align-[-3px] mr-1" />
          {p.for_goal > p.daily
            ? <>The goal would need about <b className="text-slate-200">{num(p.for_goal)}</b> messages a day at today's rate; {num(p.cap)} is the most one campaign sends without a second person's approval. </>
            : <>{num(p.daily)} a day is enough for the goal's daily share at today's rate. </>}
          Expected numbers come from {num(p.messages_sent)} messages so far: a branch's own results count, weighed against the
          average until it has enough of its own, so a lucky first campaign is not over-promised.
        </p>

        {/* Every branch */}
        <div className="rounded-xl border border-slate-800 overflow-hidden">
          <div className="px-4 py-2.5 bg-slate-950/60 text-[11px] uppercase tracking-wider font-semibold text-slate-500 flex items-center gap-2">
            <Icon name="pin_drop" className="text-[15px]" /> Every branch, best first
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-[12.5px]">
              <thead>
                <tr className="text-left text-[11px] text-slate-500 border-b border-slate-800">
                  <th className="px-4 py-2 font-semibold">Branch</th>
                  <th className="px-3 py-2 font-semibold">People left</th>
                  <th className="px-3 py-2 font-semibold text-right">Messaged</th>
                  <th className="px-3 py-2 font-semibold text-right">Replied</th>
                  <th className="px-3 py-2 font-semibold text-right">Started applying</th>
                  <th className="px-3 py-2 font-semibold text-right">Leads</th>
                  <th className="px-4 py-2 font-semibold text-right" title={`Ranked by this step, as Campaign Insights judges campaigns`}>Expected rate · {p.judged_on_label.split(" (")[0]}</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800">
                {p.branches.map((b, i) => (
                  <tr key={b.branch_code} className="hover:bg-slate-800/40">
                    <td className="px-4 py-2.5">
                      <div className="flex items-center gap-2 min-w-0">
                        <span className={`h-6 w-6 shrink-0 rounded-md flex items-center justify-center text-[11px] font-bold ${i < 3
                          ? 'bg-amber-500/20 text-amber-400' : 'bg-slate-800 text-slate-400'}`}>{i + 1}</span>
                        <div className="min-w-0">
                          <div className="font-semibold text-slate-100 truncate">{b.branch_name}
                            {!b.tried && <span className="ml-1.5 rounded-full bg-sky-500/15 text-sky-300 border border-sky-500/30 px-1.5 py-px text-[10px] font-semibold align-middle">new</span>}
                          </div>
                          <div className="text-[11px] text-slate-500 truncate">{b.district || '—'} · {b.pincode} · {b.branch_code}</div>
                        </div>
                      </div>
                    </td>
                    <td className="px-3 py-2.5 min-w-[150px]">
                      <div className="flex items-center gap-2">
                        <div className="flex-1 h-2 rounded-full bg-slate-800 overflow-hidden">
                          <div className="h-full rounded-full bg-emerald-500" style={{ width: `${(b.left / maxLeft) * 100}%` }} />
                        </div>
                        <span className="w-10 text-right tabular-nums text-slate-200 font-semibold">{num(b.left)}</span>
                      </div>
                    </td>
                    <td className="px-3 py-2.5 text-right tabular-nums text-slate-300">{num(b.sent)}</td>
                    <td className="px-3 py-2.5 text-right tabular-nums text-slate-300">{num(b.results.engaged)}</td>
                    <td className="px-3 py-2.5 text-right tabular-nums text-slate-300">{num(b.results.interested)}</td>
                    <td className="px-3 py-2.5 text-right tabular-nums font-semibold text-amber-400">{num(b.results.lead)}</td>
                    <td className="px-4 py-2.5 text-right tabular-nums text-slate-200">{pct(b.rates[p.judged_on])}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </section>
  );
};
