import React, { useCallback, useEffect, useState } from 'react';
import { fetchLeads, replyToLead, type Lead } from '../api';

/**
 * People who tapped "Call me back", and the place to answer them.
 *
 * Each row carries everything needed to act on it — who, where, which
 * campaign — because a lead that requires looking someone up is a lead that
 * waits. Replying happens here rather than in a personal WhatsApp: a message
 * sent from this box goes out from the business number, in the thread the
 * campaign started.
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

/** How long is left to send a plain message, in words. */
const windowLeft = (iso: string) => {
  const mins = Math.floor((new Date(iso).getTime() - Date.now()) / 60000);
  if (mins <= 0) return null;
  if (mins < 60) return `${mins}m left`;
  return `${Math.floor(mins / 60)}h left`;
};

const LeadRow: React.FC<{ lead: Lead; onSent: () => void }> = ({ lead, onSent }) => {
  const [open, setOpen] = useState(false);
  const [text, setText] = useState('');
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const left = windowLeft(lead.window_expires_at);
  const closed = left === null;

  const send = async () => {
    const body = text.trim();
    if (!body || sending) return;
    setSending(true);
    setError(null);
    try {
      await replyToLead(lead.click_id, body);
      setText('');
      setOpen(false);
      onSent();
    } catch (err) {
      setError((err as { message?: string })?.message || 'Could not send');
    } finally {
      setSending(false);
    }
  };

  return (
    <li className="px-4 py-3">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="text-sm font-medium text-slate-100 truncate">
            {lead.name || lead.phone || 'Unknown'}
          </div>
          <div className="text-[11px] font-mono-code text-slate-400 mt-0.5">
            {lead.phone}
          </div>
          <div className="flex flex-wrap items-center gap-1.5 mt-1.5">
            {lead.category && (
              <span className="text-[10px] px-1.5 py-0.5 rounded border border-slate-700
                               bg-slate-800 text-slate-300 truncate max-w-[160px]">
                {lead.category}
              </span>
            )}
            {(lead.district || lead.state) && (
              <span className="text-[10px] text-slate-500">
                {[lead.district, lead.state].filter(Boolean).join(', ')}
              </span>
            )}
          </div>
          {lead.button_text && (
            <div className="text-[11px] text-amber-400 mt-1.5">
              tapped “{lead.button_text}”
              {lead.campaign && <span className="text-slate-600"> · {lead.campaign}</span>}
            </div>
          )}
        </div>

        <div className="flex flex-col items-end gap-1.5 shrink-0">
          <span className="text-[10px] text-slate-500 whitespace-nowrap">
            {since(lead.clicked_at)}
          </span>
          {closed ? (
            // Said plainly rather than shown as a dead button: the reason it
            // cannot be done is the useful part.
            <span
              className="text-[10px] text-slate-500 whitespace-nowrap"
              title="Meta only allows a typed message within 24 hours of the tap. An approved template is the only way to reach this number now."
            >
              window closed
            </span>
          ) : (
            <button
              onClick={() => setOpen(o => !o)}
              className="text-[10px] font-semibold px-2 py-1 rounded border
                         border-emerald-800 bg-emerald-950 text-emerald-300
                         hover:bg-emerald-900 transition-colors whitespace-nowrap cursor-pointer"
            >
              {open ? 'Cancel' : 'Reply'}
            </button>
          )}
          {!closed && (
            <span className="text-[10px] text-slate-600 whitespace-nowrap">{left}</span>
          )}
        </div>
      </div>

      {/* What has already been said, so the same person is not answered twice. */}
      {lead.replies.length > 0 && (
        <ul className="mt-2 flex flex-col gap-1">
          {lead.replies.map(r => (
            <li
              key={r.reply_id}
              className={`text-[11px] rounded px-2 py-1.5 border ${
                r.status === 'SENT'
                  ? 'border-slate-800 bg-slate-950 text-slate-300'
                  : 'border-rose-900 bg-rose-950/50 text-rose-300'
              }`}
            >
              <span className="text-slate-600 mr-1">↩</span>
              {r.body}
              <span className="block text-[10px] text-slate-600 mt-0.5">
                {r.status === 'SENT' ? 'sent' : `failed — ${r.error_reason}`}
                {' · '}{since(r.sent_at)}
                {r.sent_by && ` · ${r.sent_by}`}
              </span>
            </li>
          ))}
        </ul>
      )}

      {open && !closed && (
        <div className="mt-2 flex flex-col gap-1.5">
          <textarea
            value={text}
            onChange={e => setText(e.target.value)}
            onKeyDown={e => {
              // Enter sends, as in a chat; Shift+Enter starts a line.
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                send();
              }
            }}
            rows={3}
            maxLength={4096}
            autoFocus
            placeholder={`Message ${lead.name || lead.phone}…`}
            className="w-full text-xs rounded border border-slate-700 bg-slate-950
                       text-slate-100 p-2 resize-y focus:outline-none
                       focus:border-emerald-600 placeholder:text-slate-600"
          />
          {error && (
            <p className="text-[11px] text-rose-400 leading-relaxed">{error}</p>
          )}
          <div className="flex items-center justify-between gap-2">
            <span className="text-[10px] text-slate-600">
              Sent from the business number · Enter to send
            </span>
            <button
              onClick={send}
              disabled={sending || !text.trim()}
              className="text-[11px] font-semibold px-3 py-1.5 rounded border
                         border-emerald-700 bg-emerald-900 text-emerald-100
                         hover:bg-emerald-800 transition-colors disabled:opacity-40
                         disabled:cursor-not-allowed cursor-pointer whitespace-nowrap"
            >
              {sending ? 'Sending…' : 'Send'}
            </button>
          </div>
        </div>
      )}
    </li>
  );
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
        <ul className="divide-y divide-slate-800 max-h-[420px] overflow-y-auto">
          {leads.map(l => (
            <LeadRow key={l.click_id} lead={l} onSent={load} />
          ))}
        </ul>
      )}
    </div>
  );
};
