import React, { useState, useEffect } from 'react';
import type { BusinessItem, ApiError } from '../types/api';
import { fetchBusinesses, fetchDcSummary, triggerCsvStream, triggerExcelStream, type DcSummary } from '../api';

/**
 * DC Data (Biswajit Sir, 23 Nov 2026): the businesses we scraped for District
 * Coordinators and nothing else. The figures on top, then the leads themselves,
 * which a click on a state or district narrows down. Only reads.
 */

const PAGE_SIZE = 50;
const n = (v: number) => v.toLocaleString('en-IN');
const pct = (part: number, whole: number) => (whole ? Math.round((part / whole) * 100) : 0);
const when = (iso: string | null) =>
  iso ? new Date(iso).toLocaleString('en-IN', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' }) : '—';

const Tile: React.FC<{ label: string; value: string; note?: string; icon: string }> = ({ label, value, note, icon }) => (
  <div className="bg-slate-900 border border-slate-800 rounded-lg p-4 flex flex-col gap-1">
    <div className="flex items-center gap-1.5 text-[10px] uppercase tracking-wider text-slate-400 font-semibold">
      <span className="material-symbols-outlined text-[15px] text-purple-400">{icon}</span>
      {label}
    </div>
    <div className="text-2xl font-semibold text-slate-100 tabular-nums">{value}</div>
    {note && <div className="text-[11px] text-slate-500">{note}</div>}
  </div>
);

const Panel: React.FC<{ title: string; children: React.ReactNode; className?: string }> = ({ title, children, className = '' }) => (
  <section className={`bg-slate-900 border border-slate-800 rounded-lg p-4 flex flex-col gap-3 min-w-0 ${className}`}>
    <h2 className="text-xs uppercase tracking-wider text-slate-400 font-semibold">{title}</h2>
    {children}
  </section>
);

export const DcDataView: React.FC = () => {
  const [summary, setSummary] = useState<DcSummary | null>(null);
  const [summaryError, setSummaryError] = useState<ApiError | null>(null);

  const [rows, setRows] = useState<BusinessItem[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<ApiError | null>(null);

  const [search, setSearch] = useState('');
  const [state, setState] = useState('');
  const [district, setDistrict] = useState('');
  const [openState, setOpenState] = useState<string | null>(null);

  const loadSummary = () => {
    setSummaryError(null);
    fetchDcSummary(30).then(setSummary).catch(setSummaryError);
  };
  useEffect(loadSummary, []);

  // Only the latest load may fill the table, so a slow answer cannot overwrite a newer one.
  const latest = React.useRef(0);
  const loadRows = async (targetPage = 1) => {
    const ticket = ++latest.current;
    setLoading(true);
    setError(null);
    try {
      const res = await fetchBusinesses({
        page: targetPage, page_size: PAGE_SIZE, hiring_for: 'DC',
        search: search.trim() || undefined, state: state || undefined, district: district || undefined,
      });
      if (ticket !== latest.current) return;
      setRows(res.items);
      setTotal(res.total);
      setPage(res.page);
      setTotalPages(Math.max(1, res.total_pages || Math.ceil(res.total / PAGE_SIZE)));
    } catch (err: any) {
      if (ticket === latest.current) setError(err);
    } finally {
      if (ticket === latest.current) setLoading(false);
    }
  };
  useEffect(() => {
    const t = setTimeout(() => loadRows(1), 300);
    return () => clearTimeout(t);
  }, [search, state, district]);

  const refresh = () => { loadSummary(); loadRows(page); };
  const pick = (st: string, d = '') => { setState(st); setDistrict(d); };
  const exportFilters = { hiring_for: 'DC' as const, state: state || undefined, search: search.trim() || undefined };

  const s = summary;
  const peak = s ? Math.max(1, ...s.daily.map(d => d.count)) : 1;
  const topCategory = s ? Math.max(1, ...s.categories.map(c => c.count)) : 1;
  const districts = s ? s.states.reduce((sum, st) => sum + st.districts.length, 0) : 0;

  return (
    <div className="flex-1 flex flex-col min-w-0 h-full overflow-y-auto bg-slate-950 text-slate-100">
      <div className="px-6 py-4 border-b border-slate-800 bg-slate-900 flex flex-col md:flex-row md:items-center justify-between gap-3 shrink-0">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">District Coordinator Data</h1>
          <p className="text-xs text-slate-400 mt-0.5">
            Businesses found on Google Maps for District Coordinator hiring · last found {when(s?.last_found_at ?? null)}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button onClick={refresh}
            className="h-8 px-3 bg-slate-800 hover:bg-slate-700 border border-slate-700 text-slate-200 text-xs rounded flex items-center gap-1.5 cursor-pointer">
            <span className={`material-symbols-outlined text-[16px] text-slate-400 ${loading ? 'animate-spin' : ''}`}>refresh</span>
            Refresh
          </button>
          <button onClick={() => triggerExcelStream(exportFilters)}
            className="h-8 px-3 bg-purple-600 hover:bg-purple-500 text-white text-xs font-semibold rounded flex items-center gap-1.5 cursor-pointer">
            <span className="material-symbols-outlined text-[16px]">download</span>
            Excel
          </button>
          <button onClick={() => triggerCsvStream(exportFilters)}
            className="h-8 px-3 bg-slate-800 hover:bg-slate-700 border border-slate-700 text-slate-200 text-xs rounded cursor-pointer">
            CSV
          </button>
        </div>
      </div>

      <div className="p-4 md:p-6 flex flex-col gap-4">
        {summaryError && (
          <div className="p-3 bg-rose-950/70 border border-rose-800 rounded text-rose-200 text-xs">
            Could not load the DC figures: {summaryError.message}
          </div>
        )}

        <div className="grid grid-cols-2 lg:grid-cols-5 gap-3">
          <Tile icon="hub" label="DC leads" value={s ? n(s.total) : '…'} note="found so far" />
          <Tile icon="today" label="Today" value={s ? n(s.today) : '…'} note={s ? `${n(s.last_7_days)} in the last 7 days` : undefined} />
          <Tile icon="map" label="Coverage" value={s ? `${s.states.length} states` : '…'} note={s ? `${districts} districts` : undefined} />
          <Tile icon="call" label="With phone" value={s ? `${pct(s.with_phone, s.total)}%` : '…'} note={s ? `${n(s.with_phone)} leads` : undefined} />
          <Tile icon="mail" label="With email / website" value={s ? `${n(s.with_email)} / ${n(s.with_website)}` : '…'}
                note={s ? `${pct(s.with_email, s.total)}% / ${pct(s.with_website, s.total)}%` : undefined} />
        </div>

        <Panel title="Found per day · last 30 days">
          <div className="flex items-end gap-[3px] h-28">
            {(s?.daily || []).map(d => (
              <div key={d.date} className="flex-1 h-full flex flex-col justify-end group relative"
                   title={`${new Date(d.date).toLocaleDateString('en-IN', { day: '2-digit', month: 'short' })}: ${d.count}`}>
                <div className={`rounded-t ${d.count ? 'bg-purple-500 group-hover:bg-purple-400' : 'bg-slate-800'}`}
                     style={{ height: `${d.count ? Math.max(4, (d.count / peak) * 100) : 2}%` }} />
              </div>
            ))}
          </div>
          {s && (
            <div className="flex justify-between text-[10px] text-slate-500">
              <span>{new Date(s.daily[0]?.date).toLocaleDateString('en-IN', { day: '2-digit', month: 'short' })}</span>
              <span>peak {peak} a day</span>
              <span>today</span>
            </div>
          )}
        </Panel>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
          <Panel title="By state and district · click to filter the list" className="lg:col-span-2">
            <div className="flex flex-col divide-y divide-slate-800 text-sm">
              {(s?.states || []).map(st => (
                <div key={st.state}>
                  <div className={`flex items-center gap-2 py-2 cursor-pointer hover:bg-slate-800/50 px-1 rounded ${state === st.state && !district ? 'text-purple-300' : ''}`}>
                    <button onClick={() => setOpenState(openState === st.state ? null : st.state)} className="text-slate-500 cursor-pointer">
                      <span className="material-symbols-outlined text-[18px]">{openState === st.state ? 'expand_more' : 'chevron_right'}</span>
                    </button>
                    <span className="flex-1 truncate" onClick={() => pick(st.state)}>{st.state}</span>
                    <span className="text-[11px] text-slate-500">{st.districts.length} districts</span>
                    <span className="w-14 text-right tabular-nums font-semibold" onClick={() => pick(st.state)}>{n(st.count)}</span>
                  </div>
                  {openState === st.state && (
                    <div className="pl-8 pb-2 grid grid-cols-1 sm:grid-cols-2 gap-x-6">
                      {st.districts.map(d => (
                        <button key={d.district} onClick={() => pick(st.state, d.district)}
                          className={`flex justify-between py-1 text-xs hover:text-purple-300 cursor-pointer ${district === d.district && state === st.state ? 'text-purple-300' : 'text-slate-300'}`}>
                          <span className="truncate">{d.district}</span>
                          <span className="tabular-nums text-slate-400">{n(d.count)}</span>
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              ))}
              {s && !s.states.length && <p className="text-xs text-slate-500 py-2">No DC leads yet.</p>}
            </div>
          </Panel>

          <Panel title="Kinds of business">
            <div className="flex flex-col gap-2">
              {(s?.categories || []).map(c => (
                <div key={c.category} className="flex flex-col gap-1">
                  <div className="flex justify-between text-xs">
                    <span className="truncate text-slate-300">{c.category}</span>
                    <span className="tabular-nums text-slate-400">{n(c.count)}</span>
                  </div>
                  <div className="h-1.5 bg-slate-800 rounded">
                    <div className="h-full bg-purple-500 rounded" style={{ width: `${(c.count / topCategory) * 100}%` }} />
                  </div>
                </div>
              ))}
            </div>
          </Panel>
        </div>

        <Panel title="DC leads">
          <div className="flex flex-col md:flex-row md:items-center gap-2">
            <div className="relative flex-1 max-w-xl">
              <span className="absolute left-2.5 top-1/2 -translate-y-1/2 text-slate-500 text-[16px] material-symbols-outlined">search</span>
              <input value={search} onChange={e => setSearch(e.target.value)} placeholder="Search name, category, district or phone"
                className="w-full bg-slate-950 border border-slate-700 focus:border-purple-500 rounded pl-8 pr-3 h-8 text-xs text-slate-100 placeholder:text-slate-500 outline-none" />
            </div>
            {(state || district) && (
              <button onClick={() => pick('')}
                className="h-8 px-3 rounded-full bg-purple-600 text-white text-xs font-semibold flex items-center gap-1.5 self-start cursor-pointer">
                {district ? `${district}, ${state}` : state}
                <span className="material-symbols-outlined text-[15px]">close</span>
              </button>
            )}
            <span className="text-xs text-slate-400 md:ml-auto">{n(total)} leads</span>
          </div>

          {error && <p className="text-xs text-rose-300">Could not load the leads: {error.message}</p>}

          <div className="overflow-x-auto border border-slate-800 rounded">
            <table className="w-full text-left text-xs select-text">
              <thead className="bg-slate-900 text-[10px] uppercase tracking-wider text-slate-400">
                <tr className="h-9">
                  <th className="px-3 min-w-[200px]">Name</th>
                  <th className="px-3 min-w-[120px]">Phone</th>
                  <th className="px-3 min-w-[160px]">Category</th>
                  <th className="px-3 min-w-[120px]">District</th>
                  <th className="px-3 min-w-[110px]">State</th>
                  <th className="px-3 min-w-[160px]">Email / website</th>
                  <th className="px-3 min-w-[90px]">PIN code</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800">
                {loading ? (
                  <tr><td colSpan={7} className="py-10 text-center text-slate-400">Loading…</td></tr>
                ) : !rows.length ? (
                  <tr><td colSpan={7} className="py-10 text-center text-slate-400">No DC leads match.</td></tr>
                ) : rows.map((b, i) => (
                  <tr key={`${b.phone}-${i}`} className="h-9 hover:bg-slate-900/60">
                    <td className="px-3 font-medium text-slate-100" title={b.address || ''}>{b.name}</td>
                    <td className="px-3 text-slate-200 tabular-nums">{b.phone || '—'}</td>
                    <td className="px-3 text-slate-300">{b.category || '—'}</td>
                    <td className="px-3 text-slate-300">{b.district || '—'}</td>
                    <td className="px-3 text-slate-300">{b.state || '—'}</td>
                    <td className="px-3 text-sky-400 truncate max-w-[200px]">
                      {b.email ? <a href={`mailto:${b.email}`} className="hover:underline">{b.email}</a>
                        : b.website ? <a href={b.website.startsWith('http') ? b.website : `https://${b.website}`} target="_blank" rel="noreferrer" className="hover:underline">{b.website.replace(/^https?:\/\//, '')}</a>
                        : <span className="text-slate-500">—</span>}
                    </td>
                    <td className="px-3 text-slate-400 tabular-nums">{b.pincode || '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="flex items-center justify-end gap-2 text-xs">
            <button onClick={() => loadRows(page - 1)} disabled={page <= 1 || loading}
              className="h-7 px-2.5 bg-slate-800 border border-slate-700 rounded disabled:opacity-40 cursor-pointer">Prev</button>
            <span className="text-slate-300">Page {page} of {totalPages}</span>
            <button onClick={() => loadRows(page + 1)} disabled={page >= totalPages || loading}
              className="h-7 px-2.5 bg-slate-800 border border-slate-700 rounded disabled:opacity-40 cursor-pointer">Next</button>
          </div>
        </Panel>
      </div>
    </div>
  );
};
