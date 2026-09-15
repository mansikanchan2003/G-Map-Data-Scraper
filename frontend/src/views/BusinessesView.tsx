import React, { useState, useEffect } from 'react';
import type { BusinessItem, PaginatedResponse, ApiError } from '../types/api';
import { fetchBusinesses, triggerCsvStream, triggerExcelStream, exportToGoogleSheets } from '../api';

interface BusinessesViewProps {
  initialSearch?: string;
}

export const BusinessesView: React.FC<BusinessesViewProps> = ({
  initialSearch = '',
}) => {
  const [businesses, setBusinesses] = useState<BusinessItem[]>([]);
  const [total, setTotal] = useState<number>(0);
  const [page, setPage] = useState<number>(1);
  const [pageSize] = useState<number>(100);
  const [totalPages, setTotalPages] = useState<number>(1);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<ApiError | null>(null);
  const [googleSheetsLoading, setGoogleSheetsLoading] = useState<boolean>(false);
  const [googleSheetsSuccess, setGoogleSheetsSuccess] = useState<string | null>(null);

  // Filters
  const [search, setSearch] = useState<string>(initialSearch);
  const [selectedState, setSelectedState] = useState<string>('All');
  const [jumpPage, setJumpPage] = useState<string>('');

  const loadData = async (targetPage = page, searchTerm = search, st = selectedState) => {
    setLoading(true);
    setError(null);
    try {
      const res: PaginatedResponse<BusinessItem> = await fetchBusinesses({
        page: targetPage,
        page_size: pageSize,
        search: searchTerm,
        state: st !== 'All' ? st : undefined,
      });
      setBusinesses(res.items);
      setTotal(res.total);
      setPage(res.page);
      setTotalPages(res.total_pages || Math.max(1, Math.ceil(res.total / pageSize)));
    } catch (err: any) {
      setError(err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData(1, search, selectedState);
  }, [search, selectedState]);

  const handlePageChange = (newPage: number) => {
    if (newPage >= 1 && newPage <= totalPages && newPage !== page) {
      setPage(newPage);
      loadData(newPage, search, selectedState);
    }
  };

  const handleJump = () => {
    const num = parseInt(jumpPage, 10);
    if (!isNaN(num) && num >= 1 && num <= totalPages) {
      handlePageChange(num);
      setJumpPage('');
    }
  };

  const handleGoogleSheetsExport = async () => {
    setGoogleSheetsLoading(true);
    setGoogleSheetsSuccess(null);
    setError(null);
    try {
      const filters = { search, state: selectedState !== 'All' ? selectedState : undefined };
      const res = await exportToGoogleSheets(filters, [], true); // exportAll = true for current filters
      setGoogleSheetsSuccess(res.spreadsheet_url);
    } catch (err: any) {
      setError(err);
    } finally {
      setGoogleSheetsLoading(false);
    }
  };

  const startRecord = total > 0 ? (page - 1) * pageSize + 1 : 0;
  const endRecord = total > 0 ? Math.min(page * pageSize, total) : 0;

  return (
    <div className="flex-1 flex flex-col min-w-0 h-full bg-slate-950 text-slate-100 select-none">
      {/* Content Header & Filter Bar */}
      <div className="px-6 py-4 border-b border-slate-800 bg-slate-900 flex flex-col gap-3 shrink-0">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div>
            <div className="flex items-center gap-3">
              <h1 className="text-2xl font-semibold text-white tracking-tight">Business Data</h1>
              <span className="px-2 py-0.5 bg-sky-950/80 border border-sky-800 text-sky-400 font-mono-code text-xs rounded flex items-center gap-1.5 font-medium">
                <span className="h-1.5 w-1.5 rounded-full bg-sky-400 animate-ping" />
                {total.toLocaleString()} records discovered
              </span>
            </div>
            <p className="text-xs text-slate-400 mt-0.5">
              Discovered, deduplicated, and geographically validated Google Maps business records
            </p>
          </div>

          {/* Action Bar */}
          <div className="flex items-center gap-2">
            <button
              onClick={() => loadData(page)}
              disabled={loading}
              className="h-8 px-3 bg-slate-800 hover:bg-slate-700 border border-slate-700 text-slate-200 text-xs font-mono-code rounded flex items-center gap-1.5 transition-all shadow-sm cursor-pointer active:scale-95 disabled:opacity-50"
            >
              <span className={`material-symbols-outlined text-[16px] text-slate-400 ${loading ? 'animate-spin' : ''}`}>
                refresh
              </span>
              <span>Refresh</span>
            </button>

            {/* Primary Action: Download CSV */}
            <div className="relative group">
              <button
                onClick={() => triggerCsvStream()}
                className="h-8 px-3.5 bg-slate-700 hover:bg-slate-600 border border-slate-600 text-white font-mono-code text-xs font-semibold rounded flex items-center gap-2 transition-all shadow-sm cursor-pointer active:scale-95"
                title="Download CSV"
              >
                <span className="material-symbols-outlined text-[17px] text-white">description</span>
                <span>CSV</span>
              </button>
            </div>

            {/* Primary Action: Download Excel */}
            <div className="relative group">
              <button
                onClick={() => triggerExcelStream()}
                className="h-8 px-3.5 bg-emerald-600 hover:bg-emerald-500 text-white font-mono-code text-xs font-semibold rounded flex items-center gap-2 transition-all shadow-sm cursor-pointer active:scale-95"
                title="Download full business dataset as Excel (XLSX)"
              >
                <span className="material-symbols-outlined text-[17px] text-white">table</span>
                <span>Download Excel</span>
              </button>

              <div className="absolute right-0 top-full mt-1.5 hidden group-hover:flex flex-col z-50 w-72 p-2.5 bg-slate-900 border border-slate-700 text-slate-200 rounded shadow-xl pointer-events-none text-left">
                <span className="text-[10px] font-mono-code text-emerald-400 uppercase font-bold">STREAM ENDPOINT</span>
                <span className="text-xs font-mono-code text-slate-100 mt-0.5 break-all font-semibold">
                  GET /api/v1/export/businesses?format=excel
                </span>
                <span className="text-xs text-slate-400 mt-1">
                  Streams full dataset directly from FastAPI backend in native Excel format with optimized columns.
                </span>
              </div>
            </div>

            {/* Primary Action: Export to Google Sheets */}
            <button
              onClick={handleGoogleSheetsExport}
              disabled={googleSheetsLoading || loading}
              className="h-8 px-3.5 bg-sky-700 hover:bg-sky-600 disabled:bg-slate-700 disabled:opacity-70 border border-sky-600 disabled:border-slate-600 text-white font-mono-code text-xs font-semibold rounded flex items-center gap-2 transition-all shadow-sm cursor-pointer active:scale-95"
              title="Export all matching records to a new Google Sheet"
            >
              {googleSheetsLoading ? (
                <span className="w-3.5 h-3.5 border-2 border-white/30 border-t-white rounded-full animate-spin" />
              ) : (
                <span className="material-symbols-outlined text-[17px] text-white">post_add</span>
              )}
              <span>{googleSheetsLoading ? 'Exporting...' : 'Google Sheets'}</span>
            </button>
          </div>
        </div>

        {/* Filter and Search Bar */}
        <div className="flex flex-col lg:flex-row items-stretch lg:items-center justify-between gap-3 pt-1">
          <div className="flex items-center gap-2 flex-1 max-w-2xl">
            <div className="relative flex-1">
              <span className="absolute left-2.5 top-1/2 -translate-y-1/2 text-slate-500 text-[16px] material-symbols-outlined">
                search
              </span>
              <input
                type="text"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Search by business name or address..."
                className="w-full bg-slate-950 border border-slate-700 focus:border-sky-500 focus:ring-1 focus:ring-sky-500 rounded pl-8 pr-3 h-8 text-xs font-mono-code text-slate-100 placeholder:text-slate-500 outline-none transition-all"
              />
            </div>

            <select
              value={selectedState}
              onChange={(e) => setSelectedState(e.target.value)}
              className="h-8 px-2 bg-slate-950 border border-slate-700 text-slate-200 text-xs font-mono-code rounded shadow-sm focus:outline-none focus:border-sky-500 cursor-pointer"
            >
              <option value="All">State: All</option>
              <option value="DELHI">Delhi</option>
              <option value="UTTAR PRADESH">Uttar Pradesh</option>
              <option value="HARYANA">Haryana</option>
              <option value="MAHARASHTRA">Maharashtra</option>
              <option value="KARNATAKA">Karnataka</option>
              <option value="TAMIL NADU">Tamil Nadu</option>
            </select>
          </div>

          <div className="flex items-center gap-2 self-end lg:self-auto px-2.5 py-1 bg-slate-950 border border-slate-800 rounded text-xs font-mono-code text-slate-400">
            <span className="h-2 w-2 rounded-full bg-emerald-400" />
            <span>
              Server-side page size: <strong className="text-slate-200 font-semibold">{pageSize} / page</strong>
            </span>
          </div>
        </div>
      </div>

      {/* Error State Banner */}
      {error && (
        <div className="m-4 p-4 bg-rose-950/70 border border-rose-800 rounded text-rose-200 space-y-2">
          <div className="flex items-center gap-2 font-semibold text-sm">
            <span className="material-symbols-outlined text-rose-400">error</span>
            <span>Unable to load business records</span>
          </div>
          <p className="text-xs font-mono-code text-rose-300">
            {error.isNetworkError
              ? `Backend connection error at ${error.endpoint || '/api/v1/businesses'}. Ensure FastAPI is running.`
              : error.message}
          </p>
          <button
            onClick={() => loadData(page)}
            className="px-3 py-1 bg-slate-900 border border-rose-700 hover:bg-slate-800 text-rose-300 text-xs font-mono-code rounded font-semibold cursor-pointer"
          >
            Retry
          </button>
        </div>
      )}

      {/* Google Sheets Success Banner */}
      {googleSheetsSuccess && (
        <div className="m-4 p-4 bg-emerald-950/70 border border-emerald-800 rounded text-emerald-200 space-y-2 flex justify-between items-center">
          <div className="flex items-center gap-2 font-semibold text-sm">
            <span className="material-symbols-outlined text-emerald-400">check_circle</span>
            <span>Google Sheet created successfully</span>
          </div>
          <a
            href={googleSheetsSuccess}
            target="_blank"
            rel="noreferrer"
            className="px-3 py-1.5 bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-mono-code rounded font-semibold flex items-center gap-1 transition-colors"
          >
            <span>Open Google Sheet</span>
            <span className="material-symbols-outlined text-[14px]">open_in_new</span>
          </a>
        </div>
      )}

      {/* DENSE DATA TABLE */}
      <div className="flex-1 overflow-auto relative bg-slate-950 border-b border-slate-800">
        <table className="w-full text-left border-collapse select-text">
          <thead className="sticky top-0 z-20 bg-slate-900 border-b-2 border-slate-800">
            <tr className="h-9">
              <th className="px-3 text-[10px] font-mono-code uppercase tracking-wider text-slate-400 font-bold border-r border-slate-800 min-w-[200px]">
                Name
              </th>
              <th className="px-3 text-[10px] font-mono-code uppercase tracking-wider text-slate-400 font-bold border-r border-slate-800 min-w-[260px]">
                Address
              </th>
              <th className="px-3 text-[10px] font-mono-code uppercase tracking-wider text-slate-400 font-bold border-r border-slate-800 min-w-[130px]">
                Phone
              </th>
              <th className="px-3 text-[10px] font-mono-code uppercase tracking-wider text-slate-400 font-bold border-r border-slate-800 min-w-[160px]">
                Email
              </th>
              <th className="px-3 text-[10px] font-mono-code uppercase tracking-wider text-slate-400 font-bold border-r border-slate-800 min-w-[140px]">
                Website
              </th>
              <th className="px-3 text-[10px] font-mono-code uppercase tracking-wider text-slate-400 font-bold border-r border-slate-800 min-w-[160px]">
                Category
              </th>
              <th className="px-3 text-[10px] font-mono-code uppercase tracking-wider text-slate-400 font-bold border-r border-slate-800 min-w-[120px]">
                District
              </th>
              <th className="px-3 text-[10px] font-mono-code uppercase tracking-wider text-slate-400 font-bold min-w-[110px]">
                State
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-800 text-xs font-mono-code">
            {loading ? (
              <tr>
                <td colSpan={9} className="py-16 text-center text-slate-400 bg-slate-950">
                  <div className="flex flex-col items-center justify-center gap-2">
                    <span className="w-6 h-6 border-2 border-sky-400 border-t-transparent rounded-full animate-spin" />
                    <span>Loading businesses (page {page} of {totalPages})...</span>
                  </div>
                </td>
              </tr>
            ) : businesses.length === 0 ? (
              <tr>
                <td colSpan={9} className="py-16 text-center text-slate-400 bg-slate-950">
                  <div className="flex flex-col items-center justify-center gap-2">
                    <span className="material-symbols-outlined text-[32px] text-slate-600">inventory_2</span>
                    <span className="font-semibold text-slate-300">No businesses discovered yet.</span>
                    <span className="text-xs text-slate-500">
                      Run discovery batches from the Dashboard or Jobs Monitor to populate records.
                    </span>
                  </div>
                </td>
              </tr>
            ) : (
              businesses.map((biz) => (
                <tr key={biz.business_id} className="h-9 hover:bg-slate-900/60 transition-colors bg-slate-950/40">
                  <td className="px-3 border-r border-slate-800 font-medium text-slate-100 font-sans">
                    <div className="flex items-center gap-1.5">
                      <span className="truncate max-w-[220px]" title={biz.name}>
                        {biz.name}
                      </span>
                      {biz.verified && (
                        <span
                          className="material-symbols-outlined text-[15px] text-emerald-400 shrink-0"
                          title="Verified valid business"
                        >
                          verified
                        </span>
                      )}
                    </div>
                  </td>
                  <td className="px-3 border-r border-slate-800 text-slate-400 truncate max-w-[260px]" title={biz.address || '—'}>
                    {biz.address || '—'}
                  </td>
                  <td className="px-3 border-r border-slate-800 text-slate-200">
                    {biz.phone || '—'}
                  </td>
                  <td className="px-3 border-r border-slate-800 text-sky-400 truncate max-w-[160px]">
                    {biz.email ? (
                      <a href={`mailto:${biz.email}`} className="hover:underline">{biz.email}</a>
                    ) : '—'}
                  </td>
                  <td className="px-3 border-r border-slate-800">
                    {biz.website ? (
                      <a
                        href={biz.website.startsWith('http') ? biz.website : `https://${biz.website}`}
                        target="_blank"
                        rel="noreferrer"
                        className="inline-flex items-center gap-1 text-sky-400 hover:text-sky-300 truncate max-w-[130px]"
                      >
                        <span className="truncate">{biz.website.replace(/^https?:\/\//, '')}</span>
                        <span className="material-symbols-outlined text-[12px]">open_in_new</span>
                      </a>
                    ) : (
                      <span className="text-slate-600">—</span>
                    )}
                  </td>
                  <td className="px-3 border-r border-slate-800">
                    <span className="inline-block px-1.5 py-0.5 rounded text-[10px] uppercase bg-slate-800 text-slate-300 border border-slate-700 truncate max-w-[150px]">
                      {biz.category || 'General'}
                    </span>
                  </td>
                  <td className="px-3 border-r border-slate-800 text-slate-300 font-sans truncate max-w-[120px]">
                    {biz.district || '—'}
                  </td>
                  <td className="px-3 text-slate-300 font-sans truncate max-w-[110px]">
                    {biz.state || '—'}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {/* SERVER-SIDE PAGINATION FOOTER */}
      <footer className="h-12 bg-slate-900 border-t border-slate-800 px-4 flex flex-col sm:flex-row items-center justify-between gap-2 select-none shadow-sm shrink-0">
        <div className="flex items-center gap-4 text-xs font-mono-code text-slate-400">
          <div>
            Showing <span className="text-slate-100 font-bold">{startRecord} - {endRecord}</span> of{' '}
            <span className="text-slate-100 font-bold">{total.toLocaleString()}</span> records
          </div>
          <div className="hidden md:flex items-center gap-1 text-slate-500">
            <span>•</span>
            <span>Server-side pagination (100 / page)</span>
          </div>
        </div>

        <div className="flex items-center gap-2 font-mono-code text-xs">
          <button
            onClick={() => handlePageChange(page - 1)}
            disabled={page <= 1 || loading}
            className="h-7 px-2.5 bg-slate-800 hover:bg-slate-700 text-slate-300 border border-slate-700 rounded flex items-center gap-1 transition-colors cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed"
          >
            <span className="material-symbols-outlined text-[14px]">chevron_left</span>
            <span>Prev</span>
          </button>

          <span className="text-slate-200 font-semibold px-1">
            Page {page} of {totalPages}
          </span>

          <button
            onClick={() => handlePageChange(page + 1)}
            disabled={page >= totalPages || loading}
            className="h-7 px-2.5 bg-slate-800 hover:bg-slate-700 text-slate-300 border border-slate-700 rounded flex items-center gap-1 transition-colors cursor-pointer shadow-sm disabled:opacity-40 disabled:cursor-not-allowed"
          >
            <span>Next</span>
            <span className="material-symbols-outlined text-[14px]">chevron_right</span>
          </button>

          {/* Jump to page input */}
          <div className="hidden sm:flex items-center gap-1.5 ml-2 pl-2 border-l border-slate-800 text-slate-400">
            <span className="text-[10px] uppercase font-semibold">Go to:</span>
            <input
              type="text"
              value={jumpPage}
              onChange={(e) => setJumpPage(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && handleJump()}
              placeholder={String(page)}
              className="h-7 w-12 bg-slate-950 border border-slate-700 text-center text-xs text-slate-200 rounded focus:border-sky-500 focus:outline-none"
            />
            <button
              onClick={handleJump}
              className="h-7 px-2 bg-slate-800 hover:bg-slate-700 border border-slate-700 text-slate-300 text-[10px] rounded uppercase font-semibold cursor-pointer"
            >
              Jump
            </button>
          </div>
        </div>
      </footer>
    </div>
  );
};
