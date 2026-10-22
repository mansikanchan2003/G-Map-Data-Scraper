import React, { useEffect, useState } from 'react';
import { fetchMissingActions, type MissingSteps } from '../api/inbox';
import { formatDateTime } from '../utils/datetime';

/**
 * The Dashboard's alert for missing dispositions and action items (the
 * user, 2026-10-22): leads with no disposition where one is due, and
 * dispositions whose action item is missing or overdue, each opening its
 * chat. Beside the missing-step alert (MissingStepsCard), which keeps to
 * records that do not add up. Quiet, and green, when nothing is missing.
 */

const Icon: React.FC<{ name: string; className?: string }> = ({ name, className = '' }) =>
  <span className={`material-symbols-outlined ${className}`} aria-hidden="true">{name}</span>;

const SEVERITY: Record<string, { chip: string; dot: string }> = {
  high: { chip: 'bg-rose-950 border-rose-800/60 text-rose-300', dot: 'bg-rose-500' },
  medium: { chip: 'bg-amber-950 border-amber-800/60 text-amber-300', dot: 'bg-amber-400' },
  low: { chip: 'bg-slate-800 border-slate-700 text-slate-300', dot: 'bg-slate-500' },
};
const GROUP_ICON: Record<string, { icon: string; tint: string }> = {
  disposition: { icon: 'label_off', tint: 'bg-rose-950 text-rose-300' },
  action: { icon: 'pending_actions', tint: 'bg-amber-950 text-amber-300' },
  record: { icon: 'rule', tint: 'bg-slate-800 text-slate-300' },
};

type Flag = MissingSteps['flags'][number];

const Rows: React.FC<{ flags: Flag[] }> = ({ flags }) => {
  const [all, setAll] = useState(false);
  const list = all ? flags : flags.slice(0, 5);
  return (
    <>
      <ul className="space-y-1.5">
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
      {flags.length > 5 && (
        <button onClick={() => setAll(!all)} className="mt-2 text-[12px] text-sky-300 hover:underline cursor-pointer">
          {all ? 'Show fewer' : `Show all ${flags.length}`}
        </button>
      )}
    </>
  );
};

export const DispositionAlertCard: React.FC = () => {
  const [d, setD] = useState<MissingSteps | null>(null);
  const [hidden, setHidden] = useState(false);
  const [check, setCheck] = useState<string | null>(null);
  useEffect(() => { fetchMissingActions().then(setD).catch(() => setHidden(true)); }, []);
  if (hidden || !d) return null;

  const main = d.flags.filter(f => f.group !== 'record');
  const mainLeads = new Set(main.map(f => f.phone)).size;

  if (!main.length) {
    return (
      <section className="rounded-xl border border-emerald-800/60 bg-emerald-950 px-4 py-3 flex items-center gap-2 text-[13px] text-emerald-300">
        <Icon name="verified" className="text-[18px]" />Every lead has its disposition and its action items are on track.
      </section>
    );
  }

  return (
    <section className={`rounded-xl border bg-slate-900 shadow-sm overflow-hidden select-text ${main.length ? 'border-amber-800/60' : 'border-slate-800'}`}>
      <div className={`px-4 py-3 flex flex-wrap items-center gap-3 border-b border-slate-800 ${main.length ? 'bg-amber-950/40' : ''}`}>
        <span className="h-9 w-9 rounded-lg bg-amber-950 text-amber-300 flex items-center justify-center"><Icon name="assignment_late" className="text-[20px]" /></span>
        <div className="flex-1 min-w-[220px]">
          <h2 className="text-sm font-semibold text-slate-100">Missing dispositions and action items</h2>
          <p className="text-[12px] text-slate-400">
            {main.length
              ? <><b className="text-slate-200 tabular-nums">{mainLeads}</b> {mainLeads === 1 ? 'lead needs' : 'leads need'} a disposition recorded or an action item done.</>
              : 'Every lead has its disposition and its action items are on track.'}
          </p>
        </div>
        <span className="text-2xl font-bold tabular-nums text-amber-300">{main.length || ''}</span>
      </div>

      {main.length > 0 && (
        <div className="p-4 grid gap-4 xl:grid-cols-2">
          {d.groups.filter(g => g.group !== 'record').map(g => {
            const flags = main.filter(f => f.group === g.group && (!check || f.check === check));
            const checks = d.by_check.filter(c => c.group === g.group);
            const gi = GROUP_ICON[g.group];
            return (
              <div key={g.group} className="rounded-lg border border-slate-800 bg-slate-950/50 p-3.5">
                <div className="flex items-center gap-2 mb-2.5">
                  <span className={`h-7 w-7 rounded-md flex items-center justify-center ${gi.tint}`}><Icon name={gi.icon} className="text-[16px]" /></span>
                  <h3 className="text-[13px] font-semibold text-slate-100 flex-1">{g.label}</h3>
                  <b className="tabular-nums text-slate-100">{g.count}</b>
                </div>
                {checks.length > 0 && (
                  <div className="flex flex-wrap gap-1.5 mb-2.5">
                    {checks.map(c => (
                      <button key={c.check} onClick={() => setCheck(check === c.check ? null : c.check)}
                        className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full border text-[11px] cursor-pointer ${SEVERITY[c.severity].chip} ${check === c.check ? 'ring-2 ring-sky-500' : ''}`}>
                        {c.label}<b className="tabular-nums">{c.count}</b>
                      </button>
                    ))}
                  </div>
                )}
                {flags.length ? <Rows flags={flags} /> : <div className="text-[12.5px] text-slate-500">Nothing missing here.</div>}
              </div>
            );
          })}
        </div>
      )}

    </section>
  );
};
