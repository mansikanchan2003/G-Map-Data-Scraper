import React, { useEffect, useState } from 'react';
import { fetchNumberUsage, type NumberUsage } from '../api';
import { formatDateTime } from '../utils/datetime';

/**
 * What the shared WhatsApp number (+91 99118 44469) was used for, for the
 * admin: AutoGMap's sends beside the messages the other apps on the number
 * sent, seen through Meta's delivery updates, with their cost before GST.
 * Hidden for anyone the API refuses.
 */
export const NumberUsagePanel: React.FC = () => {
  const [u, setU] = useState<NumberUsage | null>(null);
  const [hidden, setHidden] = useState(false);
  const [days, setDays] = useState(7);
  useEffect(() => {
    fetchNumberUsage(days).then(setU).catch(() => setHidden(true));
  }, [days]);
  if (hidden || !u) return null;
  const max = Math.max(1, ...u.days.map(d => d.autogmap + d.others));
  return (
    <section className="rounded-lg border border-slate-800 bg-slate-900 p-4 select-text">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="text-sm font-semibold text-slate-100 flex items-center gap-1.5">
          <span className="material-symbols-outlined text-[18px] text-emerald-400">forum</span>
          WhatsApp number usage · +91 99118 44469
        </h2>
        <div className="flex gap-1 text-[11px]">
          {[7, 30].map(n => (
            <button key={n} onClick={() => setDays(n)}
              className={`px-2 py-0.5 rounded cursor-pointer ${days === n ? 'bg-slate-800 text-slate-100' : 'text-slate-500 hover:text-slate-300'}`}>
              {n} days
            </button>
          ))}
        </div>
      </div>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mt-3">
        {[
          ['AutoGMap sent', u.autogmap_total.toLocaleString('en-IN')],
          ['Other apps sent', u.others_total.toLocaleString('en-IN')],
          ['Other apps cost', `₹${u.others_cost_inr.toLocaleString('en-IN')}`],
          ['Last other message', u.last_other_message_at ? formatDateTime(u.last_other_message_at) : '—'],
        ].map(([label, value]) => (
          <div key={label} className="rounded-md border border-slate-800 bg-slate-950/60 px-3 py-2">
            <div className="text-[10.5px] uppercase tracking-wider text-slate-500">{label}</div>
            <div className="text-lg font-semibold text-slate-100 tabular-nums">{value}</div>
          </div>
        ))}
      </div>
      <div className="mt-3 space-y-1">
        {u.days.slice(-days).map(d => (
          <div key={d.day} className="grid grid-cols-[72px_1fr_210px] items-center gap-2 text-[11.5px]"
            title={`${d.day}: AutoGMap ${d.autogmap}, other apps ${d.others} (${Object.entries(d.others_by_category).map(([k, v]) => `${k} ${v}`).join(', ') || 'none'})`}>
            <span className="text-slate-500">{d.day.slice(5)}</span>
            <span className="h-2.5 rounded-full bg-slate-800 overflow-hidden flex">
              <span className="h-full bg-sky-500" style={{ width: `${(d.autogmap / max) * 100}%` }} />
              <span className="h-full bg-amber-400" style={{ width: `${(d.others / max) * 100}%` }} />
            </span>
            <span className="text-slate-400 tabular-nums">
              <span className="text-sky-300">AutoGMap {d.autogmap}</span> · <span className="text-amber-300">others {d.others}</span> · ₹{d.others_cost_inr}
            </span>
          </div>
        ))}
        {!u.days.length && <div className="text-[12px] text-slate-500">Nothing yet: counting starts once this is live.</div>}
      </div>
      <p className="text-[11px] text-slate-500 mt-2">{u.note}</p>
    </section>
  );
};
