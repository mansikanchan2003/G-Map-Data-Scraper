import React, { useEffect, useState } from 'react';
import { fetchGrowthPlan, type CreativeRow, type GrowthPlan as Plan, type GrowthRow } from '../api/insights';
import { formatDateTime } from '../utils/datetime';

/**
 * The lead goal at the top of Campaign Insights: leads so far against the
 * target, where people drop out on the way, who to call, where and whom to
 * message next, and what kind of template to make. The template agents are
 * given the same plan each time they write.
 */

const pct = (v: number | null | undefined) => (v == null ? '—' : `${(v * 100).toFixed(v < 0.1 ? 1 : 0)}%`);
const num = (v: number | null | undefined) => (v == null ? '—' : v.toLocaleString('en-IN'));

const IMPACT: Record<string, string> = {
  high: 'bg-emerald-900/30 border-emerald-700/50 text-emerald-300',
  medium: 'bg-sky-900/30 border-sky-700/50 text-sky-300',
  low: 'bg-slate-800 border-slate-700 text-slate-400',
};

const EVIDENCE: Record<string, { label: string; cls: string; title: string }> = {
  strong: { label: 'Proven', cls: 'text-emerald-300', title: 'The difference holds even allowing for chance.' },
  likely: { label: 'Likely', cls: 'text-sky-300', title: 'A big difference, not yet certain.' },
  no_difference: { label: 'No difference', cls: 'text-slate-400', title: 'No clearer than the rest.' },
  too_early: { label: 'Too early', cls: 'text-amber-300', title: 'Not enough people yet to tell.' },
  untried: { label: 'Not tried', cls: 'text-violet-300', title: 'Never messaged: worth a small test.' },
};

const Evidence: React.FC<{ c: string; direction?: string; campaigns?: number }> = ({ c, direction, campaigns }) => {
  const e = EVIDENCE[c] || EVIDENCE.too_early;
  // A firm verdict says which way it went: proven worse is a warning, not a win.
  const firm = c === 'strong' || c === 'likely';
  const worse = firm && direction === 'worse';
  const label = firm && direction === 'better' ? `${e.label} better` : worse ? `${e.label} worse` : e.label;
  const cls = worse ? 'text-rose-300' : e.cls;
  return (
    <span className={`text-[11px] font-semibold whitespace-nowrap ${cls}`} title={e.title}>
      {label}
      {campaigns === 1 && c !== 'untried' && (
        <span className="ml-1 font-normal text-slate-500"
          title="All from one campaign: its place, timing and template went together, so which of them mattered cannot be told yet.">
          · 1 campaign
        </span>
      )}
    </span>
  );
};

const Section: React.FC<{ title: string; subtitle?: React.ReactNode; children: React.ReactNode }> = ({ title, subtitle, children }) => (
  <div className="rounded-lg border border-slate-800 bg-slate-900/60 p-4">
    <h3 className="text-sm font-semibold text-slate-100">{title}</h3>
    {subtitle && <div className="text-xs text-slate-500 mt-0.5 mb-3">{subtitle}</div>}
    {!subtitle && <div className="mb-3" />}
    {children}
  </div>
);

const GoalCard: React.FC<{ plan: Plan }> = ({ plan }) => {
  const g = plan.goal;
  const done = Math.min(100, (g.leads / Math.max(g.target, 1)) * 100);
  const deadline = new Date(`${g.deadline}T00:00:00+05:30`).toLocaleDateString('en-IN', { day: 'numeric', month: 'long', year: 'numeric' });
  return (
    <div className="rounded-lg border border-emerald-800/50 bg-gradient-to-br from-emerald-950/40 to-slate-900 p-5">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <div className="text-xs uppercase tracking-wider text-emerald-300/80 font-semibold">Lead goal</div>
          <div className="mt-1 text-3xl font-semibold text-slate-50 tabular-nums">
            {g.leads} <span className="text-slate-500 text-xl">/ {g.target} leads</span>
          </div>
          <div className="text-xs text-slate-400 mt-1">
            by {deadline} · a lead is someone a campaign reached who submitted their documents
          </div>
        </div>
        <div className="grid grid-cols-3 gap-5 text-right">
          <div><div className="text-xl font-semibold text-slate-100 tabular-nums">{g.days_left}</div><div className="text-[11px] text-slate-500">days left</div></div>
          <div><div className="text-xl font-semibold text-slate-100 tabular-nums">{g.still_needed}</div><div className="text-[11px] text-slate-500">still needed</div></div>
          <div><div className="text-xl font-semibold text-slate-100 tabular-nums">{g.per_day_needed ?? '—'}</div><div className="text-[11px] text-slate-500">per day needed</div></div>
        </div>
      </div>
      <div className="mt-4 h-2 rounded-full bg-slate-800 overflow-hidden">
        <div className="h-full bg-emerald-500 rounded-full" style={{ width: `${done}%` }} />
      </div>
      <div className="mt-2 text-[11px] text-slate-500">
        {g.leads_per_1000 != null
          ? <>{g.leads_per_1000} leads per 1,000 messages so far{g.messages_needed ? <>, so about {num(g.messages_needed)} more messages at this rate</> : null}.</>
          : <>No lead yet from {num(g.messages_sent)} campaign messages, so nothing can be projected; the plan below works from the steps before a lead.</>}
        {g.lead_list.length > 0 && <> Leads: {g.lead_list.map(l => `${l.name || l.phone} (${formatDateTime(l.submitted_at)})`).join(', ')}.</>}
      </div>
    </div>
  );
};

const NextSteps: React.FC<{ plan: Plan }> = ({ plan }) => (
  <Section title="What to do next" subtitle="Most effective first. Worked out afresh from every campaign each time this page opens.">
    <ol className="space-y-3">
      {plan.next_steps.map((s, i) => (
        <li key={i} className="flex gap-3">
          <span className="mt-0.5 h-6 w-6 shrink-0 rounded-full bg-slate-800 text-slate-300 text-xs font-semibold flex items-center justify-center">{i + 1}</span>
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-sm font-semibold text-slate-100">{s.title}</span>
              <span className={`text-[10px] uppercase tracking-wide px-1.5 py-0.5 rounded border ${IMPACT[s.impact]}`}>{s.impact} impact</span>
            </div>
            <div className="text-xs text-slate-300 mt-0.5">{s.detail}</div>
            <div className="text-[11px] text-slate-500 mt-0.5">Why: {s.why}</div>
          </div>
        </li>
      ))}
    </ol>
  </Section>
);

const Funnel: React.FC<{ plan: Plan }> = ({ plan }) => {
  const steps = plan.funnel.steps;
  const max = Math.max(1, ...steps.filter(s => s.key !== 'sent').map(s => s.count));
  const leak = plan.funnel.biggest_leak;
  return (
    <Section title="From message to lead" subtitle="How many people reached each step, and how many of those before them got through.">
      <div className="space-y-1.5">
        {steps.map(s => (
          <div key={s.key} className={`grid grid-cols-[minmax(130px,1.2fr)_3fr_auto] items-center gap-3 text-xs ${leak?.step === s.key ? 'text-rose-200' : 'text-slate-300'}`}>
            <span className="truncate">{s.label}</span>
            <div className="h-2.5 rounded-sm bg-slate-800 overflow-hidden">
              {s.key !== 'sent' && <div className={`h-full ${leak?.step === s.key ? 'bg-rose-500' : 'bg-sky-500'}`} style={{ width: `${(s.count / max) * 100}%` }} />}
            </div>
            <span className="tabular-nums whitespace-nowrap text-right min-w-[150px]">
              {num(s.count)}
              {s.from_previous != null && <span className="text-slate-500"> · {pct(s.from_previous)}</span>}
              {s.of_tracked != null && <span className="text-slate-600" title="Measured on campaigns sent after delivery reports began"> of {num(s.of_tracked)}</span>}
              {s.waiting > 0 && <span className="text-amber-300/80" title="Asked, not answered yet"> · {s.waiting} deciding</span>}
            </span>
          </div>
        ))}
      </div>
      {leak && (
        <div className="mt-3 rounded border border-rose-800/50 bg-rose-950/30 p-3 text-xs text-rose-100">
          <span className="font-semibold">Biggest drop: {leak.label}.</span> {leak.to} of {leak.from} got through. {leak.advice}
        </div>
      )}
    </Section>
  );
};

const WarmPeople: React.FC<{ plan: Plan }> = ({ plan }) => (
  <Section title="Call these people first" subtitle="Part-way to applying and not ruled out: the quickest leads there are.">
    {plan.warm_people.length === 0 ? <div className="text-xs text-slate-500">Nobody part-way right now.</div> : (
      <table className="w-full text-xs">
        <tbody>
          {plan.warm_people.map(p => (
            <tr key={p.phone} className="border-t border-slate-800 first:border-0">
              <td className="py-1.5 pr-2 text-slate-100">{p.name || '—'}</td>
              <td className="py-1.5 pr-2 font-mono text-slate-300 select-text">{p.phone}</td>
              <td className="py-1.5 pr-2 text-slate-400">{p.stage}</td>
              <td className="py-1.5 text-slate-500 whitespace-nowrap">{p.last_message_at ? formatDateTime(p.last_message_at) : ''}</td>
            </tr>
          ))}
        </tbody>
      </table>
    )}
  </Section>
);

const TargetTable: React.FC<{ title: string; rows: GrowthRow[]; stage: string }> = ({ title, rows, stage }) => (
  <div className="min-w-0">
    <div className="text-xs font-semibold text-slate-300 mb-1.5">{title}</div>
    <table className="w-full text-xs">
      <thead className="text-slate-500 text-left">
        <tr>
          <th className="py-1 font-semibold">Name</th>
          <th className="py-1 font-semibold text-right" title={`Reached, and how many went on to “${stage}”`}>Went on</th>
          <th className="py-1 font-semibold text-right" title="Businesses with a mobile number not yet messaged">Left</th>
          <th className="py-1 font-semibold text-right">Evidence</th>
        </tr>
      </thead>
      <tbody>
        {rows.map(r => (
          <tr key={r.name} className="border-t border-slate-800 text-slate-300">
            <td className="py-1.5 pr-2 text-slate-100 truncate max-w-[180px]" title={r.name}>{r.name}</td>
            <td className="py-1.5 text-right tabular-nums whitespace-nowrap">{r.sent ? <>{r.success} of {num(r.sent)}</> : '—'}</td>
            <td className="py-1.5 text-right tabular-nums">{num(r.left)}</td>
            <td className="py-1.5 text-right"><Evidence c={r.confidence} direction={r.direction} /></td>
          </tr>
        ))}
      </tbody>
    </table>
  </div>
);

const CREATIVE_LABELS: Record<string, string> = {
  angle: 'Message angle', layout: 'Poster layout', image_headline: 'Headline on the image',
  language_match: 'Language', body_length: 'Message length', time_of_day: 'Time sent (IST)', weekday: 'Day sent',
};

const CreativeTable: React.FC<{ dim: string; rows: CreativeRow[] }> = ({ dim, rows }) => (
  <div className="min-w-0">
    <div className="text-xs font-semibold text-slate-300 mb-1.5">{CREATIVE_LABELS[dim] || dim}</div>
    {rows.length === 0 ? <div className="text-[11px] text-slate-500">No results yet.</div> : (
      <table className="w-full text-xs">
        <tbody>
          {rows.slice(0, 4).map(r => (
            <tr key={r.value} className="border-t border-slate-800 first:border-0 text-slate-300">
              <td className="py-1.5 pr-2 text-slate-100 truncate max-w-[200px]" title={r.value}>{r.value}</td>
              <td className="py-1.5 text-right tabular-nums whitespace-nowrap">{r.success} of {num(r.sent)} <span className="text-slate-500">({pct(r.rate)})</span></td>
              <td className="py-1.5 pl-2 text-right"><Evidence c={r.confidence} direction={r.direction} campaigns={r.campaigns} /></td>
            </tr>
          ))}
        </tbody>
      </table>
    )}
  </div>
);

export const GrowthPlan: React.FC = () => {
  const [plan, setPlan] = useState<Plan | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => { fetchGrowthPlan().then(setPlan).catch(e => setError(e.message)); }, []);

  if (error) return <div className="mb-6 p-3 rounded border border-rose-600/50 bg-rose-900/20 text-rose-200 text-sm">Growth plan: {error}</div>;
  if (!plan) return <div className="mb-6 text-sm text-slate-500">Working out the growth plan…</div>;

  const stage = plan.judged_on_label;
  return (
    <div className="mb-8 space-y-4">
      <GoalCard plan={plan} />
      <div className="grid gap-4 xl:grid-cols-2">
        <NextSteps plan={plan} />
        <div className="space-y-4">
          <Funnel plan={plan} />
          <WarmPeople plan={plan} />
        </div>
      </div>
      <Section title="Where and whom to message next"
        subtitle={<>Judged on “{stage}”, the furthest step with enough people to compare. Places and categories that answered come first, then the biggest untried ones. {num(plan.targets.reachable_left)} businesses with a mobile number have not been messaged yet.</>}>
        <div className="grid gap-6 lg:grid-cols-2">
          <TargetTable title="Districts" rows={plan.targets.districts} stage={stage} />
          <TargetTable title="Categories" rows={plan.targets.categories} stage={stage} />
        </div>
      </Section>
      <Section title="What the templates that worked had in common"
        subtitle={<>Judged on “{stage}”. “1 campaign” means the result could equally be that campaign's place or timing. The template agents read this before writing.</>}>
        <div className="grid gap-6 md:grid-cols-2 xl:grid-cols-3">
          {['angle', 'layout', 'image_headline', 'language_match', 'time_of_day', 'weekday'].map(d =>
            <CreativeTable key={d} dim={d} rows={(plan.creative[d] as CreativeRow[]) || []} />)}
        </div>
        {(plan.creative.untried_angles.length > 0 || plan.creative.untried_layouts.length > 0) && (
          <div className="mt-4 text-xs text-slate-400">
            <span className="text-violet-300 font-semibold">Not tried yet:</span>{' '}
            {plan.creative.untried_angles.length > 0 && <>angles {plan.creative.untried_angles.join(', ')}</>}
            {plan.creative.untried_angles.length > 0 && plan.creative.untried_layouts.length > 0 && '; '}
            {plan.creative.untried_layouts.length > 0 && <>poster layouts {plan.creative.untried_layouts.join(', ')}</>}.
          </div>
        )}
      </Section>
    </div>
  );
};
