import React, { useEffect, useState } from 'react';
import { fetchMissingSteps, type MissingSteps } from '../api/inbox';
import { formatDateTime } from '../utils/datetime';

/**
 * The Dashboard's flag for leads whose recorded steps do not add up: a tap
 * with no sent message, documents without the qualifying answers, a read
 * with no delivered update. Each opens its chat. Quiet, and green, when every
 * journey adds up.
 */

const Icon: React.FC<{ name: string; className?: string }> = ({ name, className = '' }) =>
  <span className={`material-symbols-outlined ${className}`} aria-hidden="true">{name}</span>;

const SEVERITY: Record<string, { label: string; chip: string; dot: string }> = {
  high: { label: 'Needs a look', chip: 'bg-rose-950 border-rose-800/60 text-rose-300', dot: 'bg-rose-500' },
  medium: { label: 'Check', chip: 'bg-amber-950 border-amber-800/60 text-amber-300', dot: 'bg-amber-400' },
  low: { label: 'Minor', chip: 'bg-slate-800 border-slate-700 text-slate-300', dot: 'bg-slate-500' },
};

export const MissingStepsCard: React.FC = () => {
  const [d, setD] = useState<MissingSteps | null>(null);
  const [hidden, setHidden] = useState(false);
  const [check, setCheck] = useState<string | null>(null);
  const [all, setAll] = useState(false);
  useEffect(() => { fetchMissingSteps().then(setD).catch(() => setHidden(true)); }, []);
  if (hidden || !d) return null;

  if (!d.total) {
    return (
      <section className="rounded-xl border border-emerald-800/60 bg-emerald-950 px-4 py-3 flex items-center gap-2 text-[13px] text-emerald-300">
        <Icon name="verified" className="text-[18px]" />Every lead's journey adds up: no missing steps.
      </section>
    );
  }
  const shown = d.flags.filter(f => !check || f.check === check);
  const list = all ? shown : shown.slice(0, 6);
  return (
    <section className="rounded-xl border border-amber-800/60 bg-slate-900 shadow-sm overflow-hidden select-text">
      <div className="px-4 py-3 flex flex-wrap items-center gap-3 border-b border-slate-800 bg-amber-950/40">
        <span className="h-9 w-9 rounded-lg bg-amber-950 text-amber-300 flex items-center justify-center"><Icon name="rule" className="text-[20px]" /></span>
        <div className="flex-1 min-w-[220px]">
          <h2 className="text-sm font-semibold text-slate-100">Missing steps in lead journeys</h2>
          <p className="text-[12px] text-slate-400">
            <b className="text-slate-200 tabular-nums">{d.leads}</b> {d.leads === 1 ? 'lead has' : 'leads have'} a step with no record of the one before it.
          </p>
        </div>
        <span className="text-2xl font-bold tabular-nums text-amber-300">{d.total}</span>
      </div>
      <div className="px-4 pt-3 flex flex-wrap gap-1.5">
        {d.by_check.map(c => (
          <button key={c.check} onClick={() => setCheck(check === c.check ? null : c.check)}
            className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full border text-[11.5px] cursor-pointer ${check === c.check
              ? 'ring-2 ring-sky-500 ' + SEVERITY[c.severity].chip : SEVERITY[c.severity].chip}`}>
            <span className={`h-1.5 w-1.5 rounded-full ${SEVERITY[c.severity].dot}`} />{c.label}
            <b className="tabular-nums">{c.count}</b>
          </button>
        ))}
      </div>
      <ul className="px-4 py-3 space-y-1.5">
        {list.map((f, i) => (
          <li key={`${f.phone}-${f.check}-${i}`} className="grid grid-cols-[10px_1fr_auto] items-start gap-2.5 text-[12.5px]">
            <span className={`h-2 w-2 rounded-full mt-1.5 ${SEVERITY[f.severity].dot}`} />
            <div className="min-w-0">
              <a href={`#inbox/${f.phone.replace(/\D/g, '')}`} className="font-semibold text-sky-300 hover:underline">{f.name || f.phone}</a>
              <span className="text-slate-300"> · {f.label}</span>
              {f.detail && <div className="text-[11.5px] text-slate-500 truncate">{f.detail}</div>}
            </div>
            <span className="text-[11px] text-slate-500 whitespace-nowrap">{f.at ? formatDateTime(f.at) : ''}</span>
          </li>
        ))}
      </ul>
      {shown.length > 6 && (
        <div className="px-4 pb-3">
          <button onClick={() => setAll(!all)} className="text-[12px] text-sky-300 hover:underline cursor-pointer">
            {all ? 'Show fewer' : `Show all ${shown.length}`}
          </button>
        </div>
      )}
    </section>
  );
};
