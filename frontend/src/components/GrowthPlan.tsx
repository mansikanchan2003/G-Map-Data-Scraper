import React, { useEffect, useState } from 'react';
import { getApiBaseUrl } from '../api';
import {
  fetchGrowthPlan, setRevenueGoal, type BusinessSummary, type CreativeRow, type GrowthPlan as Plan, type GrowthRow,
} from '../api/insights';
import { formatDateTime } from '../utils/datetime';

/**
 * The lead goal at the top of Campaign Insights: leads so far against the
 * target, what to do today, where people drop out on the way, who to call,
 * where and whom to message next, and what the templates that worked had in
 * common. The template agents are given the same plan each time they write.
 *
 * Colours come from the theme ramps (slate, sky, emerald, rose, amber,
 * purple), which the light theme redefines, so the page reads in both. The
 * goal banner keeps Eko's own teal and gold in either theme.
 */

const pct = (v: number | null | undefined) => (v == null ? '—' : `${(v * 100).toFixed(v > 0 && v < 0.1 ? 1 : 0)}%`);
const num = (v: number | null | undefined) => (v == null ? '—' : v.toLocaleString('en-IN'));
const lakh = (v: number | null | undefined) => (v == null ? '—' : `₹${(v / 1e5).toFixed(1)} L`);
const inr = (v: number | null | undefined) => (v == null ? '—' : `₹${Math.round(v).toLocaleString('en-IN')}`);
const Icon: React.FC<{ name: string; className?: string }> = ({ name, className = '' }) =>
  <span className={`material-symbols-outlined ${className}`}>{name}</span>;

const mediaUrl = (headerContent: string | null) => {
  try {
    const d = JSON.parse(headerContent || '');
    return d.media_id ? `${getApiBaseUrl()}/api/v1/whatsapp/media/${d.media_id}` : null;
  } catch { return null; }
};

// ---------------------------------------------------------------------------
// Evidence: how firm a result is, and which way it went.
// ---------------------------------------------------------------------------

const Chip: React.FC<{ c: string; direction?: string; campaigns?: number }> = ({ c, direction, campaigns }) => {
  const firm = c === 'strong' || c === 'likely';
  const word = c === 'strong' ? 'Proven' : 'Likely';
  let label = 'Too early', cls = 'bg-amber-950 text-amber-300 border-amber-800/60', title = 'Not enough people yet to tell.';
  if (firm && direction === 'better') { label = `${word} better`; cls = 'bg-emerald-950 text-emerald-300 border-emerald-800/60'; title = 'Better than the rest, beyond chance.'; }
  else if (firm && direction === 'worse') { label = `${word} worse`; cls = 'bg-rose-950 text-rose-300 border-rose-800/60'; title = 'Worse than the rest, beyond chance.'; }
  else if (c === 'no_difference') { label = 'No difference'; cls = 'bg-slate-950 text-slate-400 border-slate-800'; title = 'No clearer than the rest.'; }
  else if (c === 'untried') { label = 'Not tried'; cls = 'bg-purple-950 text-purple-300 border-purple-800/60'; title = 'Never messaged: worth a small test.'; }
  return (
    <span className="inline-flex items-center gap-1 whitespace-nowrap">
      <span title={title} className={`px-2 py-0.5 rounded-full border text-[10.5px] font-semibold ${cls}`}>{label}</span>
      {campaigns === 1 && c !== 'untried' && (
        <span className="text-[10.5px] text-slate-500"
          title="All from one campaign: its place, timing and template went together, so which of them mattered cannot be told yet.">
          1 campaign
        </span>
      )}
    </span>
  );
};

const Card: React.FC<{ icon: string; title: string; subtitle?: React.ReactNode; tint?: string; children: React.ReactNode; className?: string }> =
  ({ icon, title, subtitle, tint = 'bg-sky-950 text-sky-300', children, className = '' }) => (
  <section className={`rounded-xl border border-slate-800 bg-slate-900 shadow-sm ${className}`}>
    <header className="flex items-start gap-3 px-5 pt-4 pb-3">
      <span className={`h-9 w-9 shrink-0 rounded-lg flex items-center justify-center ${tint}`}><Icon name={icon} className="text-[20px]" /></span>
      <div className="min-w-0">
        <h3 className="text-[15px] font-semibold text-slate-100 leading-tight">{title}</h3>
        {subtitle && <p className="text-xs text-slate-500 mt-0.5">{subtitle}</p>}
      </div>
    </header>
    <div className="px-5 pb-5">{children}</div>
  </section>
);

// ---------------------------------------------------------------------------
// The goal banner
// ---------------------------------------------------------------------------

const Ring: React.FC<{ value: number; target: number }> = ({ value, target }) => {
  const r = 52, c = 2 * Math.PI * r;
  const done = Math.min(1, value / Math.max(target, 1));
  return (
    <div className="relative h-36 w-36 shrink-0">
      <svg viewBox="0 0 120 120" className="h-full w-full -rotate-90">
        <circle cx="60" cy="60" r={r} fill="none" stroke="rgba(255,255,255,0.14)" strokeWidth="10" />
        <circle cx="60" cy="60" r={r} fill="none" stroke="#f9ab10" strokeWidth="10" strokeLinecap="round"
          strokeDasharray={`${Math.max(done * c, value ? 0 : 0.001)} ${c}`} />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center text-white">
        <div className="text-4xl font-bold tabular-nums leading-none">{value}</div>
        <div className="text-[11px] mt-1 text-white/70">of {target} leads</div>
      </div>
    </div>
  );
};

const STAGE_SHORT: Record<string, string> = {
  engaged: 'Replied or tapped', interested: 'Started applying', qualified: 'Qualified', lead: 'Submitted documents',
};

const Goal: React.FC<{ plan: Plan }> = ({ plan }) => {
  const g = plan.goal;
  const deadline = new Date(`${g.deadline}T00:00:00+05:30`).toLocaleDateString('en-IN', { day: 'numeric', month: 'long' });
  const stages = plan.stages;
  const stat = (icon: string, value: React.ReactNode, label: string) => (
    <div className="rounded-lg bg-white/10 px-4 py-3 min-w-[110px]">
      <div className="flex items-center gap-1.5 text-white/70 text-[11px]"><Icon name={icon} className="text-[15px]" />{label}</div>
      <div className="text-2xl font-semibold text-white tabular-nums mt-0.5">{value}</div>
    </div>
  );
  return (
    <section className="rounded-2xl overflow-hidden shadow-md text-white"
      style={{ background: 'linear-gradient(120deg, #0a3543 0%, #16435a 55%, #1d5a6e 100%)' }}>
      <div className="p-6 flex flex-col lg:flex-row lg:items-center gap-6">
        <Ring value={g.leads} target={g.target} />
        <div className="flex-1 min-w-0">
          <div className="text-[11px] uppercase tracking-[0.14em] font-semibold flex flex-wrap items-center gap-2" style={{ color: '#f9ab10' }}>
            {g.label} goal · {g.target} leads
            <span className="normal-case tracking-normal font-medium text-[10.5px] px-2 py-0.5 rounded-full bg-white/10 text-white/80">
              <Icon name="smart_toy" className="text-[13px] align-[-2px] mr-0.5" />set by the agent from {g.basis}
            </span>
          </div>
          <h2 className="text-2xl font-semibold mt-1 leading-snug">
            {g.still_needed ? <>{g.still_needed} more lead{g.still_needed === 1 ? '' : 's'} by {deadline}</> : <>Goal reached 🎉</>}
          </h2>
          <p className="text-sm text-white/75 mt-1 max-w-2xl">
            A lead is someone a campaign reached who submitted their documents.{' '}
            {g.leads_per_1000 != null
              ? <>So far {g.leads_per_1000} per 1,000 messages{g.messages_needed ? <>, so about {num(g.messages_needed)} more messages at this rate</> : null}.</>
              : <>None yet from {num(g.messages_sent)} messages, so the plan works from the steps before a lead.</>}
          </p>
          <div className="flex flex-wrap gap-3 mt-4">
            {stat('event', g.days_left, 'days left')}
            {stat('flag', g.still_needed, 'still needed')}
            {stat('speed', g.per_day_needed ?? '—', 'needed per day')}
          </div>
        </div>
        <div className="lg:w-64 shrink-0">
          <div className="text-[11px] uppercase tracking-wider text-white/60 font-semibold mb-2">The way to a lead</div>
          <ol className="space-y-1.5">
            {stages.map((s, i) => (
              <li key={s.key} className="flex items-center gap-2.5">
                <span className={`h-6 w-6 rounded-full flex items-center justify-center text-[11px] font-bold ${i === stages.length - 1 ? 'text-[#0a3543]' : 'bg-white/15 text-white'}`}
                  style={i === stages.length - 1 ? { background: '#f9ab10' } : undefined}>{i + 1}</span>
                <span className="flex-1 text-sm text-white/85 truncate" title={s.label}>{STAGE_SHORT[s.key] || s.label}</span>
                <span className="text-sm font-semibold tabular-nums">{num(s.count)}</span>
              </li>
            ))}
          </ol>
        </div>
      </div>
      {g.reasoning?.length > 0 && (
        <div className="px-6 py-4 bg-black/15 border-t border-white/10">
          <div className="text-[11px] uppercase tracking-wider text-white/60 font-semibold mb-2">Why this goal</div>
          <ol className="grid gap-x-8 gap-y-1.5 md:grid-cols-2 text-[13px] text-white/85">
            {g.reasoning.map((r, i) => (
              <li key={i} className="flex gap-2"><span className="text-white/45 tabular-nums">{i + 1}.</span><span>{r}</span></li>
            ))}
          </ol>
        </div>
      )}
      {g.lead_list.length > 0 && (
        <div className="px-6 py-2.5 bg-black/15 text-xs text-white/80">
          <Icon name="verified" className="text-[15px] align-middle mr-1" />
          Leads: {g.lead_list.map(l => `${l.name || l.phone} (${formatDateTime(l.submitted_at)})`).join(' · ')}
        </div>
      )}
    </section>
  );
};

// ---------------------------------------------------------------------------
// From a lead to revenue
// ---------------------------------------------------------------------------

const BASIS: Record<string, string> = { actual: '', projected: 'projected', estimated: 'estimated' };

const money = (v: number) => (v >= 1e7 ? `₹${+(v / 1e7).toFixed(2)} Cr` : `₹${(v / 1e5).toFixed(1)} L`);

/** The month's revenue against the team's goal, and setting that goal. */
const RevenueGoal: React.FC<{ plan: Plan; onSaved: () => void }> = ({ plan, onSaved }) => {
  const g = plan.goal;
  const r = g.revenue;
  const [editing, setEditing] = useState(false);
  const [value, setValue] = useState(r ? String(r.goal_inr / 1e5) : '');
  // The month the revenue is to be reached by; this month unless a goal is set.
  const [month, setMonth] = useState(r?.month || g.start.slice(0, 7));
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const save = async (lakhs: number | null) => {
    setSaving(true); setError(null);
    try {
      // Moving a goal to another month clears it from the old one.
      if (r && r.month !== month) await setRevenueGoal(r.month, null);
      await setRevenueGoal(month, lakhs ? Math.round(lakhs * 1e5) : null);
      setEditing(false); onSaved();
    }
    catch (e: any) { setError(e.message); }
    finally { setSaving(false); }
  };
  const editor = (
    <div className="flex flex-wrap items-center gap-2">
      <span className="text-sm text-slate-400">₹</span>
      <input value={value} onChange={e => setValue(e.target.value.replace(/[^\d.]/g, ''))} inputMode="decimal" autoFocus
        className="h-9 w-28 px-3 rounded-lg border border-slate-800 bg-slate-900 text-sm text-slate-100 outline-none focus:border-sky-500" />
      <span className="text-sm text-slate-400">lakh a month (100 = ₹1 Cr), by the end of</span>
      <input type="month" value={month} min={g.start.slice(0, 7)} onChange={e => setMonth(e.target.value)}
        className="h-9 px-2 rounded-lg border border-slate-800 bg-slate-900 text-sm text-slate-100 outline-none focus:border-sky-500" />
      <button onClick={() => save(parseFloat(value) || null)} disabled={saving}
        className="h-9 px-4 rounded-lg bg-emerald-500 text-white text-sm font-semibold disabled:opacity-50">{saving ? 'Saving…' : 'Save'}</button>
      {r && <button onClick={() => save(null)} disabled={saving} className="h-9 px-3 rounded-lg text-sm text-slate-400 hover:text-rose-300">Clear</button>}
      <button onClick={() => setEditing(false)} className="h-9 px-3 rounded-lg text-sm text-slate-400 hover:text-slate-200">Cancel</button>
      {error && <span className="text-xs text-rose-300">{error}</span>}
    </div>
  );
  if (!r) {
    return (
      <div className="rounded-lg border border-dashed border-slate-700 p-4 mb-5 flex flex-wrap items-center justify-between gap-3">
        <div className="text-sm text-slate-400">No revenue goal set. Set one (a monthly revenue, and the month to reach it by) and the agent works its lead goal out from it.</div>
        {editing ? editor : (
          <button onClick={() => setEditing(true)} className="h-9 px-3.5 rounded-lg border border-slate-800 bg-slate-900 text-sm text-slate-300 hover:bg-slate-800 flex items-center gap-1.5">
            <Icon name="flag" className="text-[18px]" />Set a revenue goal</button>
        )}
      </div>
    );
  }
  const done = Math.min(100, r.share * 100);
  return (
    <div className="rounded-xl border border-emerald-800/60 bg-emerald-950 p-4 mb-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="text-[11px] uppercase tracking-wider font-semibold text-emerald-300">
            Revenue goal · by {r.deadline_label} · {r.months_left} month{r.months_left === 1 ? '' : 's'} left
          </div>
          <div className="flex flex-wrap items-baseline gap-x-3 mt-0.5">
            <span className="text-2xl font-bold text-slate-100 tabular-nums">{money(r.goal_inr)} <span className="text-sm font-medium text-slate-400">a month</span></span>
            <span className="text-sm text-slate-400">{r.baseline_month} {r.expected_basis} {money(r.expected_inr)} · {Math.round(r.share * 100)}%</span>
            {r.gap_inr > 0
              ? <span className="text-sm font-semibold text-rose-300">{money(r.gap_inr)} short</span>
              : <span className="text-sm font-semibold text-emerald-300">on course</span>}
          </div>
        </div>
        {!editing && (
          <button onClick={() => { setValue(String(r.goal_inr / 1e5)); setMonth(r.month); setEditing(true); }}
            className="h-8 px-3 rounded-lg border border-slate-800 bg-slate-900 text-xs text-slate-300 hover:bg-slate-800 flex items-center gap-1">
            <Icon name="edit" className="text-[16px]" />Change</button>
        )}
      </div>
      {editing && <div className="mt-3">{editor}</div>}
      <div className="h-2.5 rounded-full bg-slate-800 mt-3 overflow-hidden">
        <div className="h-full rounded-full bg-emerald-500" style={{ width: `${done}%` }} />
      </div>
      {r.gap_inr > 0 && (
        <div className="grid gap-3 md:grid-cols-2 mt-4 text-[13px]">
          <div className="rounded-lg bg-slate-900 border border-slate-800 p-3">
            <div className="font-semibold text-slate-100 flex items-center gap-1.5"><Icon name="today" className="text-[18px] text-amber-300" />By {r.deadline_label}</div>
            <p className="text-slate-400 mt-1">Mostly the existing CSPs: <b className="text-slate-200">{num(r.extra_txns)} more transactions a month</b>
              {r.extra_txns_share ? ` (+${Math.round(r.extra_txns_share * 100)}%)` : ''}, about {r.extra_txns_per_csp} more each. A CSP going live now
              adds only about ₹{num(r.new_csp_by_then_inr)} a month by then.</p>
          </div>
          <div className="rounded-lg bg-slate-900 border border-slate-800 p-3">
            <div className="font-semibold text-slate-100 flex items-center gap-1.5"><Icon name="update" className="text-[18px] text-sky-300" />For good</div>
            <p className="text-slate-400 mt-1">About <b className="text-slate-200">{r.csps_needed} more established CSPs</b>: {r.leads_needed} leads,
              so <b className="text-slate-200">{r.leads_per_month} a month</b> until {r.deadline_label}. That is AutoGMap's part.</p>
          </div>
        </div>
      )}
    </div>
  );
};

const Business: React.FC<{ b: BusinessSummary; plan: Plan; onSaved: () => void }> = ({ b, plan, onSaved }) => {
  const months = b.months.filter(m => m.revenue_inr);
  const top = Math.max(1, ...months.map(m => m.revenue_inr || 0));
  const low = Math.min(...months.map(m => m.revenue_inr || 0));
  const ob = b.onboarding;
  const steps = [
    { icon: 'campaign', title: 'Lead', text: 'AutoGMap reaches a business; it qualifies and submits documents.' },
    { icon: 'fact_check', title: 'Onboarding', text: `CAT-1, CAT-2, SBI branch, RBO and LHO approvals. ${ob.go_live_rate != null ? `${Math.round(ob.go_live_rate * 100)}% of decided go live.` : ''}` },
    { icon: 'rocket_launch', title: 'Go live', text: `${b.csps_live ?? '—'} CSPs active now${b.csps_inactive ? `, ${b.csps_inactive} inactive` : ''}.` },
    { icon: 'trending_up', title: 'Ramp up', text: b.new_csp_ramp.length ? `A new CSP: ${b.new_csp_ramp.map(r => `~${r.median_txns}`).join(' → ')} transactions in its first months.` : 'New CSPs start slowly.' },
    { icon: 'payments', title: 'Revenue', text: `About ₹${b.revenue_per_txn ?? '—'} a transaction; an established CSP ~${inr(b.mature_csp.revenue_inr)} a month.` },
  ];
  const ch = b.latest_change;
  return (
    <Card icon="account_balance" title="From a lead to revenue" tint="bg-emerald-950 text-emerald-300"
      subtitle={<>How Eko earns from a CSP, from Tara and the onboarding sheet{b.exported_at ? <> · updated {formatDateTime(b.exported_at)}</> : null}. The agent sets its goal from these numbers.</>}>
      <RevenueGoal plan={plan} onSaved={onSaved} />
      <ol className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
        {steps.map((s, i) => (
          <li key={s.title} className="relative rounded-lg border border-slate-800 bg-slate-950/60 p-3.5">
            <div className="flex items-center gap-2">
              <span className="h-7 w-7 rounded-full bg-emerald-950 text-emerald-300 flex items-center justify-center"><Icon name={s.icon} className="text-[16px]" /></span>
              <span className="text-[11px] font-semibold text-slate-500">{i + 1}</span>
              <span className="text-sm font-semibold text-slate-100">{s.title}</span>
            </div>
            <p className="text-[12.5px] text-slate-400 mt-2 leading-relaxed">{s.text}</p>
          </li>
        ))}
      </ol>

      <div className="grid gap-6 lg:grid-cols-[1.4fr_1fr] mt-6">
        <div className="min-w-0">
          <div className="text-xs font-semibold uppercase tracking-wider text-slate-500 mb-3">Revenue and CSPs by month</div>
          <div className="flex items-end gap-2 h-44">
            {months.map(m => {
              // Bars start from a little under the lowest month, so month-to-month change shows.
              const floor = low * 0.9;
              const h = 18 + ((m.revenue_inr! - floor) / Math.max(top - floor, 1)) * 82;
              return (
                <div key={m.month} className="flex-1 min-w-0 flex flex-col items-center justify-end h-full">
                  <span className="text-[11px] font-semibold text-slate-200 tabular-nums">{lakh(m.revenue_inr)}</span>
                  <div className={`w-full max-w-[56px] rounded-t-md mt-1 ${m.revenue_basis === 'actual' ? 'bg-emerald-500' : 'bg-emerald-500/40 border border-dashed border-emerald-500'}`}
                    style={{ height: `${h}%` }} title={`${m.label}: ${inr(m.revenue_inr)}${BASIS[m.revenue_basis || ''] ? ` (${BASIS[m.revenue_basis || '']})` : ''}`} />
                  <span className="text-[11px] text-slate-400 mt-1.5">{m.label.split(' ')[0]}</span>
                  <span className="text-[10.5px] text-slate-500 tabular-nums">{num(m.active_csps)} CSPs</span>
                  <span className={`text-[10.5px] tabular-nums ${m.new_csps ? 'text-sky-300 font-semibold' : 'text-slate-600'}`}>
                    {m.new_csps == null ? '—' : `+${m.new_csps} new`}
                  </span>
                </div>
              );
            })}
          </div>
          <div className="text-[11px] text-slate-500 mt-2">Faded bars are estimated or projected. “New” is CSPs that went live that month.</div>
        </div>
        <div className="min-w-0 space-y-3">
          {ch && (
            <div className="rounded-lg border border-sky-800/60 bg-sky-950 p-3.5 text-[13px] text-slate-200">
              <div className="font-semibold text-sky-300 flex items-center gap-1.5"><Icon name="insights" className="text-[18px]" />What moves revenue</div>
              <p className="mt-1 leading-relaxed">
                {ch.from} → {ch.to}: revenue {ch.revenue_change_inr >= 0 ? 'rose' : 'fell'} by {inr(Math.abs(ch.revenue_change_inr))} while
                the network changed by {ch.csp_change >= 0 ? '+' : ''}{ch.csp_change} CSPs. New CSPs brought {inr(ch.from_new_csps_inr)}.
                In a single month, revenue follows the existing CSPs' activity; new CSPs add to it over the months they take to ramp up.
              </p>
            </div>
          )}
          <div className="rounded-lg border border-slate-800 bg-slate-950/60 p-3.5">
            <div className="text-xs font-semibold text-slate-400 mb-2">Onboarding so far</div>
            <div className="flex h-2.5 rounded-full overflow-hidden bg-slate-800">
              <div className="bg-emerald-500" style={{ width: `${((ob.went_live || 0) / Math.max(ob.applicants || 1, 1)) * 100}%` }} title="Went live" />
              <div className="bg-amber-400" style={{ width: `${((ob.in_progress || 0) / Math.max(ob.applicants || 1, 1)) * 100}%` }} title="In progress" />
              <div className="bg-rose-500" style={{ width: `${((ob.rejected || 0) / Math.max(ob.applicants || 1, 1)) * 100}%` }} title="Rejected" />
            </div>
            <div className="flex flex-wrap gap-x-4 gap-y-1 mt-2 text-[12px] text-slate-400">
              <span><span className="inline-block h-2 w-2 rounded-full bg-emerald-500 mr-1" />{ob.went_live} live</span>
              <span><span className="inline-block h-2 w-2 rounded-full bg-amber-400 mr-1" />{ob.in_progress} in progress</span>
              <span><span className="inline-block h-2 w-2 rounded-full bg-rose-500 mr-1" />{ob.rejected} rejected</span>
              <span className="text-slate-500">of {ob.applicants} applicants</span>
            </div>
            {ob.top_rejections.length > 0 && (
              <div className="text-[11.5px] text-slate-500 mt-2">Most rejected: {ob.top_rejections.slice(0, 2).map(([s, n]) => `${s.toLowerCase()} (${n})`).join(', ')}.</div>
            )}
          </div>
          {b.this_month_by_state.length > 0 && (
            <div className="rounded-lg border border-slate-800 bg-slate-950/60 p-3.5">
              <div className="text-xs font-semibold text-slate-400 mb-2">The onboarding team's targets this month</div>
              <ul className="space-y-1.5">
                {b.this_month_by_state.filter(r => r.state !== 'Total' && r.target).sort((a, c) => (c.target - c.leads) - (a.target - a.leads)).slice(0, 5).map(r => (
                  <li key={r.state} className="flex items-center gap-2 text-[12.5px]">
                    <span className="w-24 truncate text-slate-200">{r.state}</span>
                    <div className="flex-1 h-1.5 rounded-full bg-slate-800 overflow-hidden">
                      <div className="h-full bg-sky-500 rounded-full" style={{ width: `${Math.min(100, (r.leads / Math.max(r.target, 1)) * 100)}%` }} />
                    </div>
                    <span className="text-slate-400 tabular-nums w-24 text-right">{r.leads} of {r.target} leads</span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      </div>
    </Card>
  );
};

// ---------------------------------------------------------------------------
// What to do now
// ---------------------------------------------------------------------------

const IMPACT: Record<string, { bar: string; tag: string; tint: string; label: string }> = {
  high: { bar: 'bg-emerald-500', tag: 'bg-emerald-950 text-emerald-300 border-emerald-800/60', tint: 'bg-emerald-950 text-emerald-300', label: 'High impact' },
  medium: { bar: 'bg-sky-500', tag: 'bg-sky-950 text-sky-300 border-sky-800/60', tint: 'bg-sky-950 text-sky-300', label: 'Medium impact' },
  low: { bar: 'bg-slate-600', tag: 'bg-slate-950 text-slate-400 border-slate-800', tint: 'bg-slate-950 text-slate-400', label: 'Low impact' },
};

const NextSteps: React.FC<{ plan: Plan }> = ({ plan }) => (
  <Card icon="checklist" title="What to do next" tint="bg-emerald-950 text-emerald-300"
    subtitle="Most effective first, worked out afresh from every campaign whenever this page opens.">
    <div className="space-y-3">
      {plan.next_steps.map((s, i) => {
        const im = IMPACT[s.impact] || IMPACT.low;
        return (
          <article key={i} className="relative overflow-hidden rounded-lg border border-slate-800 bg-slate-950/60 pl-5 pr-4 py-3.5">
            <span className={`absolute left-0 top-0 bottom-0 w-1 ${im.bar}`} />
            <div className="flex items-start gap-3">
              <span className={`h-8 w-8 shrink-0 rounded-full flex items-center justify-center ${im.tint}`}>
                <Icon name={s.icon || 'arrow_forward'} className="text-[18px]" />
              </span>
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-[11px] font-semibold text-slate-500 tabular-nums">{String(i + 1).padStart(2, '0')}</span>
                  <h4 className="text-sm font-semibold text-slate-100">{s.title}</h4>
                  <span className={`text-[10px] font-semibold px-2 py-0.5 rounded-full border ${im.tag}`}>{im.label}</span>
                </div>
                <p className="text-[13px] text-slate-300 mt-1 leading-relaxed">{s.detail}</p>
                <p className="text-[11.5px] text-slate-500 mt-1.5 flex gap-1"><Icon name="info" className="text-[14px]" />{s.why}</p>
              </div>
            </div>
          </article>
        );
      })}
    </div>
  </Card>
);

// ---------------------------------------------------------------------------
// From message to lead
// ---------------------------------------------------------------------------

const Funnel: React.FC<{ plan: Plan }> = ({ plan }) => {
  const steps = plan.funnel.steps;
  const leak = plan.funnel.biggest_leak;
  const max = Math.max(1, ...steps.map(s => s.count));
  // Counts run from thousands down to a handful: a log scale keeps every step visible.
  const width = (n: number) => `${Math.max(4, (Math.log10(n + 1) / Math.log10(max + 1)) * 100)}%`;
  return (
    <Card icon="filter_alt" title="From message to lead" tint="bg-sky-950 text-sky-300"
      subtitle="How many reached each step, and what share of the step before got through.">
      <ol>
        {steps.map((s, i) => {
          const isLeak = leak?.step === s.key;
          return (
            <li key={s.key}>
              {i > 0 && s.from_previous != null && (
                <div className={`flex items-center gap-1 pl-[42%] h-5 text-[10.5px] font-semibold ${isLeak ? 'text-rose-400' : 'text-slate-500'}`}>
                  <Icon name="south" className="text-[13px]" />{pct(s.from_previous)}
                  {s.of_tracked != null && <span className="font-normal text-slate-500">of {num(s.of_tracked)} tracked</span>}
                </div>
              )}
              <div className="grid grid-cols-[40%_1fr] items-center gap-3">
                <span className={`text-[13px] truncate text-right ${isLeak ? 'text-rose-300 font-semibold' : 'text-slate-300'}`} title={s.label}>{s.label}</span>
                <div className="flex items-center gap-2">
                  <div className={`h-6 rounded-md flex items-center px-2 ${isLeak ? 'bg-rose-500' : i === steps.length - 1 ? 'bg-amber-400' : 'bg-sky-500'}`}
                    style={{ width: width(s.count), opacity: isLeak ? 1 : 0.35 + 0.65 * (1 - i / steps.length) }}>
                    <span className="text-[11px] font-semibold text-white tabular-nums">{num(s.count)}</span>
                  </div>
                  {s.waiting > 0 && (
                    <span className="text-[10.5px] font-semibold px-1.5 py-0.5 rounded-full bg-amber-950 text-amber-300 whitespace-nowrap" title="Asked, not answered yet">
                      {s.waiting} deciding
                    </span>
                  )}
                </div>
              </div>
            </li>
          );
        })}
      </ol>
      {leak && (
        <div className="mt-4 rounded-lg border border-rose-800/60 bg-rose-950 p-3.5 flex gap-3">
          <Icon name="warning" className="text-rose-400 text-[20px]" />
          <div className="text-[13px] text-rose-200">
            <div className="font-semibold text-rose-300">Biggest drop: {leak.label}</div>
            <div className="mt-0.5">Only {leak.to} of {leak.from} got through. {leak.advice}</div>
          </div>
        </div>
      )}
    </Card>
  );
};

// ---------------------------------------------------------------------------
// Who to call
// ---------------------------------------------------------------------------

const initials = (name: string | null, phone: string) =>
  (name || '').trim().split(/\s+/).slice(0, 2).map(w => w[0]).join('').toUpperCase() || phone.slice(-2);

const CallList: React.FC<{ plan: Plan }> = ({ plan }) => (
  <Card icon="call" title="Call these people first" tint="bg-amber-950 text-amber-300"
    subtitle="Part-way to applying and not ruled out: the quickest leads there are.">
    {plan.warm_people.length === 0 ? (
      <div className="text-sm text-slate-500 py-6 text-center">Nobody part-way right now.</div>
    ) : (
      <ul className="divide-y divide-slate-800">
        {plan.warm_people.map(p => (
          <li key={p.phone} className="flex items-center gap-3 py-2.5">
            <span className="h-9 w-9 shrink-0 rounded-full bg-sky-950 text-sky-300 text-xs font-bold flex items-center justify-center">
              {initials(p.name, p.phone)}
            </span>
            <div className="min-w-0 flex-1">
              <div className="text-sm font-medium text-slate-100 truncate">{p.name || p.phone}</div>
              <div className="text-[11.5px] text-slate-500 flex flex-wrap gap-x-2">
                <span className="font-mono select-text">{p.phone}</span>
                {p.last_message_at && <span>· {formatDateTime(p.last_message_at)}</span>}
              </div>
            </div>
            <span className="hidden sm:inline text-[10.5px] font-semibold px-2 py-0.5 rounded-full bg-amber-950 text-amber-300 whitespace-nowrap">{p.stage}</span>
            <a href={`#inbox/${p.phone.replace(/\D/g, '')}`} title="Open the chat"
              className="h-8 w-8 rounded-full border border-slate-800 text-slate-400 hover:text-sky-300 hover:bg-slate-950 flex items-center justify-center">
              <Icon name="chat" className="text-[18px]" />
            </a>
            <a href={`tel:${p.phone}`} title="Call"
              className="h-8 w-8 rounded-full bg-emerald-500 text-white hover:opacity-90 flex items-center justify-center">
              <Icon name="call" className="text-[18px]" />
            </a>
          </li>
        ))}
      </ul>
    )}
  </Card>
);

// ---------------------------------------------------------------------------
// Where and whom to message
// ---------------------------------------------------------------------------

const TargetList: React.FC<{ title: string; icon: string; rows: GrowthRow[] }> = ({ title, icon, rows }) => {
  const tried = rows.filter(r => r.confidence !== 'untried');
  const untried = rows.filter(r => r.confidence === 'untried');
  const top = Math.max(0.0001, ...tried.map(r => r.rate || 0));
  return (
    <div className="min-w-0">
      <div className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wider text-slate-500 mb-2">
        <Icon name={icon} className="text-[16px]" />{title}
      </div>
      <ul className="space-y-2.5">
        {tried.map(r => (
          <li key={r.name}>
            <div className="flex items-center gap-2">
              <span className="text-sm font-medium text-slate-100 truncate flex-1" title={r.name}>{r.name}</span>
              <Chip c={r.confidence} direction={r.direction} />
            </div>
            <div className="flex items-center gap-2 mt-1">
              <div className="h-1.5 flex-1 rounded-full bg-slate-800 overflow-hidden">
                <div className={`h-full rounded-full ${r.direction === 'worse' ? 'bg-rose-500' : 'bg-emerald-500'}`}
                  style={{ width: `${((r.rate || 0) / top) * 100}%` }} />
              </div>
              <span className="text-[11.5px] text-slate-400 tabular-nums whitespace-nowrap w-24 text-right">{r.success} of {num(r.sent)}</span>
              <span className={`text-[11px] tabular-nums whitespace-nowrap w-20 text-right ${r.left ? 'text-sky-300 font-semibold' : 'text-slate-500'}`}>
                {r.left ? `${num(r.left)} left` : 'all sent'}
              </span>
            </div>
          </li>
        ))}
      </ul>
      {untried.length > 0 && (
        <div className="mt-4">
          <div className="text-[11px] font-semibold text-purple-300 mb-1.5">Worth a small test</div>
          <div className="flex flex-wrap gap-1.5">
            {untried.map(r => (
              <span key={r.name} className="text-[11.5px] px-2.5 py-1 rounded-full border border-purple-800/60 bg-purple-950 text-purple-300">
                {r.name} <span className="opacity-70">· {num(r.left)}</span>
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
  );
};

const Targets: React.FC<{ plan: Plan }> = ({ plan }) => (
  <Card icon="travel_explore" title="Where and whom to message next" tint="bg-purple-950 text-purple-300"
    subtitle={<>Judged on “{plan.judged_on_label}”. Bars show how many of those reached went on; “left” is businesses with a mobile number not yet messaged ({num(plan.targets.reachable_left)} in all).</>}>
    <div className="grid gap-8 lg:grid-cols-2">
      <TargetList title="Districts" icon="location_on" rows={plan.targets.districts} />
      <TargetList title="Categories" icon="storefront" rows={plan.targets.categories} />
    </div>
  </Card>
);

// ---------------------------------------------------------------------------
// What the templates that worked had in common
// ---------------------------------------------------------------------------

const RECIPE_LABELS: Record<string, string> = {
  angle: 'Angle', layout: 'Layout', image_headline: 'Image headline', language: 'Language',
  time_of_day: 'Sent', weekday: 'Day',
};
const CREATIVE_LABELS: Record<string, string> = {
  angle: 'Message angle', layout: 'Poster layout', image_headline: 'Headline on the image',
  language_match: 'Language', time_of_day: 'Time sent (IST)', weekday: 'Day sent',
};

const Compare: React.FC<{ dim: string; rows: CreativeRow[] }> = ({ dim, rows }) => {
  const top = Math.max(0.0001, ...rows.map(r => r.rate));
  return (
    <div className="rounded-lg border border-slate-800 bg-slate-950/60 p-3.5 min-w-0">
      <div className="text-xs font-semibold text-slate-400 mb-2">{CREATIVE_LABELS[dim] || dim}</div>
      {rows.length === 0 ? <div className="text-[12px] text-slate-500">No results yet.</div> : (
        <ul className="space-y-2">
          {rows.slice(0, 3).map(r => (
            <li key={r.value}>
              <div className="flex items-center gap-2">
                <span className="text-[13px] text-slate-100 truncate flex-1" title={r.value}>{r.value}</span>
                <span className="text-[11.5px] text-slate-400 tabular-nums">{pct(r.rate)}</span>
              </div>
              <div className="flex items-center gap-2 mt-1">
                <div className="h-1.5 flex-1 rounded-full bg-slate-800 overflow-hidden">
                  <div className={`h-full rounded-full ${r.direction === 'worse' ? 'bg-rose-500' : 'bg-sky-500'}`} style={{ width: `${(r.rate / top) * 100}%` }} />
                </div>
                <Chip c={r.confidence} direction={r.direction} campaigns={r.campaigns} />
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
};

const Creative: React.FC<{ plan: Plan }> = ({ plan }) => {
  const c = plan.creative;
  const show = c.showcase;
  const img = show ? mediaUrl(show.header_content) : null;
  return (
    <Card icon="auto_awesome" title="What the templates that worked had in common" tint="bg-amber-950 text-amber-300"
      subtitle={<>Judged on “{plan.judged_on_label}”. The template agents read this before writing each new template.</>}>
      {show && (
        <div className="rounded-xl border border-amber-800/60 bg-amber-950/60 p-4 mb-5 flex flex-col md:flex-row gap-5">
          {img && (
            <img src={img} alt="" className="w-full md:w-64 aspect-[3/2] object-cover rounded-lg border border-slate-800 bg-slate-950 shrink-0" />
          )}
          <div className="min-w-0 flex-1">
            <div className="text-[11px] uppercase tracking-wider font-semibold text-amber-300">Best template so far</div>
            <div className="text-lg font-semibold text-slate-100 mt-0.5 truncate">{show.template}</div>
            <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1 mt-1">
              <span className="text-3xl font-bold text-slate-100 tabular-nums">{pct(show.rate)}</span>
              <span className="text-sm text-slate-400">{show.success} of {num(show.sent)} went on</span>
              <Chip c={show.confidence} direction={show.direction} />
            </div>
            <div className="flex flex-wrap gap-1.5 mt-3">
              {Object.entries(show.recipe).filter(([, v]) => v && !String(v).startsWith('No ')).map(([k, v]) => (
                <span key={k} className="text-[11.5px] px-2.5 py-1 rounded-full bg-slate-900 border border-slate-800 text-slate-300 max-w-full truncate">
                  <span className="text-slate-500">{RECIPE_LABELS[k] || k}:</span> {v}
                </span>
              ))}
            </div>
          </div>
        </div>
      )}
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
        {['angle', 'layout', 'image_headline', 'language_match', 'time_of_day', 'weekday'].map(d =>
          <Compare key={d} dim={d} rows={(c[d] as CreativeRow[]) || []} />)}
      </div>
      {(c.untried_angles.length > 0 || c.untried_layouts.length > 0) && (
        <div className="mt-4 flex flex-wrap items-center gap-1.5">
          <span className="text-[11px] font-semibold text-purple-300 mr-1">Not tried yet:</span>
          {c.untried_angles.map(a => <span key={a} className="text-[11.5px] px-2.5 py-1 rounded-full border border-purple-800/60 bg-purple-950 text-purple-300">{a}</span>)}
          {c.untried_layouts.map(l => <span key={l} className="text-[11.5px] px-2.5 py-1 rounded-full border border-purple-800/60 bg-purple-950 text-purple-300">{l} layout</span>)}
        </div>
      )}
    </Card>
  );
};

// ---------------------------------------------------------------------------

export const GrowthPlan: React.FC = () => {
  const [plan, setPlan] = useState<Plan | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = () => fetchGrowthPlan().then(setPlan).catch(e => setError(e.message));
  useEffect(() => { load(); }, []);

  if (error) return <div className="p-3 rounded-lg border border-rose-800/60 bg-rose-950 text-rose-300 text-sm">Growth plan: {error}</div>;
  if (!plan) return (
    <div className="rounded-2xl h-48 animate-pulse" style={{ background: 'linear-gradient(120deg, #0a3543, #16435a)' }} />
  );

  return (
    <div className="space-y-5">
      <Goal plan={plan} />
      {plan.business && <Business b={plan.business} plan={plan} onSaved={load} />}
      <div className="grid gap-5 xl:grid-cols-[1.4fr_1fr]">
        <NextSteps plan={plan} />
        <div className="space-y-5 min-w-0">
          <Funnel plan={plan} />
          <CallList plan={plan} />
        </div>
      </div>
      <Targets plan={plan} />
      <Creative plan={plan} />
    </div>
  );
};
