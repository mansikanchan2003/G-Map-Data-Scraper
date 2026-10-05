import React, { useEffect, useRef, useState } from 'react';

/**
 * The export formats, behind one button.
 *
 * Three buttons sat in the action bar permanently while being used rarely —
 * and one of them, Google Sheets, is not a download at all but a link out to a
 * live sheet. Folding them into a menu gives the row back its width and puts
 * the choice where the choice is being made.
 */

interface Props {
  onCsv: () => void;
  onExcel: () => void;
  /** Opens the live sheet; null while no sheet has been configured. */
  sheetUrl: string | null;
  onSheetSync: () => void;
  sheetBusy?: boolean;
  /** Why the sheet is unavailable, shown in place of the link. */
  sheetUnavailable?: string | null;
}

export const DownloadMenu: React.FC<Props> = ({
  onCsv, onExcel, sheetUrl, onSheetSync, sheetBusy, sheetUnavailable,
}) => {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  // A menu that only closes on its own button is a menu people leave open.
  useEffect(() => {
    if (!open) return;
    const onDocClick = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    const onEsc = (e: KeyboardEvent) => e.key === 'Escape' && setOpen(false);
    document.addEventListener('mousedown', onDocClick);
    document.addEventListener('keydown', onEsc);
    return () => {
      document.removeEventListener('mousedown', onDocClick);
      document.removeEventListener('keydown', onEsc);
    };
  }, [open]);

  const item =
    'w-full flex items-start gap-2.5 px-3 py-2 text-left rounded hover:bg-slate-800 ' +
    'transition-colors cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed';

  return (
    <div className="relative" ref={ref}>
      <button
        onClick={() => setOpen(v => !v)}
        aria-expanded={open}
        aria-haspopup="menu"
        className="h-8 px-3.5 bg-emerald-600 hover:bg-emerald-500 text-white font-mono-code
                   text-xs font-semibold rounded flex items-center gap-2 transition-all
                   shadow-sm cursor-pointer active:scale-95"
        title="Export this dataset"
      >
        <span className="material-symbols-outlined text-[17px]">download</span>
        <span>Export</span>
        <span className={`material-symbols-outlined text-[16px] transition-transform ${open ? 'rotate-180' : ''}`}>
          expand_more
        </span>
      </button>

      {open && (
        <div
          role="menu"
          className="absolute left-0 sm:left-auto sm:right-0 top-full mt-1.5 z-50 w-72
                     bg-slate-900 border border-slate-700 rounded shadow-xl p-1.5 flex flex-col gap-0.5"
        >
          <button className={item} onClick={() => { onCsv(); setOpen(false); }}>
            <span className="material-symbols-outlined text-[18px] text-slate-300 mt-0.5">description</span>
            <span className="min-w-0">
              <span className="block text-xs font-semibold text-slate-100">CSV</span>
              <span className="block text-[11px] text-slate-500">Streamed from the backend</span>
            </span>
          </button>

          <button className={item} onClick={() => { onExcel(); setOpen(false); }}>
            <span className="material-symbols-outlined text-[18px] text-emerald-400 mt-0.5">table</span>
            <span className="min-w-0">
              <span className="block text-xs font-semibold text-slate-100">Excel (.xlsx)</span>
              <span className="block text-[11px] text-slate-500">Same data, native workbook</span>
            </span>
          </button>

          <div className="h-px bg-slate-800 my-1" />

          {sheetUrl ? (
            <>
              <a
                href={sheetUrl}
                target="_blank"
                rel="noopener noreferrer"
                className={item}
                onClick={() => setOpen(false)}
              >
                <span className="material-symbols-outlined text-[18px] text-sky-400 mt-0.5">open_in_new</span>
                <span className="min-w-0">
                  <span className="block text-xs font-semibold text-slate-100">Open Google Sheet</span>
                  <span className="block text-[11px] text-slate-500">
                    Opens the live sheet; you need access to it
                  </span>
                </span>
              </a>
              <button className={item} data-edit onClick={() => { onSheetSync(); setOpen(false); }} disabled={sheetBusy}>
                <span className={`material-symbols-outlined text-[18px] text-sky-400 mt-0.5 ${sheetBusy ? 'animate-spin' : ''}`}>
                  {sheetBusy ? 'progress_activity' : 'sync'}
                </span>
                <span className="min-w-0">
                  <span className="block text-xs font-semibold text-slate-100">
                    {sheetBusy ? 'Updating sheet…' : 'Update the sheet now'}
                  </span>
                  <span className="block text-[11px] text-slate-500">Replaces its contents with today's data</span>
                </span>
              </button>
            </>
          ) : (
            <div className="px-3 py-2">
              <span className="block text-xs font-semibold text-slate-400">Google Sheet</span>
              <span className="block text-[11px] text-slate-500 mt-0.5">
                {sheetUnavailable || 'Not configured yet.'}
              </span>
            </div>
          )}
        </div>
      )}
    </div>
  );
};
