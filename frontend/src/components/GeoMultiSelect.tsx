import React, { useEffect, useMemo, useRef, useState } from 'react';

export interface GeoChoice {
  /** Unique across the list, e.g. "Gujarat|Rajkot" for a district. */
  key: string;
  label: string;
  /** The level above, shown beside the name so repeated names can be told apart. */
  sub?: string | null;
  count: number;
}

interface Props {
  label: string;
  /** Plural, for "All states" and "3 states". */
  plural: string;
  choices: GeoChoice[];
  selected: string[];
  onChange: (keys: string[]) => void;
}

/**
 * A dropdown that takes any number of places, with counts and a search box.
 * Nothing ticked means all of them.
 */
export const GeoMultiSelect: React.FC<Props> = ({ label, plural, choices, selected, onChange }) => {
  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState('');
  const box = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const close = (e: MouseEvent) => {
      if (box.current && !box.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener('mousedown', close);
    return () => document.removeEventListener('mousedown', close);
  }, [open]);

  const picked = new Set(selected);
  const shown = useMemo(() => {
    const q = search.trim().toLowerCase();
    return q ? choices.filter(c => `${c.label} ${c.sub ?? ''}`.toLowerCase().includes(q)) : choices;
  }, [choices, search]);

  const toggle = (key: string) =>
    onChange(picked.has(key) ? selected.filter(k => k !== key) : [...selected, key]);

  const names = choices.filter(c => picked.has(c.key)).map(c => c.label);
  const summary = names.length === 0 ? `All ${plural}`
    : names.length <= 2 ? names.join(', ')
    : `${names.length} ${plural}`;

  return (
    <div className="flex flex-col gap-1 relative" ref={box}>
      <label className="text-[10px] uppercase tracking-wider text-slate-500 font-semibold">{label}</label>
      <button
        type="button"
        onClick={() => setOpen(o => !o)}
        disabled={choices.length === 0 && selected.length === 0}
        className="bg-slate-950 border border-slate-700 rounded px-3 py-2 text-sm text-slate-200 text-left flex items-center justify-between gap-2 disabled:opacity-50"
        title={names.join(', ') || undefined}
      >
        <span className="truncate">{summary}</span>
        <span className="material-symbols-outlined text-[18px] text-slate-500">{open ? 'expand_less' : 'expand_more'}</span>
      </button>

      {open && (
        <div className="absolute top-full left-0 right-0 mt-1 z-20 bg-slate-900 border border-slate-700 rounded-lg shadow-2xl">
          <div className="p-2 border-b border-slate-800 flex items-center gap-2">
            <input
              autoFocus
              value={search}
              onChange={e => setSearch(e.target.value)}
              placeholder={`Search ${plural}`}
              className="flex-1 min-w-0 bg-slate-950 border border-slate-700 rounded px-2 py-1.5 text-xs text-slate-200 outline-none"
            />
            {selected.length > 0 && (
              <button type="button" onClick={() => onChange([])}
                className="text-[11px] text-sky-400 hover:text-sky-300 font-semibold shrink-0">
                Clear
              </button>
            )}
          </div>
          <div className="max-h-64 overflow-y-auto py-1">
            {shown.length === 0 ? (
              <div className="px-3 py-3 text-xs text-slate-500">No {plural} match</div>
            ) : shown.map(c => (
              <label key={c.key}
                className="flex items-center gap-2 px-3 py-1.5 text-sm text-slate-200 hover:bg-slate-800 cursor-pointer">
                <input type="checkbox" checked={picked.has(c.key)} onChange={() => toggle(c.key)}
                  className="accent-emerald-500" />
                <span className="flex-1 min-w-0 truncate">
                  {c.label}
                  {c.sub && <span className="text-slate-500 text-xs"> · {c.sub}</span>}
                </span>
                <span className="text-xs text-slate-500">{c.count.toLocaleString()}</span>
              </label>
            ))}
          </div>
        </div>
      )}
    </div>
  );
};
