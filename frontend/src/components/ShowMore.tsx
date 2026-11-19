import React, { useState } from 'react';

/**
 * Long lists, short at first (19 Nov 2026: the plans and "Call these people first" ran the
 * page very long). The first few show; a button opens the rest and closes them again.
 */

/** The first `first` items, and a toggle for the rest. */
export function useShowMore<T>(items: T[], first: number) {
  const [open, setOpen] = useState(false);
  const hidden = Math.max(0, items.length - first);
  return { shown: open || !hidden ? items : items.slice(0, first), hidden, open, toggle: () => setOpen(o => !o) };
}

export const ShowMoreButton: React.FC<{ hidden: number; open: boolean; onClick: () => void; noun?: string; className?: string }> =
  ({ hidden, open, onClick, noun = 'more', className = '' }) => {
    if (!hidden) return null;
    return (
      <button type="button" onClick={onClick}
        className={`w-full mt-2 h-9 rounded-lg border border-slate-800 bg-slate-950/60 hover:bg-slate-800/60 text-[12.5px] font-semibold text-sky-300 flex items-center justify-center gap-1.5 transition-colors ${className}`}>
        <span className="material-symbols-outlined text-[17px]" aria-hidden="true">{open ? 'expand_less' : 'expand_more'}</span>
        {open ? 'Show less' : `Show ${hidden} ${noun}`}
      </button>
    );
  };
