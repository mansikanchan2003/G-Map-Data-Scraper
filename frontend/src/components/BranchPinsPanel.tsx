import React, { useEffect, useState } from 'react';
import { fetchBranchPins, type BranchPin } from '../api';

/**
 * PINs targeted because SBI branches there want CSP operators, each with the
 * branches it serves. They are scraped like every other PIN; this section
 * only keeps them, and their branch codes, in view.
 */
export const BranchPinsPanel: React.FC<{ refreshKey?: number }> = ({ refreshKey }) => {
  const [pins, setPins] = useState<BranchPin[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchBranchPins()
      .then(setPins)
      .catch((err: any) => setError(err?.message || 'Could not load the SBI branch PINs'));
  }, [refreshKey]);

  // Nothing to show until a branch list has been added.
  if (pins !== null && pins.length === 0 && !error) return null;

  const branchCount = (pins || []).reduce((n, p) => n + p.branches.length, 0);

  return (
    <div className="shrink-0 mx-4 lg:mx-6 mt-4 bg-slate-900 border border-amber-800/70 rounded shadow-sm overflow-hidden">
      <div className="p-3 bg-slate-950 border-b border-slate-800 flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <span className="material-symbols-outlined text-amber-400 text-[18px]">account_balance</span>
          <h2 className="text-xs font-mono-code font-bold uppercase text-slate-200">
            SBI Branch PINs {pins ? `(${pins.length} PINs · ${branchCount} branches)` : ''}
          </h2>
        </div>
        <span className="text-[11px] text-slate-400">
          PIN codes of SBI branches looking for CSP operators · scraped like every other PIN
        </span>
      </div>

      {error ? (
        <div className="p-4 text-xs text-rose-300">{error}</div>
      ) : pins === null ? (
        <div className="p-6 text-center text-xs text-slate-500">Loading SBI branch PINs...</div>
      ) : (
        <div className="overflow-auto max-h-[420px]">
          <table className="w-full text-left border-collapse select-text text-xs font-mono-code">
            <thead className="sticky top-0 bg-slate-950/90 border-b border-slate-800 text-[10px] text-slate-400 uppercase font-bold">
              <tr className="h-8">
                <th className="px-3 border-r border-slate-800">PIN Code</th>
                <th className="px-3 border-r border-slate-800">Town</th>
                <th className="px-3 border-r border-slate-800">District</th>
                <th className="px-3 border-r border-slate-800">State</th>
                <th className="px-3 border-r border-slate-800">Branch Code</th>
                <th className="px-3 border-r border-slate-800">Branch Name</th>
                <th className="px-3 border-r border-slate-800">IFSC</th>
                <th className="px-3 border-r border-slate-800">SBI Module</th>
                <th className="px-3">Scraping</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800">
              {pins.map(pin => {
                const loc = pin.location;
                const done = pin.jobs.completed;
                return (
                  <tr key={pin.pincode} className="hover:bg-slate-800/50 align-top">
                    <td className="px-3 py-2 border-r border-slate-800 font-semibold text-amber-300">{pin.pincode}</td>
                    <td className="px-3 py-2 border-r border-slate-800 text-slate-300">
                      {loc?.anchor_name || pin.branches[0]?.town || '—'}
                    </td>
                    <td className="px-3 py-2 border-r border-slate-800 text-slate-300">
                      {loc?.district || pin.branches[0]?.district || '—'}
                    </td>
                    <td className="px-3 py-2 border-r border-slate-800 text-slate-300">
                      {loc?.state || pin.branches[0]?.state || '—'}
                    </td>
                    {/* A PIN can be served by several branches: one line each. */}
                    <td className="px-3 py-2 border-r border-slate-800 text-sky-300">
                      {pin.branches.map(b => <div key={b.branch_code}>{b.branch_code}</div>)}
                    </td>
                    <td className="px-3 py-2 border-r border-slate-800 text-slate-200">
                      {pin.branches.map(b => (
                        <div key={b.branch_code} title={b.note || b.address || undefined}>
                          {b.branch_name}{b.note ? ' ⚠' : ''}
                        </div>
                      ))}
                    </td>
                    <td className="px-3 py-2 border-r border-slate-800 text-slate-400">
                      {pin.branches.map(b => <div key={b.branch_code}>{b.ifsc || '—'}</div>)}
                    </td>
                    <td className="px-3 py-2 border-r border-slate-800 text-slate-400">
                      {pin.branches.map(b => <div key={b.branch_code}>{b.module || '—'}</div>)}
                    </td>
                    <td className="px-3 py-2 text-slate-300 whitespace-nowrap">
                      {!loc ? (
                        <span className="text-rose-300" title="This PIN could not be placed on the map, so it has no jobs">
                          Not on the map
                        </span>
                      ) : (
                        <span title={`${pin.jobs.pending} pending · ${pin.jobs.failed} failed`}>
                          {done}/{pin.jobs.total} jobs · {pin.businesses_saved} businesses
                        </span>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
};
