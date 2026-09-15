import React, { useState, useEffect } from 'react';
import type { LocationItem, CategoryItem, PaginatedResponse, ApiError } from '../types/api';
import { fetchConfigLocations, fetchConfigCategories, syncConfiguration, generateJobQueue } from '../api';

export const ConfigView: React.FC = () => {
  const [locations, setLocations] = useState<LocationItem[]>([]);
  const [totalLocations, setTotalLocations] = useState<number>(0);
  const [locPage, setLocPage] = useState<number>(1);
  const [locPages, setLocPages] = useState<number>(1);
  const [locLoading, setLocLoading] = useState<boolean>(true);

  const [categories, setCategories] = useState<CategoryItem[]>([]);
  const [totalCategories, setTotalCategories] = useState<number>(0);
  const [catPage, setCatPage] = useState<number>(1);
  const [catPages, setCatPages] = useState<number>(1);
  const [catLoading, setCatLoading] = useState<boolean>(true);

  const [actionLoading, setActionLoading] = useState<string | null>(null);
  const [feedback, setFeedback] = useState<string | null>(null);
  const [error, setError] = useState<ApiError | null>(null);

  const loadLocations = async (targetPage = locPage) => {
    setLocLoading(true);
    try {
      const res: PaginatedResponse<LocationItem> = await fetchConfigLocations(targetPage, 100);
      setLocations(res.items);
      setTotalLocations(res.total);
      setLocPage(res.page);
      setLocPages(res.total_pages || Math.max(1, Math.ceil(res.total / 100)));
    } catch (err: any) {
      setError(err);
    } finally {
      setLocLoading(false);
    }
  };

  const loadCategories = async (targetPage = catPage) => {
    setCatLoading(true);
    try {
      const res: PaginatedResponse<CategoryItem> = await fetchConfigCategories(targetPage, 100);
      setCategories(res.items);
      setTotalCategories(res.total);
      setCatPage(res.page);
      setCatPages(res.total_pages || Math.max(1, Math.ceil(res.total / 100)));
    } catch (err: any) {
      setError(err);
    } finally {
      setCatLoading(false);
    }
  };

  useEffect(() => {
    loadLocations(1);
    loadCategories(1);
  }, []);

  const handleSync = async () => {
    setActionLoading('sync');
    setFeedback(null);
    try {
      const res = await syncConfiguration();
      setFeedback(`Config Synced: ${res.locations.total_in_excel} locations (${res.locations.new} new), ${res.categories.total_in_excel} categories (${res.categories.new} new).`);
      loadLocations(1);
      loadCategories(1);
    } catch (err: any) {
      setFeedback(`Sync failed: ${err.message}`);
    } finally {
      setActionLoading(null);
    }
  };

  const handleGenerateJobs = async () => {
    setActionLoading('generate');
    setFeedback(null);
    try {
      const res = await generateJobQueue();
      setFeedback(`Job Queue: ${res.jobs_created} new jobs generated. Total queue size: ${res.total_jobs}.`);
    } catch (err: any) {
      setFeedback(`Job generation failed: ${err.message}`);
    } finally {
      setActionLoading(null);
    }
  };

  const matrixSize = totalLocations * totalCategories;

  return (
    <div className="flex-1 flex flex-col min-w-0 h-full bg-slate-950 text-slate-100 select-none overflow-y-auto">
      {/* Content Header & Real Actions */}
      <div className="px-6 py-4 border-b border-slate-800 bg-slate-900 flex flex-col gap-4 shrink-0">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div>
            <div className="flex items-center gap-3">
              <h1 className="text-2xl font-semibold text-white tracking-tight">Configuration</h1>
              <span className="px-2 py-0.5 bg-sky-950/80 border border-sky-800 text-sky-400 font-mono-code text-xs rounded flex items-center gap-1.5 font-medium">
                <span className="h-1.5 w-1.5 rounded-full bg-sky-400" />
                Source Datasets
              </span>
            </div>
            <p className="text-xs text-slate-400 mt-0.5">
              Geographic target coordinates and business category personas ingested from host Excel files
            </p>
          </div>

          <div className="flex items-center gap-2">
            {/* Real Action: POST /api/v1/config/sync */}
            <button
              onClick={handleSync}
              disabled={actionLoading !== null}
              className="h-8 px-3 bg-slate-800 hover:bg-slate-700 border border-slate-700 text-slate-200 text-xs font-mono-code rounded flex items-center gap-1.5 transition-all shadow-sm cursor-pointer active:scale-95 disabled:opacity-50"
              title="Re-sync Excel files from host into database via POST /api/v1/config/sync"
            >
              <span className={`material-symbols-outlined text-[16px] text-sky-400 ${actionLoading === 'sync' ? 'animate-spin' : ''}`}>
                sync
              </span>
              <span>Sync Config Files</span>
            </button>

            {/* Real Action: POST /api/v1/jobs/generate */}
            <button
              onClick={handleGenerateJobs}
              disabled={actionLoading !== null}
              className="h-8 px-3.5 bg-sky-600 hover:bg-sky-500 text-white font-mono-code text-xs font-semibold rounded flex items-center gap-1.5 transition-all shadow-sm cursor-pointer active:scale-95 disabled:opacity-50"
              title="Generate missing Location × Category jobs via POST /api/v1/jobs/generate"
            >
              <span className={`material-symbols-outlined text-[16px] ${actionLoading === 'generate' ? 'animate-spin' : ''}`}>
                autorenew
              </span>
              <span>Generate Job Queue</span>
            </button>
          </div>
        </div>

        {feedback && (
          <div className="p-2.5 bg-sky-950/80 border border-sky-800 rounded text-xs font-mono-code text-sky-300 flex items-center justify-between">
            <span>{feedback}</span>
            <button onClick={() => setFeedback(null)} className="text-sky-400 hover:text-sky-200 font-bold cursor-pointer">
              ✕
            </button>
          </div>
        )}

        {/* 4 Metric Summary Cards */}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          <div className="p-3 bg-slate-950 border border-slate-800 rounded flex flex-col justify-between">
            <div className="flex items-center justify-between text-slate-400 text-[10px] font-mono-code uppercase font-semibold">
              <span>Configured Locations</span>
              <span className="material-symbols-outlined text-[16px] text-slate-500">pin_drop</span>
            </div>
            <div className="text-xl font-mono-code text-white font-bold mt-1">{totalLocations.toLocaleString()} PINs</div>
            <div className="text-[11px] font-mono-code text-slate-400 mt-0.5">Geocoded Ad Targeting Source</div>
          </div>

          <div className="p-3 bg-slate-950 border border-slate-800 rounded flex flex-col justify-between">
            <div className="flex items-center justify-between text-slate-400 text-[10px] font-mono-code uppercase font-semibold">
              <span>Target Categories</span>
              <span className="material-symbols-outlined text-[16px] text-slate-500">category</span>
            </div>
            <div className="text-xl font-mono-code text-white font-bold mt-1">{totalCategories.toLocaleString()} Personas</div>
            <div className="text-[11px] font-mono-code text-slate-400 mt-0.5">G-Map Categories Source</div>
          </div>

          <div className="p-3 bg-sky-950/40 border border-sky-800 rounded flex flex-col justify-between">
            <div className="flex items-center justify-between text-sky-400 text-[10px] font-mono-code uppercase font-semibold">
              <span>Total Matrix Size</span>
              <span className="material-symbols-outlined text-[16px]">hub</span>
            </div>
            <div className="text-xl font-mono-code text-sky-200 font-bold mt-1">{matrixSize.toLocaleString()} Pairs</div>
            <div className="text-[11px] font-mono-code text-sky-400 mt-0.5">Locations × Categories</div>
          </div>

          <div className="p-3 bg-emerald-950/40 border border-emerald-800 rounded flex flex-col justify-between">
            <div className="flex items-center justify-between text-emerald-400 text-[10px] font-mono-code uppercase font-semibold">
              <span>Host Excel Files</span>
              <span className="material-symbols-outlined text-[16px]">verified</span>
            </div>
            <div className="text-xl font-mono-code text-emerald-300 font-bold mt-1">Available</div>
            <div className="text-[11px] font-mono-code text-emerald-400 mt-0.5">Host files detected on disk</div>
          </div>
        </div>
      </div>

      {/* Error state */}
      {error && (
        <div className="m-4 p-4 bg-rose-950/70 border border-rose-800 rounded text-rose-200 space-y-1 text-xs font-mono-code">
          <div className="font-semibold text-sm flex items-center gap-1.5">
            <span className="material-symbols-outlined text-rose-400">error</span>
            <span>Configuration Error</span>
          </div>
          <p>{error.message}</p>
        </div>
      )}

      {/* SPLIT TWO-PANEL LAYOUT (DARK THEME) */}
      <div className="flex-1 grid grid-cols-1 lg:grid-cols-12 gap-4 p-4 lg:p-6 min-h-0">
        {/* PANEL A: GEOGRAPHIC LOCATIONS (7 COLS) */}
        <div className="lg:col-span-7 bg-slate-900 border border-slate-800 rounded flex flex-col shadow-sm overflow-hidden">
          <div className="p-3 bg-slate-950 border-b border-slate-800 flex items-center justify-between">
            <div className="flex items-center gap-2">
              <span className="material-symbols-outlined text-sky-400 text-[18px]">location_on</span>
              <h2 className="text-xs font-mono-code font-bold uppercase text-slate-200">
                Geographic Locations ({totalLocations.toLocaleString()})
              </h2>
            </div>
            <span className="text-xs font-mono-code text-slate-500">
              Page {locPage} of {locPages}
            </span>
          </div>

          <div className="flex-1 overflow-auto max-h-[440px]">
            <table className="w-full text-left border-collapse select-text text-xs font-mono-code">
              <thead className="sticky top-0 bg-slate-950/90 border-b border-slate-800 text-[10px] text-slate-400 uppercase font-bold">
                <tr className="h-8">
                  <th className="px-3 w-12 border-r border-slate-800 text-center">#</th>
                  <th className="px-3 border-r border-slate-800">PIN Code</th>
                  <th className="px-3 border-r border-slate-800">Latitude</th>
                  <th className="px-3 border-r border-slate-800">Longitude</th>
                  <th className="px-3">Radius</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800">
                {locLoading ? (
                  <tr>
                    <td colSpan={5} className="py-12 text-center text-slate-500">
                      Loading configured locations...
                    </td>
                  </tr>
                ) : locations.length === 0 ? (
                  <tr>
                    <td colSpan={5} className="py-12 text-center text-slate-500">
                      No locations found in dataset.
                    </td>
                  </tr>
                ) : (
                  locations.map((loc, idx) => (
                    <tr key={loc.location_id} className="h-8 hover:bg-slate-800/50">
                      <td className="px-3 border-r border-slate-800 text-center text-slate-500 text-[11px]">
                        {(locPage - 1) * 100 + idx + 1}
                      </td>
                      <td className="px-3 border-r border-slate-800 font-semibold text-sky-400">
                        {loc.pincode}
                      </td>
                      <td className="px-3 border-r border-slate-800 text-slate-300">
                        {loc.latitude?.toFixed(4)}
                      </td>
                      <td className="px-3 border-r border-slate-800 text-slate-300">
                        {loc.longitude?.toFixed(4)}
                      </td>
                      <td className="px-3 text-slate-400">
                        {loc.radius_km} km
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>

          <div className="p-2.5 bg-slate-950 border-t border-slate-800 flex items-center justify-between text-xs font-mono-code text-slate-400">
            <span>Showing {locations.length} of {totalLocations} records</span>
            <div className="flex gap-1">
              <button
                onClick={() => locPage > 1 && loadLocations(locPage - 1)}
                disabled={locPage <= 1 || locLoading}
                className="px-2.5 py-1 bg-slate-800 border border-slate-700 rounded hover:bg-slate-700 text-slate-300 disabled:opacity-40 cursor-pointer"
              >
                Prev
              </button>
              <button
                onClick={() => locPage < locPages && loadLocations(locPage + 1)}
                disabled={locPage >= locPages || locLoading}
                className="px-2.5 py-1 bg-slate-800 border border-slate-700 rounded hover:bg-slate-700 text-slate-300 disabled:opacity-40 cursor-pointer"
              >
                Next
              </button>
            </div>
          </div>
        </div>

        {/* PANEL B: CATEGORY PERSONAS (5 COLS) */}
        <div className="lg:col-span-5 bg-slate-900 border border-slate-800 rounded flex flex-col shadow-sm overflow-hidden">
          <div className="p-3 bg-slate-950 border-b border-slate-800 flex items-center justify-between">
            <div className="flex items-center gap-2">
              <span className="material-symbols-outlined text-sky-400 text-[18px]">category</span>
              <h2 className="text-xs font-mono-code font-bold uppercase text-slate-200">
                Categories ({totalCategories.toLocaleString()})
              </h2>
            </div>
            <span className="text-xs font-mono-code text-slate-500">
              Page {catPage} of {catPages}
            </span>
          </div>

          <div className="flex-1 overflow-auto max-h-[440px]">
            <table className="w-full text-left border-collapse select-text text-xs font-mono-code">
              <thead className="sticky top-0 bg-slate-950/90 border-b border-slate-800 text-[10px] text-slate-400 uppercase font-bold">
                <tr className="h-8">
                  <th className="px-3 w-12 border-r border-slate-800 text-center">#</th>
                  <th className="px-3">Category Persona</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800">
                {catLoading ? (
                  <tr>
                    <td colSpan={2} className="py-12 text-center text-slate-500">
                      Loading categories...
                    </td>
                  </tr>
                ) : categories.length === 0 ? (
                  <tr>
                    <td colSpan={2} className="py-12 text-center text-slate-500">
                      No categories found.
                    </td>
                  </tr>
                ) : (
                  categories.map((cat, idx) => (
                    <tr key={cat.category_id} className="h-8 hover:bg-slate-800/50">
                      <td className="px-3 border-r border-slate-800 text-center text-slate-500 text-[11px]">
                        {(catPage - 1) * 100 + idx + 1}
                      </td>
                      <td className="px-3 font-semibold text-slate-200">
                        {cat.category_name}
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>

          <div className="p-2.5 bg-slate-950 border-t border-slate-800 flex items-center justify-between text-xs font-mono-code text-slate-400">
            <span>Showing {categories.length} of {totalCategories} records</span>
            <div className="flex gap-1">
              <button
                onClick={() => catPage > 1 && loadCategories(catPage - 1)}
                disabled={catPage <= 1 || catLoading}
                className="px-2.5 py-1 bg-slate-800 border border-slate-700 rounded hover:bg-slate-700 text-slate-300 disabled:opacity-40 cursor-pointer"
              >
                Prev
              </button>
              <button
                onClick={() => catPage < catPages && loadCategories(catPage + 1)}
                disabled={catPage >= catPages || catLoading}
                className="px-2.5 py-1 bg-slate-800 border border-slate-700 rounded hover:bg-slate-700 text-slate-300 disabled:opacity-40 cursor-pointer"
              >
                Next
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
