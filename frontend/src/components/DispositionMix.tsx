import React, { useEffect, useState } from 'react';
import { fetchDispositionMix, type DispositionMix as Mix, type MixGroup, type MixRow } from '../api/insights';

/**
 * Where the people each campaign, template and state reached stand now: each
 * person's current disposition (as in the Inbox), counted under the latest
 * campaign sent to them. One stacked bar per row in the Dispositions tab's
 * colours, each group with its label too, and the row's top dispositions.
 */

type Dim = 'campaign' | 'template' | 'state';

const GROUP: Record<MixGroup, { label: string; bar: string; dot: string }> = {
  positive: { label: 'Going well', bar: 'bg-emerald-500', dot: 'bg-emerald-500' },
  follow_up: { label: 'Follow up', bar: 'bg-amber-400', dot: 'bg-amber-400' },
  negative: { label: 'Closed', bar: 'bg-rose-500', dot: 'bg-rose-500' },
  other: { label: 'Other', bar: 'bg-slate-500', dot: 'bg-slate-500' },
  no_reply: { label: 'No reply yet', bar: 'bg-slate-700', dot: 'bg-slate-700' },
};
const ORDER: MixGroup[] = ['positive', 'follow_up', 'negative', 'other', 'no_reply'];
const DIMS: { key: Dim; label: string; icon: string }[] = [
  { key: 'campaign', label: 'Campaign', icon: 'campaign' },
  { key: 'template', label: 'Template', icon: 'article' },
  { key: 'state', label: 'State', icon: 'map' },
];
const pct = (n: number, total: number) => (total ? Math.round((n / total) * 100) : 0);

const Row: React.FC<{ r: MixRow }> = ({ r }) => (
  <li className="rounded-xl border border-slate-800 bg-slate-950/60 p-3">
    <div className="flex flex-wrap items-baseline justify-between gap-2">
      <span className="text-[13px] font-semibold text-slate-100">{r.value}</span>
      <span className="text-[11.5px] text-slate-500 tabular-nums">
        {r.sent.toLocaleString('en-IN')} reached · {r.replied.toLocaleString('en-IN')} replied ({pct(r.replied, r.sent)}%)
      </span>
    </div>
    <div className="mt-2 h-3 w-full rounded-full overflow-hidden flex bg-slate-800" role="img"
      aria-label={ORDER.map(g => `${GROUP[g].label} ${r.groups[g]}`).join(', ')}>
      {ORDER.filter(g => r.groups[g]).map(g => (
        <div key={g} className={`${GROUP[g].bar} h-full`} style={{ width: `${(r.groups[g] / r.sent) * 100}%` }}
          title={`${GROUP[g].label}: ${r.groups[g]} (${pct(r.groups[g], r.sent)}%)`} />
      ))}
    </div>
    <div className="mt-2 flex flex-wrap gap-x-3 gap-y-1 text-[11.5px] text-slate-400">
      {ORDER.filter(g => r.groups[g]).map(g => (
        <span key={g} className="inline-flex items-center gap-1.5">
          <span className={`h-2 w-2 rounded-full ${GROUP[g].dot}`} />{GROUP[g].label} <span className="tabular-nums text-slate-300">{r.groups[g]}</span>
        </span>
      ))}
    </div>
    {r.dispositions.some(d => d.group !== 'no_reply') && (
      <div className="mt-2 flex flex-wrap gap-1.5">
        {r.dispositions.filter(d => d.group !== 'no_reply').slice(0, 6).map(d => (
          <span key={d.label} className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full border border-slate-700 text-[11px] text-slate-300">
            <span className={`h-1.5 w-1.5 rounded-full ${GROUP[d.group]?.dot || GROUP.other.dot}`} />{d.label}
            <span className="tabular-nums text-slate-500">{d.count}</span>
          </span>
        ))}
      </div>
    )}
  </li>
);

export const DispositionMix: React.FC = () => {
  const [mix, setMix] = useState<Mix | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [dim, setDim] = useState<Dim>('campaign');
  useEffect(() => { fetchDispositionMix().then(setMix).catch(e => setError(e.message)); }, []);

  if (error) return <div className="p-4 rounded-xl border border-rose-800/60 bg-rose-950 text-rose-300 text-sm">Could not load the dispositions: {error}</div>;
  if (!mix) return <div className="h-40 rounded-2xl bg-slate-900 border border-slate-800 animate-pulse" />;
  const rows = mix[dim];

  return (
    <section className="rounded-xl border border-slate-800 bg-slate-900 shadow-sm p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-sm font-semibold text-slate-100">Where the people reached stand now</h2>
          <p className="text-[12.5px] text-slate-500 mt-1">
            Each person's disposition now, as in the Inbox, under the latest campaign sent to them. Test sends are left out.
          </p>
        </div>
        <div className="flex items-center gap-1 rounded-lg border border-slate-800 bg-slate-950 p-1">
          {DIMS.map(d => (
            <button key={d.key} onClick={() => setDim(d.key)}
              className={`px-3 py-1.5 rounded-md text-xs font-semibold inline-flex items-center gap-1 cursor-pointer ${dim === d.key
                ? 'bg-slate-800 text-slate-100' : 'text-slate-500 hover:text-slate-300'}`}>
              <span className="material-symbols-outlined text-[15px]">{d.icon}</span>{d.label}
            </button>
          ))}
        </div>
      </div>
      {rows.length ? (
        <ul className="mt-4 space-y-2">{rows.map(r => <Row key={r.value} r={r} />)}</ul>
      ) : (
        <div className="mt-4 py-8 text-center text-sm text-slate-500 rounded-xl border border-dashed border-slate-800">
          No campaign has been sent yet.
        </div>
      )}
    </section>
  );
};
