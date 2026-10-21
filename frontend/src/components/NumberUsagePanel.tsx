import React, { useEffect, useState } from 'react';
import { fetchNumberUsage, type NumberUsage } from '../api';
import { formatDateTime } from '../utils/datetime';

// AutoGMap in sky, the other apps in Eko's amber, on Campaign Insights' deep-teal banner.
const OURS = '#38bdf8';
const THEIRS = '#f9ab10';

const Icon: React.FC<{ name: string; className?: string; style?: React.CSSProperties }> = ({ name, className = '', style }) => (
  <span className={`material-symbols-outlined ${className}`} style={style} aria-hidden="true">{name}</span>
);

const inr = (n: number) => `₹${n.toLocaleString('en-IN', { maximumFractionDigits: 2 })}`;
const CATEGORY: Record<string, string> = { marketing: 'Marketing', utility: 'Utility', authentication: 'Authentication', service: 'Service' };

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

  const shown = u.days.slice(-days);
  const total = u.autogmap_total + u.others_total;
  const ourShare = total ? Math.round((u.autogmap_total / total) * 100) : 0;
  const max = Math.max(1, ...shown.map(d => d.autogmap + d.others));
  const categories: Record<string, number> = {};
  let delivered = 0, read = 0;
  for (const d of shown) {
    for (const [k, v] of Object.entries(d.others_by_category)) categories[k] = (categories[k] || 0) + v;
    delivered += d.others_delivered;
    read += d.others_read;
  }
  const catRows = Object.entries(categories).sort((a, b) => b[1] - a[1]);
  const catMax = Math.max(1, ...catRows.map(([, v]) => v));

  const tiles: [string, string, string, string][] = [
    ['send', 'AutoGMap sent', u.autogmap_total.toLocaleString('en-IN'), OURS],
    ['apps', 'Other apps sent', u.others_total.toLocaleString('en-IN'), THEIRS],
    ['currency_rupee', 'Other apps cost', inr(u.others_cost_inr), THEIRS],
    ['schedule', 'Last other message', u.last_other_message_at ? formatDateTime(u.last_other_message_at) : '—', '#ffffff'],
  ];

  return (
    <div className="space-y-4 select-text">
      <section className="rounded-2xl overflow-hidden shadow-md text-white"
        style={{ background: 'linear-gradient(120deg, #0a3543 0%, #16435a 55%, #1d5a6e 100%)' }}>
        <div className="p-6 flex flex-wrap items-end justify-between gap-4">
          <div>
            <div className="text-[11px] uppercase tracking-[0.14em] font-semibold flex flex-wrap items-center gap-2" style={{ color: THEIRS }}>
              <Icon name="forum" className="text-[15px]" />WhatsApp number usage
              <span className="normal-case tracking-normal font-medium text-[10.5px] px-2 py-0.5 rounded-full bg-white/10 text-white/80">
                +91 99118 44469 · shared with other Eko apps
              </span>
            </div>
            <div className="mt-1 flex items-baseline gap-3">
              <span className="text-4xl sm:text-5xl font-semibold tabular-nums">{total.toLocaleString('en-IN')}</span>
              <span className="text-sm text-white/75">messages in the last <b className="text-white">{days}</b> days · <b className="text-white">{ourShare}%</b> from AutoGMap</span>
            </div>
            <div className="mt-3 h-2.5 w-full max-w-md rounded-full bg-white/10 overflow-hidden flex">
              <span className="h-full" style={{ width: `${ourShare}%`, background: OURS }} />
              <span className="h-full" style={{ width: `${total ? 100 - ourShare : 0}%`, background: THEIRS }} />
            </div>
            <div className="mt-1.5 flex gap-4 text-[11.5px] text-white/70">
              <span className="flex items-center gap-1.5"><span className="h-2 w-2 rounded-full" style={{ background: OURS }} />AutoGMap</span>
              <span className="flex items-center gap-1.5"><span className="h-2 w-2 rounded-full" style={{ background: THEIRS }} />Other apps</span>
            </div>
          </div>
          <div className="flex gap-1 rounded-full bg-white/10 p-1 text-[12px]">
            {[7, 30].map(n => (
              <button key={n} onClick={() => setDays(n)}
                className={`px-3 py-1 rounded-full cursor-pointer transition-colors ${days === n ? 'bg-white text-[#0a3543] font-semibold' : 'text-white/75 hover:text-white'}`}>
                {n} days
              </button>
            ))}
          </div>
        </div>
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 px-6 pb-6">
          {tiles.map(([icon, label, value, accent]) => (
            <div key={label} className="rounded-lg bg-white/10 px-4 py-3">
              <div className="flex items-center gap-1.5 text-white/70 text-[12px]">
                <Icon name={icon} className="text-[16px]" style={{ color: accent }} />{label}
              </div>
              <div className={`font-semibold tabular-nums mt-1 ${label === 'Last other message' ? 'text-base' : 'text-2xl'}`}>{value}</div>
            </div>
          ))}
        </div>
      </section>

      <div className="grid gap-4 xl:grid-cols-[1.6fr_1fr]">
        <section className="rounded-xl border border-slate-800 bg-slate-900 p-5">
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-semibold text-slate-100 flex items-center gap-1.5">
              <Icon name="bar_chart" className="text-[18px] text-sky-400" />Day by day
            </h3>
            <span className="text-[11px] text-slate-500">Hover a day for its numbers</span>
          </div>
          {shown.length ? (
            <div className="mt-4 flex items-end gap-2 h-44">
              {shown.map(d => {
                const sum = d.autogmap + d.others;
                return (
                  <div key={d.day} className="group flex-1 min-w-0 h-full flex flex-col items-center justify-end gap-1"
                    title={`${d.day}: AutoGMap ${d.autogmap}, other apps ${d.others}${d.others_cost_inr ? ` (${inr(d.others_cost_inr)})` : ''}`}>
                    <span className="text-[10.5px] tabular-nums text-slate-400 opacity-0 group-hover:opacity-100 transition-opacity">{sum}</span>
                    <div className="w-full max-w-[44px] rounded-t-md overflow-hidden flex flex-col-reverse bg-slate-800/60"
                      style={{ height: `${Math.max(3, (sum / max) * 100)}%` }}>
                      <span style={{ height: `${sum ? (d.autogmap / sum) * 100 : 0}%`, background: OURS }} />
                      <span style={{ height: `${sum ? (d.others / sum) * 100 : 0}%`, background: THEIRS }} />
                    </div>
                    <span className="text-[10.5px] text-slate-500 tabular-nums">{d.day.slice(5)}</span>
                  </div>
                );
              })}
            </div>
          ) : (
            <div className="text-[12px] text-slate-500 mt-4">Nothing yet: counting starts once this is live.</div>
          )}
        </section>

        <section className="rounded-xl border border-slate-800 bg-slate-900 p-5">
          <h3 className="text-sm font-semibold text-slate-100 flex items-center gap-1.5">
            <Icon name="category" className="text-[18px] text-amber-400" />What the other apps sent
          </h3>
          {catRows.length ? (
            <ul className="mt-4 space-y-3">
              {catRows.map(([k, v]) => (
                <li key={k} className="text-[13px]">
                  <div className="flex justify-between text-slate-300">
                    <span>{CATEGORY[k] || k}</span><span className="tabular-nums font-semibold text-slate-100">{v}</span>
                  </div>
                  <div className="h-2 rounded-full bg-slate-800 mt-1 overflow-hidden">
                    <div className="h-full rounded-full" style={{ width: `${(v / catMax) * 100}%`, background: THEIRS }} />
                  </div>
                </li>
              ))}
            </ul>
          ) : (
            <div className="text-[12px] text-slate-500 mt-4">No messages from other apps in this period.</div>
          )}
          {u.others_total > 0 && (
            <div className="mt-4 grid grid-cols-2 gap-2 text-[12px]">
              <div className="rounded-lg bg-slate-950/60 border border-slate-800 px-3 py-2">
                <div className="text-slate-500">Delivered</div>
                <div className="text-lg font-semibold tabular-nums text-slate-100">{delivered}</div>
              </div>
              <div className="rounded-lg bg-slate-950/60 border border-slate-800 px-3 py-2">
                <div className="text-slate-500">Read</div>
                <div className="text-lg font-semibold tabular-nums text-slate-100">{read}</div>
              </div>
            </div>
          )}
        </section>
      </div>
      <p className="text-[11px] text-slate-500">{u.note}</p>
    </div>
  );
};
