import React, { useEffect, useMemo, useState } from 'react';
import { fetchDispositionDashboard, type DispositionDashboard } from '../api/inbox';
import { formatDateTime } from '../utils/datetime';

/**
 * Every chat's outcome (disposition) at a glance, on the Dispositions tab:
 * where the chats stand (a donut of the four groups, and every category and
 * sub-category of the team's "Call Dispositions" sheet with its count), what
 * the team recorded each day and who recorded it, who is handling which chat
 * now, and the latest outcomes. Each name opens its chat in the Inbox.
 *
 * The four groups are status colours (going well, follow up, closed, other),
 * so each always carries its icon and label too: never colour alone.
 */

type Group = 'positive' | 'follow_up' | 'negative' | 'other';

const GROUP: Record<Group, { label: string; icon: string; stroke: string; bar: string; tint: string; ring: string; text: string }> = {
  positive: { label: 'Going well', icon: 'trending_up', stroke: 'stroke-emerald-500', bar: 'bg-emerald-500',
    tint: 'bg-emerald-950 text-emerald-300', ring: 'border-emerald-800/60', text: 'text-emerald-300' },
  follow_up: { label: 'Follow up', icon: 'schedule', stroke: 'stroke-amber-400', bar: 'bg-amber-400',
    tint: 'bg-amber-950 text-amber-300', ring: 'border-amber-800/60', text: 'text-amber-300' },
  negative: { label: 'Closed', icon: 'block', stroke: 'stroke-rose-500', bar: 'bg-rose-500',
    tint: 'bg-rose-950 text-rose-300', ring: 'border-rose-800/60', text: 'text-rose-300' },
  other: { label: 'Other', icon: 'more_horiz', stroke: 'stroke-slate-500', bar: 'bg-slate-500',
    tint: 'bg-slate-800 text-slate-300', ring: 'border-slate-700', text: 'text-slate-300' },
};
const ORDER: Group[] = ['positive', 'follow_up', 'negative', 'other'];
// The groups' colours on the always-dark banner, where the theme ramps do not apply.
const ACCENT: Record<Group, string> = { positive: '#34d399', follow_up: '#f9ab10', negative: '#fb7185', other: '#94a3b8' };


const Icon: React.FC<{ name: string; className?: string; style?: React.CSSProperties }> = ({ name, className = '', style }) =>
  <span className={`material-symbols-outlined ${className}`} style={style}>{name}</span>;
const who = (email: string) => email.split('@')[0].replace(/[._]/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
const initials = (text: string) => text.split(/\s+/).filter(Boolean).slice(0, 2).map(w => w[0]).join('').toUpperCase();
const chat = (phone: string) => `#inbox/${phone.replace(/\D/g, '')}`;
const pct = (n: number, total: number) => (total ? Math.round((n / total) * 100) : 0);
const ago = (iso: string | null) => {
  if (!iso) return '';
  const m = Math.max(0, Math.round((Date.now() - new Date(iso).getTime()) / 60000));
  return m < 60 ? `${m} min` : m < 1440 ? `${Math.round(m / 60)} h` : `${Math.round(m / 1440)} d`;
};
const dayLabel = (iso: string) => new Date(`${iso}T00:00:00`).toLocaleDateString('en-IN', { day: 'numeric', month: 'short' });

const Card: React.FC<{ title: string; icon: string; sub?: React.ReactNode; children: React.ReactNode; className?: string }> =
  ({ title, icon, sub, children, className = '' }) => (
  <section className={`rounded-2xl border border-slate-800 bg-slate-900 p-5 shadow-sm ${className}`}>
    <div className="flex items-start justify-between gap-3 mb-4">
      <h3 className="text-[15px] font-semibold text-slate-100 flex items-center gap-2">
        <span className="h-8 w-8 rounded-lg bg-sky-950 text-sky-300 flex items-center justify-center"><Icon name={icon} className="text-[18px]" /></span>
        {title}
      </h3>
      {sub && <div className="text-[11.5px] text-slate-500 text-right">{sub}</div>}
    </div>
    {children}
  </section>
);

/** The four groups as a donut with 2px gaps, the total in the middle; hover a slice for its share. */
const Donut: React.FC<{ totals: Record<Group, number>; total: number }> = ({ totals, total }) => {
  const [hover, setHover] = useState<Group | null>(null);
  const R = 70, W = 22, C = 2 * Math.PI * R, GAP = 3;
  let offset = 0;
  const slices = ORDER.filter(g => totals[g] > 0).map(g => {
    const len = (totals[g] / Math.max(total, 1)) * C;
    const s = { g, dash: Math.max(len - GAP, 0.5), offset };
    offset += len;
    return s;
  });
  const shown = hover ? { n: totals[hover], label: GROUP[hover].label } : { n: total, label: 'chats' };
  return (
    <div className="relative w-[190px] h-[190px] shrink-0">
      <svg viewBox="0 0 190 190" className="w-full h-full -rotate-90" role="img" aria-label="Chats by outcome group">
        <circle cx="95" cy="95" r={R} fill="none" strokeWidth={W} className="stroke-slate-800" />
        {slices.map(s => (
          <circle key={s.g} cx="95" cy="95" r={R} fill="none" strokeWidth={hover === s.g ? W + 6 : W}
            strokeDasharray={`${s.dash} ${C - s.dash}`} strokeDashoffset={-s.offset}
            className={`${GROUP[s.g].stroke} transition-all duration-200 cursor-pointer`}
            onMouseEnter={() => setHover(s.g)} onMouseLeave={() => setHover(null)}>
            <title>{`${GROUP[s.g].label}: ${totals[s.g]} chats (${pct(totals[s.g], total)}%)`}</title>
          </circle>
        ))}
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center pointer-events-none">
        <span className="text-3xl font-bold tabular-nums text-slate-100">{shown.n}</span>
        <span className="text-[11px] uppercase tracking-wider text-slate-500">{shown.label}</span>
        {hover && <span className="text-[12px] font-semibold text-slate-300">{pct(totals[hover], total)}%</span>}
      </div>
    </div>
  );
};

/** Outcomes the team recorded each day: thin columns on the baseline, a tooltip on hover. */
const Columns: React.FC<{ days: { date: string; count: number }[] }> = ({ days }) => {
  const [hover, setHover] = useState<number | null>(null);
  const max = Math.max(1, ...days.map(d => d.count));
  const every = days.length > 31 ? 14 : days.length > 10 ? 5 : 1;
  return (
    <div className="relative">
      <div className="flex items-end gap-[2px] h-36 border-b border-slate-800">
        {days.map((d, i) => (
          <div key={d.date} className="flex-1 h-full flex items-end justify-center cursor-pointer"
            onMouseEnter={() => setHover(i)} onMouseLeave={() => setHover(null)}>
            <div className={`w-full max-w-[44px] mx-auto rounded-t-[4px] transition-colors ${d.count ? (hover === i ? 'bg-sky-400' : 'bg-sky-500') : 'bg-slate-800'}`}
              style={{ height: d.count ? `${Math.max(6, (d.count / max) * 100)}%` : '3px' }} />
          </div>
        ))}
      </div>
      <div className="flex gap-[2px] mt-1.5">
        {days.map((d, i) => (
          <div key={d.date} className="flex-1 text-center text-[10px] text-slate-500 whitespace-nowrap overflow-visible">
            {(i % every === 0 || i === days.length - 1) ? dayLabel(d.date) : ''}
          </div>
        ))}
      </div>
      {hover !== null && (
        <div className="absolute -top-2 px-2.5 py-1.5 rounded-lg bg-slate-950 border border-slate-700 text-[12px] text-slate-200 shadow-lg pointer-events-none whitespace-nowrap"
          style={{ left: `${((hover + 0.5) / days.length) * 100}%`, transform: 'translate(-50%, -100%)' }}>
          <b className="tabular-nums">{days[hover].count}</b> recorded · {dayLabel(days[hover].date)}
        </div>
      )}
    </div>
  );
};

export const DispositionsPanel: React.FC<{ days?: number }> = ({ days = 7 }) => {
  const [d, setD] = useState<DispositionDashboard | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [focus, setFocus] = useState<Group | 'all'>('all');
  useEffect(() => {
    setD(null); setError(null);
    fetchDispositionDashboard(days).then(setD).catch(e => setError(e.message));
  }, [days]);

  const totals = useMemo(() => {
    const t = { positive: 0, follow_up: 0, negative: 0, other: 0 } as Record<Group, number>;
    d?.groups.forEach(g => { t[g.group as Group] += g.count; });
    return d?.group_totals || t;
  }, [d]);

  if (error) return <div className="p-4 rounded-xl border border-rose-800/60 bg-rose-950 text-rose-300 text-sm">Could not load the outcomes: {error}</div>;
  if (!d) return (
    <div className="grid gap-4 md:grid-cols-4 animate-pulse">
      {[0, 1, 2, 3].map(i => <div key={i} className="h-28 rounded-2xl bg-slate-900 border border-slate-800" />)}
    </div>
  );

  const total = d.total;
  const categories = (d.categories || []).filter(c => focus === 'all' || c.group === focus);
  // A disposition's icon is its category's.
  const iconOf = (key: string) => (d.categories || []).find(c => c.subs.some(s => s.key === key))?.icon || 'label';
  const byDay = d.by_day || [];
  const people = d.by_person || [];

  return (
    <div className="space-y-5 select-text">
      {/* The headline and the four groups, in Campaign Insights' deep-teal banner (dark in
          both themes); each tile filters the breakdown below. */}
      <section className="rounded-2xl overflow-hidden shadow-md text-white"
        style={{ background: 'linear-gradient(120deg, #0a3543 0%, #16435a 55%, #1d5a6e 100%)' }}>
        <div className="p-6 flex flex-wrap items-end justify-between gap-4">
          <div>
            <div className="text-[11px] uppercase tracking-[0.14em] font-semibold flex flex-wrap items-center gap-2" style={{ color: '#f9ab10' }}>
              Where every chat stands
              <span className="normal-case tracking-normal font-medium text-[10.5px] px-2 py-0.5 rounded-full bg-white/10 text-white/80">
                <Icon name="history" className="text-[13px] align-[-2px] mr-0.5" />{d.recent_count} recorded in the last {d.recent_days} days
              </span>
            </div>
            <div className="mt-1 flex items-baseline gap-3">
              <span className="text-4xl sm:text-5xl font-semibold tabular-nums">{pct(totals.positive, total)}%</span>
              <span className="text-sm text-white/75">going well, of <b className="text-white">{total}</b> chats</span>
            </div>
            <p className="text-sm text-white/70 mt-1">
              {d.by_team} outcomes recorded by the team; the rest read from the bot's step.
            </p>
          </div>
          <div className="flex gap-3">
            <div className="rounded-lg bg-white/10 px-4 py-3 min-w-[140px]">
              <div className="flex items-center gap-1.5 text-white/70 text-[11px]"><Icon name="rocket_launch" className="text-[15px]" style={{ color: '#34d399' }} />moved to CAT 1</div>
              <div className="text-2xl font-semibold tabular-nums mt-0.5">{d.cat1 ?? 0} <span className="text-sm font-normal text-white/70">{(d.cat1 ?? 0) === 1 ? 'lead' : 'leads'}</span></div>
            </div>
            <div className="rounded-lg bg-white/10 px-4 py-3 min-w-[140px]">
              <div className="flex items-center gap-1.5 text-white/70 text-[11px]"><Icon name="support_agent" className="text-[15px]" />with the team now</div>
              <div className="text-2xl font-semibold tabular-nums mt-0.5">{d.with_people.length} <span className="text-sm font-normal text-white/70">{d.with_people.length === 1 ? 'chat' : 'chats'}</span></div>
            </div>
          </div>
        </div>
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 px-6 pb-6">
          {ORDER.map(g => {
            const on = focus === g;
            return (
              <button key={g} onClick={() => setFocus(on ? 'all' : g)}
                className={`text-left rounded-lg px-4 py-3 transition-all cursor-pointer ${on
                  ? 'bg-white/20 ring-2 ring-[#f9ab10]' : 'bg-white/10 hover:bg-white/15'}`}>
                <div className="flex items-center justify-between">
                  <span className="flex items-center gap-1.5 text-white/75 text-[12px]">
                    <Icon name={GROUP[g].icon} className="text-[16px]" style={{ color: ACCENT[g] }} />{GROUP[g].label}
                  </span>
                  <span className="text-[11.5px] tabular-nums text-white/60">{pct(totals[g], total)}%</span>
                </div>
                <div className="text-2xl font-semibold tabular-nums mt-1">{totals[g]}</div>
                <div className="h-1.5 rounded-full bg-white/10 mt-2 overflow-hidden">
                  <div className="h-full rounded-full" style={{ width: `${pct(totals[g], total)}%`, background: ACCENT[g] }} />
                </div>
              </button>
            );
          })}
        </div>
      </section>

      <div className="grid gap-5 xl:grid-cols-[1fr_1.35fr]">
        <Card title="Outcome mix" icon="donut_large" sub="Hover a slice for its share">
          <div className="flex flex-col sm:flex-row items-center gap-6">
            <Donut totals={totals} total={total} />
            <ul className="flex-1 min-w-[180px] w-full space-y-2.5">
              {ORDER.map(g => (
                <li key={g} className="flex items-center gap-2.5 text-[13px]">
                  <span className={`h-7 w-7 rounded-lg flex items-center justify-center ${GROUP[g].tint}`}><Icon name={GROUP[g].icon} className="text-[16px]" /></span>
                  <span className="flex-1 text-slate-200 whitespace-nowrap">{GROUP[g].label}</span>
                  <span className="tabular-nums font-semibold text-slate-100">{totals[g]}</span>
                  <span className="w-10 text-right tabular-nums text-slate-500">{pct(totals[g], total)}%</span>
                </li>
              ))}
            </ul>
          </div>
        </Card>

        <Card title="Recorded by the team, day by day" icon="bar_chart" sub={`Last ${d.recent_days} days · hover a day`}>
          {byDay.some(x => x.count) ? <Columns days={byDay} /> : (
            <div className="h-36 flex items-center justify-center text-sm text-slate-500 rounded-xl border border-dashed border-slate-800">
              Nothing recorded in these days yet.
            </div>
          )}
          {people.length > 0 && (
            <div className="flex flex-wrap gap-2 mt-4">
              {people.map(p => (
                <span key={p.by} className="inline-flex items-center gap-2 pl-1 pr-3 py-1 rounded-full border border-slate-800 bg-slate-950 text-[12px]">
                  <span className="h-6 w-6 rounded-full bg-violet-950 text-violet-300 text-[10px] font-bold flex items-center justify-center">{initials(who(p.by))}</span>
                  <span className="text-slate-200">{who(p.by)}</span>
                  <b className="tabular-nums text-slate-100">{p.count}</b>
                </span>
              ))}
            </div>
          )}
        </Card>
      </div>

      <Card title="Every disposition" icon="checklist"
        sub={focus === 'all' ? 'The team\'s sheet: eleven categories and their sub-categories' : <button onClick={() => setFocus('all')} className="text-sky-300 hover:underline cursor-pointer">Showing {GROUP[focus].label} · show all</button>}>
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
          {categories.map(c => {
            const g = GROUP[c.group as Group] || GROUP.other;
            const max = Math.max(1, ...c.subs.map(x => x.count));
            return (
              <div key={c.key} className={`rounded-xl border ${g.ring} bg-slate-950/50 p-3.5`}>
                <div className="flex items-center gap-2.5">
                  <span className={`h-8 w-8 rounded-lg flex items-center justify-center ${g.tint}`}><Icon name={c.icon} className="text-[17px]" /></span>
                  <span className="flex-1 text-[13.5px] font-semibold text-slate-100">{c.label}</span>
                  <span className="text-lg font-semibold tabular-nums text-slate-100">{c.count}</span>
                </div>
                <ul className="mt-2.5 space-y-1.5">
                  {c.subs.map(x => (
                    <li key={x.key} className="text-[12.5px]" title={x.action ? `${x.action}${x.owner ? ` · ${x.owner}` : ''}` : x.label}>
                      <div className="flex items-center justify-between gap-2">
                        <span className={x.count ? 'text-slate-300' : 'text-slate-500'}>{x.label}</span>
                        <span className={`tabular-nums ${x.count ? 'font-semibold text-slate-100' : 'text-slate-600'}`}>{x.count}</span>
                      </div>
                      <div className="h-1 rounded-full bg-slate-800 mt-1 overflow-hidden">
                        <div className={`h-full rounded-full ${g.bar}`} style={{ width: `${(x.count / max) * 100}%`, opacity: x.count ? 1 : 0 }} />
                      </div>
                    </li>
                  ))}
                </ul>
              </div>
            );
          })}
        </div>
      </Card>

      <div className="grid gap-5 xl:grid-cols-[1fr_1.35fr]">
        <Card title="With the team now" icon="support_agent" sub={`${d.with_people.length} ${d.with_people.length === 1 ? 'chat' : 'chats'}`}>
          {d.with_people.length ? (
            <ul className="space-y-2">
              {d.with_people.slice(0, 8).map(p => (
                <li key={p.phone}>
                  <a href={chat(p.phone)} className="flex items-center gap-3 p-2.5 rounded-xl border border-slate-800 bg-slate-950/60 hover:border-violet-700 transition-colors">
                    <span className="h-9 w-9 rounded-full bg-slate-800 text-slate-200 text-[12px] font-bold flex items-center justify-center">{initials(p.name || p.phone)}</span>
                    <span className="min-w-0 flex-1">
                      <span className="block text-[13px] font-semibold text-slate-100 truncate">{p.name || p.phone}</span>
                      <span className="block text-[11.5px] text-slate-500">with {who(p.by)}</span>
                    </span>
                    <span className="text-[11.5px] text-violet-300 whitespace-nowrap flex items-center gap-1"><Icon name="schedule" className="text-[14px]" />{ago(p.since)}</span>
                  </a>
                </li>
              ))}
            </ul>
          ) : (
            <div className="h-36 flex flex-col items-center justify-center gap-2 text-center rounded-xl border border-dashed border-slate-800">
              <Icon name="smart_toy" className="text-[28px] text-sky-400" />
              <span className="text-[13px] text-slate-400">The bot is handling every chat.</span>
            </div>
          )}
        </Card>
        <Card title="Latest outcomes" icon="history" sub={`${d.recent_count} in the last ${d.recent_days} days`}>
          {d.recent.length ? (
            <ol className="relative ml-3 border-l border-slate-800 space-y-4">
              {d.recent.map((r, i) => {
                const grp = (d.groups.find(x => x.key === r.key)?.group || 'other') as Group;
                const g = GROUP[grp];
                return (
                  <li key={i} className="pl-5 relative">
                    <span className={`absolute -left-[13px] top-0.5 h-6 w-6 rounded-full flex items-center justify-center ring-4 ring-slate-900 ${g.tint}`}>
                      <Icon name={iconOf(r.key)} className="text-[14px]" />
                    </span>
                    <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
                      <a href={chat(r.phone)} className="text-[13.5px] font-semibold text-sky-300 hover:underline">{r.name || r.phone}</a>
                      <span className={`px-2 py-0.5 rounded-full border text-[11px] font-semibold ${g.ring} ${g.tint}`}>{r.label}</span>
                      <span className="text-[11.5px] text-slate-500">by {who(r.by)} · {formatDateTime(r.at)}</span>
                    </div>
                    {r.note && <p className="mt-1 text-[12.5px] text-slate-300 bg-slate-950/60 border border-slate-800 rounded-lg px-3 py-1.5 inline-block">{r.note}</p>}
                  </li>
                );
              })}
            </ol>
          ) : (
            <div className="py-8 text-center text-sm text-slate-500 rounded-xl border border-dashed border-slate-800">
              Nothing recorded yet. Outcomes are recorded when a chat is handed back to the bot, when a question is resolved, or with “Change” above any chat.
            </div>
          )}
        </Card>
      </div>
    </div>
  );
};
