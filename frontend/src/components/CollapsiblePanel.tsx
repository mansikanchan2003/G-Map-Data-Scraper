import React, { useState } from 'react';

/**
 * A card whose heading is the control that opens it.
 *
 * The dashboard's lower panels are reference material — the last run, the
 * engine's wiring, the manual controls — read occasionally rather than
 * watched. Closed by default they stop competing with the numbers above them,
 * and the page fits a phone without a long scroll past detail nobody asked
 * for.
 *
 * The whole header row is the button, not a separate chevron: a heading that
 * looks clickable should be clickable, and a small target is the part people
 * miss.
 */

interface Props {
  icon: string;
  /** Tailwind colour class for the icon, so each panel keeps its own accent. */
  iconClass?: string;
  title: string;
  /** Status shown beside the title; informational only, never interactive. */
  badge?: React.ReactNode;
  defaultOpen?: boolean;
  children: React.ReactNode;
}

export const CollapsiblePanel: React.FC<Props> = ({
  icon, iconClass = 'text-slate-400', title, badge, defaultOpen = false, children,
}) => {
  const [open, setOpen] = useState(defaultOpen);

  return (
    <div className="bg-slate-900 border border-slate-800 rounded shadow-sm overflow-hidden">
      <button
        onClick={() => setOpen(v => !v)}
        aria-expanded={open}
        className={`w-full flex items-center justify-between gap-3 p-4 text-left
                    hover:bg-slate-800/40 transition-colors cursor-pointer
                    ${open ? 'border-b border-slate-800' : ''}`}
      >
        <span className="flex items-center gap-2 min-w-0">
          <span className={`material-symbols-outlined text-[20px] shrink-0 ${iconClass}`}>
            {icon}
          </span>
          <h3 className="text-base font-semibold text-slate-100 truncate">{title}</h3>
        </span>

        <span className="flex items-center gap-2 shrink-0">
          {badge}
          <span
            className={`material-symbols-outlined text-[20px] text-slate-500 transition-transform
                        ${open ? 'rotate-180' : ''}`}
          >
            expand_more
          </span>
        </span>
      </button>

      {open && <div className="p-4 flex flex-col gap-4">{children}</div>}
    </div>
  );
};
