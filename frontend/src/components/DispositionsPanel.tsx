import React, { useEffect, useState } from 'react';
import { fetchDispositionDashboard, type DispositionDashboard } from '../api/inbox';
import { formatDateTime } from '../utils/datetime';

/**
 * Every chat's outcome (disposition) at a glance, on the Dispositions tab: how many
 * chats stand where, the chats people are handling now, and the outcomes the
 * team recorded lately. Each name opens its chat in the Inbox.
 */

const BAR: Record<string, string> = {
  positive: 'bg-emerald-500', follow_up: 'bg-amber-400', negative: 'bg-rose-500', other: 'bg-slate-500',
};
const GROUPS: [string, string][] = [['positive', 'Going well'], ['follow_up', 'Follow up'], ['negative', 'Closed'], ['other', 'Other']];
const who = (email: string) => email.split('@')[0].replace(/[._]/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
const chat = (phone: string) => `#inbox/${phone.replace(/\D/g, '')}`;

export const DispositionsPanel: React.FC<{ days?: number }> = ({ days = 7 }) => {
  const [d, setD] = useState<DispositionDashboard | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    setD(null);
    fetchDispositionDashboard(days).then(setD).catch(e => setError(e.message));
  }, [days]);

  if (error) return <div className="p-3 rounded border border-rose-800 bg-rose-950/70 text-rose-200 text-xs">Chat outcomes: {error}</div>;
  if (!d) return <div className="p-4 rounded-lg border border-slate-800 bg-slate-900 text-xs text-slate-500">Loading chat outcomes…</div>;
  const max = Math.max(1, ...d.groups.map(g => g.count));

  return (
    <section className="rounded-lg border border-slate-800 bg-slate-900 p-4 select-text">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="text-sm font-semibold text-slate-100 flex items-center gap-1.5">
          <span className="material-symbols-outlined text-[18px] text-sky-400">fact_check</span>Chat outcomes (dispositions)
        </h2>
        <span className="text-[11px] text-slate-500">
          {d.total} chats · {d.by_team} recorded by the team, the rest from the bot's step
        </span>
      </div>

      <div className="grid gap-5 mt-3 lg:grid-cols-[1.3fr_1fr]">
        <div className="space-y-3">
          {GROUPS.map(([g, label]) => {
            const rows = d.groups.filter(x => x.group === g && x.count > 0);
            if (!rows.length) return null;
            return (
              <div key={g}>
                <div className="text-[10.5px] uppercase tracking-wider text-slate-500 mb-1">{label}</div>
                <ul className="space-y-1">
                  {rows.map(r => (
                    <li key={r.key} className="grid grid-cols-[150px_1fr_36px] items-center gap-2 text-[12px]">
                      <span className="text-slate-300 truncate" title={r.label}>{r.label}</span>
                      <span className="h-2.5 rounded-full bg-slate-800 overflow-hidden">
                        <span className={`block h-full rounded-full ${BAR[g]}`} style={{ width: `${(r.count / max) * 100}%` }} />
                      </span>
                      <span className="text-right tabular-nums text-slate-200 font-semibold">{r.count}</span>
                    </li>
                  ))}
                </ul>
              </div>
            );
          })}
        </div>

        <div className="space-y-4 min-w-0">
          <div>
            <div className="text-[10.5px] uppercase tracking-wider text-slate-500 mb-1">With the team now ({d.with_people.length})</div>
            {d.with_people.length ? (
              <ul className="space-y-1">
                {d.with_people.slice(0, 8).map(p => (
                  <li key={p.phone} className="text-[12px] flex justify-between gap-2">
                    <a href={chat(p.phone)} className="text-sky-300 hover:underline truncate">{p.name || p.phone}</a>
                    <span className="text-slate-500 whitespace-nowrap">{who(p.by)}{p.since ? ` · ${formatDateTime(p.since)}` : ''}</span>
                  </li>
                ))}
              </ul>
            ) : <div className="text-[12px] text-slate-500">No chat is with a person; the bot handles them all.</div>}
          </div>
          <div>
            <div className="text-[10.5px] uppercase tracking-wider text-slate-500 mb-1">
              Recorded in the last {d.recent_days} days ({d.recent_count})
            </div>
            {d.recent.length ? (
              <ul className="space-y-1.5 max-h-56 overflow-y-auto pr-1">
                {d.recent.map((r, i) => (
                  <li key={i} className="text-[12px]">
                    <div className="flex justify-between gap-2">
                      <a href={chat(r.phone)} className="text-sky-300 hover:underline truncate">{r.name || r.phone}</a>
                      <span className="text-slate-500 whitespace-nowrap">{formatDateTime(r.at)}</span>
                    </div>
                    <div className="text-slate-300">{r.label} <span className="text-slate-500">· {who(r.by)}</span></div>
                    {r.note && <div className="text-slate-500 truncate" title={r.note}>{r.note}</div>}
                  </li>
                ))}
              </ul>
            ) : <div className="text-[12px] text-slate-500">Nothing recorded yet. Outcomes are recorded when a chat is handed back to the bot, when a question is resolved, or with "Change" above any chat.</div>}
          </div>
        </div>
      </div>
    </section>
  );
};
