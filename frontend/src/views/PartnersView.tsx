import React, { useEffect, useMemo, useState } from 'react';
import { fetchPartners, type PartnerList, type PartnerOrganisation } from '../api/partners';

/**
 * Organisations near SBI branches that help people find work or start a
 * business: RSETIs, NGOs, SHGs, skill centres and the like.
 *
 * These are partners to approach, not people to message: they can refer the
 * people they serve, who then write to us themselves. Individuals are not
 * collected, to stay within the DPDP Act and WhatsApp's opt-in rule.
 */

const csvCell = (v: unknown) => `"${String(v ?? '').replace(/"/g, '""')}"`;

const downloadCsv = (rows: PartnerOrganisation[]) => {
  const head = ['Name', 'Type', 'Phone', 'Email', 'Website', 'Address', 'District', 'State', 'PIN', 'SBI branch', 'Google Maps'];
  const lines = [head.map(csvCell).join(',')].concat(rows.map(p => [
    p.name, p.type, p.phone, p.email, p.website, p.address, p.district, p.state, p.pincode,
    p.branches.map(b => `${b.name} (${b.code})`).join('; '), p.google_maps_url,
  ].map(csvCell).join(',')));
  const blob = new Blob(['﻿' + lines.join('\n')], { type: 'text/csv;charset=utf-8' });
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = 'partner_organisations.csv';
  a.click();
  URL.revokeObjectURL(a.href);
};

const selectCls = 'h-9 px-2 bg-slate-950 border border-slate-700 rounded text-sm text-slate-100';

export const PartnersView: React.FC = () => {
  const [data, setData] = useState<PartnerList | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [type, setType] = useState('');
  const [branch, setBranch] = useState('');
  const [q, setQ] = useState('');
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    const t = setTimeout(() => {
      fetchPartners({ type, branch, q })
        .then(d => { setData(d); setError(null); })
        .catch(e => setError(e.message))
        .finally(() => setLoading(false));
    }, 250);
    return () => clearTimeout(t);
  }, [type, branch, q]);

  const counts = useMemo(() => {
    const out: Record<string, number> = {};
    (data?.partners || []).forEach(p => { out[p.type] = (out[p.type] || 0) + 1; });
    return out;
  }, [data]);

  const progress = data?.progress;
  const why = data?.types.find(t => t.value === type)?.why;

  return (
    <div className="flex-1 overflow-y-auto p-4 sm:p-6 space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="max-w-3xl">
          <h1 className="text-xl font-semibold text-slate-100">Partner Organisations</h1>
          <p className="text-sm text-slate-400 mt-1">
            Organisations near our SBI branches that help people find work or start a business. Approach them to
            refer the people they serve; those people then write to us themselves. Individuals are not collected:
            their details on government portals are not for outreach, and WhatsApp needs a person's own opt-in.
          </p>
        </div>
        <button onClick={() => data && downloadCsv(data.partners)} disabled={!data?.partners.length}
          className="inline-flex items-center gap-1.5 h-9 px-3 rounded bg-slate-800 border border-slate-700 text-sm text-slate-200 hover:bg-slate-700 disabled:opacity-40 cursor-pointer">
          <span className="material-symbols-outlined text-[18px]">download</span>CSV
        </button>
      </div>

      {progress && progress.total > 0 && (
        <div className="text-xs text-slate-400 bg-slate-900 border border-slate-800 rounded p-3">
          Searched at {data?.branches.length ?? 0} SBI branch PIN codes: {progress.done} of {progress.total} searches done
          {progress.pending > 0 && <>, {progress.pending} waiting (the scraper works through them)</>}
          {progress.failed > 0 && <>, {progress.failed} failed and will be tried again</>}.
        </div>
      )}

      <div className="flex flex-wrap items-end gap-3">
        <label className="text-xs text-slate-400 flex flex-col gap-1">Type
          <select value={type} onChange={e => setType(e.target.value)} className={selectCls}>
            <option value="">All types</option>
            {(data?.types || []).map(t => <option key={t.value} value={t.value}>{t.value}</option>)}
          </select>
        </label>
        <label className="text-xs text-slate-400 flex flex-col gap-1">SBI branch
          <select value={branch} onChange={e => setBranch(e.target.value)} className={selectCls}>
            <option value="">All branches</option>
            {(data?.branches || []).map(b => <option key={b.code} value={b.code}>{b.name} ({b.code}) · {b.pincode}</option>)}
          </select>
        </label>
        <label className="text-xs text-slate-400 flex flex-col gap-1 flex-1 min-w-[200px]">Search
          <input value={q} onChange={e => setQ(e.target.value)} placeholder="Name or address" className={selectCls} />
        </label>
      </div>
      {why && <p className="text-xs text-slate-500 -mt-2">{why}.</p>}

      {!type && Object.keys(counts).length > 0 && (
        <div className="flex flex-wrap gap-2">
          {Object.entries(counts).sort((a, b) => b[1] - a[1]).map(([t, n]) => (
            <button key={t} onClick={() => setType(t)}
              className="text-xs px-2.5 py-1 rounded-full border border-slate-700 text-slate-300 hover:bg-slate-800 cursor-pointer">
              {t} <span className="text-slate-500">{n}</span>
            </button>
          ))}
        </div>
      )}

      {error && <div className="text-sm text-rose-400">{error}</div>}
      {loading && !data && <div className="text-sm text-slate-500">Loading…</div>}
      {data && data.partners.length === 0 && !loading && (
        <div className="text-sm text-slate-500 bg-slate-900 border border-slate-800 rounded p-6 text-center">
          {progress && progress.done === 0
            ? 'Nothing found yet: the searches near SBI branches have not run. They are in the scraping queue.'
            : 'No organisations match these filters.'}
        </div>
      )}

      {data && data.partners.length > 0 && (
        <div className="overflow-x-auto border border-slate-800 rounded-lg">
          <table className="w-full text-sm">
            <thead className="bg-slate-900 text-left text-xs text-slate-400">
              <tr>
                <th className="px-3 py-2 font-semibold">Name</th>
                <th className="px-3 py-2 font-semibold">Type</th>
                <th className="px-3 py-2 font-semibold">Contact</th>
                <th className="px-3 py-2 font-semibold">Address</th>
                <th className="px-3 py-2 font-semibold">SBI branch</th>
              </tr>
            </thead>
            <tbody>
              {data.partners.map(p => (
                <tr key={p.business_id} className="border-t border-slate-800 align-top">
                  <td className="px-3 py-2 text-slate-100">
                    {p.name}
                    {p.google_maps_url && (
                      <a href={p.google_maps_url} target="_blank" rel="noreferrer" title="Open in Google Maps"
                        className="ml-1 text-sky-400 hover:text-sky-300 align-middle">
                        <span className="material-symbols-outlined text-[16px]">map</span>
                      </a>
                    )}
                  </td>
                  <td className="px-3 py-2 text-slate-300 whitespace-nowrap">{p.type}</td>
                  <td className="px-3 py-2 text-slate-300 select-text">
                    {p.phone && <div className="font-mono-code whitespace-nowrap">{p.phone}</div>}
                    {p.email && <div className="text-xs break-all">{p.email}</div>}
                    {p.website && <a href={p.website} target="_blank" rel="noreferrer" className="text-xs text-sky-400 break-all">{p.website}</a>}
                  </td>
                  <td className="px-3 py-2 text-xs text-slate-400 max-w-sm">{p.address}</td>
                  <td className="px-3 py-2 text-xs text-slate-300 whitespace-nowrap">
                    {p.branches.map(b => <div key={b.code}>{b.name} ({b.code})</div>)}
                    <div className="text-slate-500">PIN {p.pincode}</div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
};
