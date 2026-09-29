import React, { useCallback, useEffect, useState } from 'react';
import { fetchLeads, type Lead } from '../api';

/**
 * People who tapped "Call me back".
 *
 * Each row carries everything needed to act on it — who, where, which
 * campaign — because a lead that requires looking someone up is a lead that
 * waits. The WhatsApp link opens a chat with that number directly.
 *
 * Only quick-reply taps reach here. Meta reports nothing when a
 * call-to-action URL button is tapped; those are counted as link visits.
 */

const WINDOW_MINUTES = 60 * 24;

const since = (iso: string) => {
  const mins = Math.round((Date.now() - new Date(iso).getTime()) / 60000);
  if (mins < 1) return 'just now';
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.round(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return new Date(iso).toLocaleDateString(undefined,
    { day: '2-digit', month: 'short' });
};

export const LeadsPanel: React.FC = () => {
  const [leads, setLeads] = useState<Lead[]>([]);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    try {
      setLeads(await fetchLeads(15));
    } catch {
      setLeads([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
    // Polled rather than pushed: a tap can arrive at any time and the page is
    // often left open.
    const timer = setInterval(load, 60000);
    return () => clearInterval(timer);
  }, [load]);

  const fresh = leads.filter(
    l => (Date.now() - new Date(l.clicked_at).getTime()) / 60000 < WINDOW_MINUTES
  ).length;

  return (
    <div className="bg-slate-900 border border-slate-800 rounded shadow-sm overflow-hidden">
      <div className="flex items-center justify-between gap-3 p-4 border-b border-slate-800">
        <div className="flex items-center gap-2 min-w-0">
          <span className="material-symbols-outlined text-[20px] text-amber-400">
            notifications_active
          </span>
          <h3 className="text-base font-semibold text-slate-100 truncate">
            Callback Requests
          </h3>
          {fresh > 0 && (
            <span className="text-[10px] font-mono-code font-bold uppercase px-1.5 py-0.5
                             rounded border text-amber-400 border-amber-800 bg-amber-950/50">
              {fresh} today
            </span>
          )}
        </div>
        <button
          onClick={load}
          className="text-slate-500 hover:text-slate-200 transition-colors cursor-pointer"
          title="Refresh"
        >
          <span className={`material-symbols-outlined text-[17px] ${loading ? 'animate-spin' : ''}`}>
            refresh
          </span>
        </button>
      </div>

      {loading && leads.length === 0 ? (
        <p className="px-4 py-6 text-xs text-slate-500">Loading…</p>
      ) : leads.length === 0 ? (
        <p className="px-4 py-6 text-xs text-slate-500 leading-relaxed">
          Nobody has tapped a quick-reply button yet. Taps on a
          call-to-action link are counted as link visits instead — Meta sends
          no event for those.
        </p>
      ) : (
        <ul className="divide-y divide-slate-800 max-h-[320px] overflow-y-auto">
          {leads.map(l => (
            <li key={l.click_id} className="px-4 py-3 hover:bg-slate-800/40 transition-colors">
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="text-sm font-medium text-slate-100 truncate">
                    {l.name || l.phone || 'Unknown'}
                  </div>
                  <div className="text-[11px] font-mono-code text-slate-400 mt-0.5">
                    {l.phone}
                  </div>
                  <div className="flex flex-wrap items-center gap-1.5 mt-1.5">
                    {l.category && (
                      <span className="text-[10px] px-1.5 py-0.5 rounded border border-slate-700
                                       bg-slate-800 text-slate-300 truncate max-w-[160px]">
                        {l.category}
                      </span>
                    )}
                    {(l.district || l.state) && (
                      <span className="text-[10px] text-slate-500">
                        {[l.district, l.state].filter(Boolean).join(', ')}
                      </span>
                    )}
                  </div>
                  {l.button_text && (
                    <div className="text-[11px] text-amber-400 mt-1.5">
                      tapped “{l.button_text}”
                      {l.campaign && <span className="text-slate-600"> · {l.campaign}</span>}
                    </div>
                  )}
                </div>

                <div className="flex flex-col items-end gap-1.5 shrink-0">
                  <span className="text-[10px] text-slate-500 whitespace-nowrap">
                    {since(l.clicked_at)}
                  </span>
                  {l.phone && (
                    <a
                      href={`https://wa.me/${l.phone.replace(/^\+/, '')}`}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-[10px] font-semibold px-2 py-1 rounded border
                                 border-emerald-800 bg-emerald-950 text-emerald-300
                                 hover:bg-emerald-900 transition-colors whitespace-nowrap"
                    >
                      Reply
                    </a>
                  )}
                </div>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
};
