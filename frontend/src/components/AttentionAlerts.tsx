import React, { useCallback, useEffect, useState } from 'react';
import { ATTENTION_CHANGED, fetchAttentionAlerts, fetchRecentlyResolved, type AttentionAlert, type Ticket } from '../api/inbox';

/**
 * Conversations waiting for a person, shown on every page of the app.
 *
 * Each is a raised ticket. An alert has no close button: it goes only when
 * someone presses "Question resolved" in that chat. Tapping one opens the
 * chat. The stack can be folded into a small pill with the count, which stays
 * on screen. A ticket solved in the last two hours shows as a green notice,
 * which each person can dismiss for themselves.
 */

const POLL_MS = 20_000;
const DISMISSED_KEY = 'tickets-resolved-seen';

const readSeen = (): string[] => {
  try { return JSON.parse(localStorage.getItem(DISMISSED_KEY) || '[]'); } catch { return []; }
};

const ago = (iso: string | null) => {
  if (!iso) return '';
  const mins = Math.max(0, Math.round((Date.now() - new Date(iso).getTime()) / 60000));
  if (mins < 1) return 'just now';
  if (mins < 60) return `${mins} min ago`;
  const hours = Math.round(mins / 60);
  return hours < 24 ? `${hours} h ago` : `${Math.round(hours / 24)} d ago`;
};

export const AttentionAlerts: React.FC = () => {
  const [alerts, setAlerts] = useState<AttentionAlert[]>([]);
  const [resolved, setResolved] = useState<Ticket[]>([]);
  const [seen, setSeen] = useState<string[]>(readSeen);
  const [folded, setFolded] = useState(() => {
    try { return sessionStorage.getItem('attention-folded') === '1'; } catch { return false; }
  });
  const [, tick] = useState(0);
  // In the Inbox the list already shows them; the stack folds there so it
  // does not cover the chat, and opens again elsewhere.
  const [inInbox, setInInbox] = useState(() => /^#(inbox|whatsapp-inbox)/.test(window.location.hash));
  useEffect(() => {
    const onHash = () => setInInbox(/^#(inbox|whatsapp-inbox)/.test(window.location.hash));
    window.addEventListener('hashchange', onHash);
    return () => window.removeEventListener('hashchange', onHash);
  }, []);

  const load = useCallback(() => {
    fetchAttentionAlerts().then(setAlerts).catch(() => { /* keep what is shown */ });
    fetchRecentlyResolved().then(setResolved).catch(() => { /* keep what is shown */ });
  }, []);
  const dismiss = (id: string) => {
    const next = [...seen, id].slice(-100);
    setSeen(next);
    try { localStorage.setItem(DISMISSED_KEY, JSON.stringify(next)); } catch { /* private window */ }
  };
  const notices = resolved.filter(t => !seen.includes(t.ticket_id)).slice(0, 3);
  const noticeStack = notices.length > 0 && (
    <div className="fixed bottom-4 right-3 z-50 w-[min(320px,calc(100vw-1.5rem))] flex flex-col gap-2" role="status" aria-live="polite">
      {notices.map(t => (
        <div key={t.ticket_id} className="rounded-lg border border-emerald-800/60 bg-emerald-950 shadow-lg p-3 flex gap-2.5">
          <span className="material-symbols-outlined text-[20px] text-emerald-300">task_alt</span>
          <div className="min-w-0 flex-1">
            <div className="text-sm font-semibold text-slate-100">Ticket {t.ticket_id} resolved</div>
            <div className="text-[11.5px] text-slate-400 truncate">
              {t.raised_by || t.phone}{t.resolved_by ? ` · by ${t.resolved_by.split('@')[0]}` : ''} · {ago(t.resolved_at)}
            </div>
          </div>
          <button onClick={() => dismiss(t.ticket_id)} title="Dismiss"
            className="h-6 w-6 rounded-full text-slate-400 hover:bg-slate-900 flex items-center justify-center cursor-pointer">
            <span className="material-symbols-outlined text-[16px]">close</span>
          </button>
        </div>
      ))}
    </div>
  );

  useEffect(() => {
    load();
    const poll = setInterval(load, POLL_MS);
    const clock = setInterval(() => tick(t => t + 1), 60_000);
    window.addEventListener(ATTENTION_CHANGED, load);
    return () => { clearInterval(poll); clearInterval(clock); window.removeEventListener(ATTENTION_CHANGED, load); };
  }, [load]);

  useEffect(() => { try { sessionStorage.setItem('attention-folded', folded ? '1' : '0'); } catch { /* private window */ } }, [folded]);

  if (!alerts.length) return <>{noticeStack}</>;
  const open = (a: AttentionAlert) => { window.location.hash = `inbox/${a.phone.replace(/\D/g, '')}`; };

  if (folded || inInbox) {
    return (<>
      <button onClick={() => { if (inInbox) { window.location.hash = `inbox/${alerts[0].phone.replace(/\D/g, '')}`; } else setFolded(false); }}
        title={inInbox ? 'Open the latest conversation that needs attention' : 'Show the conversations that need attention'}
        className="fixed top-16 right-3 z-50 inline-flex items-center gap-1.5 pl-2 pr-3 py-1.5 rounded-full bg-rose-600 text-white text-xs font-semibold shadow-lg cursor-pointer animate-pulse">
        <span className="material-symbols-outlined text-[18px]">priority_high</span>
        {alerts.length} ticket{alerts.length === 1 ? '' : 's'} raised · need{alerts.length === 1 ? 's' : ''} attention
      </button>
      {noticeStack}
    </>);
  }

  const shown = alerts.slice(0, 3);
  return (<>
    {noticeStack}
    <div className="fixed top-16 right-3 z-50 w-[min(340px,calc(100vw-1.5rem))] flex flex-col gap-2" role="alert" aria-live="polite">
      <div className="flex items-center justify-between rounded-lg bg-rose-600 text-white px-3 py-1.5 shadow-lg">
        <span className="flex items-center gap-1.5 text-xs font-semibold">
          <span className="material-symbols-outlined text-[18px]">priority_high</span>
          Attention needed · {alerts.length} ticket{alerts.length === 1 ? '' : 's'} raised
        </span>
        <button onClick={() => setFolded(true)} title="Fold (the alerts stay until resolved in the chat)"
          className="h-6 w-6 rounded-full hover:bg-white/15 flex items-center justify-center cursor-pointer">
          <span className="material-symbols-outlined text-[18px]">expand_less</span>
        </button>
      </div>
      {shown.map(a => (
        <button key={a.phone} onClick={() => open(a)}
          className="text-left rounded-lg border border-rose-800/60 bg-slate-900 shadow-lg p-3 hover:border-rose-500 cursor-pointer">
          <div className="flex items-center justify-between gap-2">
            <span className="text-sm font-semibold text-slate-100 truncate">{a.name || a.phone}</span>
            <span className="text-[10.5px] text-slate-500 whitespace-nowrap">{ago(a.at)}</span>
          </div>
          {a.ticket_id && (
            <div className="mt-1 inline-flex items-center gap-1 text-[10.5px] font-semibold px-1.5 py-0.5 rounded bg-rose-950 text-rose-300 border border-rose-800/60">
              <span className="material-symbols-outlined text-[13px]">confirmation_number</span>Ticket raised · {a.ticket_id}
            </div>
          )}
          <div className="text-[12px] text-rose-300 mt-1 line-clamp-2 break-words">{a.reason || 'Needs a reply'}</div>
          <div className="text-[11px] text-sky-300 mt-1.5 flex items-center gap-1">
            <span className="material-symbols-outlined text-[15px]">chat</span>Open the chat
          </div>
        </button>
      ))}
      {alerts.length > shown.length && (
        <button onClick={() => { window.location.hash = 'inbox'; }}
          className="text-center text-[11.5px] font-semibold text-rose-300 bg-slate-900 border border-slate-800 rounded-lg py-1.5 shadow cursor-pointer hover:border-rose-500">
          and {alerts.length - shown.length} more in the Inbox
        </button>
      )}
    </div>
  </>);
};
