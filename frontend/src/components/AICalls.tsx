import React, { useEffect, useState } from 'react';
import { fetchAICalls, type AICall } from '../api/inbox';

/**
 * The AI calling agent's calls with one person (the user, 2026-11-05): each
 * call as a card with the outcome AutoGMap marked from it and why, a peek at
 * how it ended, and the whole call as a chat in a pop-up: the agent on the
 * left in Eko teal, the candidate on the right.
 *
 * The card headers keep their colours in both themes (white text on the
 * outcome's group colour); the rest uses the theme ramps.
 */

const Icon: React.FC<{ name: string; className?: string }> = ({ name, className = '' }) =>
  <span className={`material-symbols-outlined ${className}`} aria-hidden="true">{name}</span>;

const TEAL = 'linear-gradient(120deg, #0a3543 0%, #16435a 55%, #1d5a6e 100%)';
const HERO: Record<string, string> = {
  positive: 'linear-gradient(135deg, #065f46 0%, #059669 100%)',
  follow_up: 'linear-gradient(135deg, #92400e 0%, #d97706 100%)',
  negative: 'linear-gradient(135deg, #881337 0%, #be123c 100%)',
  other: 'linear-gradient(135deg, #1e293b 0%, #475569 100%)',
};
const STATUS: Record<string, { label: string; icon: string }> = {
  answered: { label: 'Baat hui', icon: 'call' },
  no_answer: { label: 'Uthaya nahi', icon: 'phone_missed' },
  busy: { label: 'Busy', icon: 'phone_paused' },
  failed: { label: 'Laga nahi', icon: 'phone_disabled' },
};

const when = (iso: string | null) => iso
  ? new Date(iso).toLocaleString('en-IN', { timeZone: 'Asia/Kolkata', day: 'numeric', month: 'short', hour: 'numeric', minute: '2-digit' })
  : '—';
const length = (s: number | null) => (s == null ? '' : s < 60 ? `${s}s` : `${Math.floor(s / 60)}m ${s % 60}s`);

/** The call's chat, bubble by bubble. */
const Chat: React.FC<{ c: AICall; limit?: number }> = ({ c, limit }) => {
  const turns = limit ? c.turns.slice(-limit) : c.turns;
  if (!turns.length) return <div className="text-[12px] text-slate-500 italic">Is call mein koi baat nahi hui.</div>;
  return (
    <div className="space-y-2">
      {turns.map((t, i) => {
        const agent = t.speaker === 'agent';
        return (
          <div key={i} className={`flex ${agent ? 'justify-start' : 'justify-end'}`}>
            <div className={`max-w-[85%] rounded-2xl px-3 py-2 text-[12.5px] leading-snug shadow-sm ${agent
              ? 'rounded-tl-sm text-white' : 'rounded-tr-sm bg-slate-800 text-slate-100 border border-slate-700'}`}
              style={agent ? { background: TEAL } : undefined}>
              <div className={`text-[10px] font-semibold uppercase tracking-wider mb-0.5 ${agent ? 'text-[#f9ab10]' : 'text-slate-400'}`}>
                {agent ? 'AI agent' : 'Candidate'}
              </div>
              {t.text}
            </div>
          </div>
        );
      })}
    </div>
  );
};

const Header: React.FC<{ c: AICall; big?: boolean }> = ({ c, big }) => {
  const st = STATUS[c.status] || { label: c.status, icon: 'call' };
  return (
    <div className={`relative overflow-hidden text-white ${big ? 'pl-5 pr-14 py-4' : 'px-3.5 py-3'}`}
      style={{ background: HERO[c.outcome_group || 'other'] || HERO.other }}>
      <Icon name="support_agent" className="absolute -right-3 -bottom-5 text-[80px] text-white/10 pointer-events-none" />
      <div className="relative flex items-center gap-2.5">
        <span className={`${big ? 'h-10 w-10' : 'h-8 w-8'} rounded-xl bg-white/20 ring-1 ring-white/25 flex items-center justify-center shrink-0`}>
          <Icon name={st.icon} className={big ? 'text-[21px]' : 'text-[17px]'} />
        </span>
        <div className="min-w-0 flex-1">
          <div className="text-[10.5px] uppercase tracking-[0.12em] font-semibold text-white/75">AI call · {when(c.started_at)}</div>
          <div className={`${big ? 'text-[17px]' : 'text-[13.5px]'} font-semibold leading-tight truncate`}>
            {c.outcome_label || 'Outcome clear nahi: team dekhe'}
          </div>
        </div>
        <div className="text-right shrink-0 text-[11px] text-white/85">
          <div className="font-semibold">{st.label}</div>
          <div className="tabular-nums">{length(c.duration_seconds)}</div>
        </div>
      </div>
    </div>
  );
};

const Modal: React.FC<{ c: AICall; onClose: () => void }> = ({ c, onClose }) => {
  useEffect(() => {
    const k = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', k);
    return () => window.removeEventListener('keydown', k);
  }, [onClose]);
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/80 backdrop-blur-sm p-3 sm:p-6"
      onClick={onClose} role="dialog" aria-modal="true">
      <div className="w-full max-w-xl max-h-[90vh] flex flex-col rounded-2xl overflow-hidden border border-slate-800 bg-slate-950 shadow-2xl"
        onClick={e => e.stopPropagation()}>
        <div className="relative">
          <Header c={c} big />
          <button onClick={onClose} aria-label="Close"
            className="absolute top-3 right-3 h-8 w-8 rounded-lg bg-white/15 hover:bg-white/25 text-white flex items-center justify-center cursor-pointer">
            <Icon name="close" className="text-[19px]" />
          </button>
        </div>
        {c.outcome_reason && (
          <div className="mx-4 mt-4 flex gap-2.5 rounded-xl border border-sky-800/60 bg-sky-950 px-3.5 py-2.5 text-[12.5px]">
            <Icon name="fact_check" className="text-[18px] text-sky-300 shrink-0" />
            <div><span className="font-semibold text-slate-100">Outcome kyun: </span><span className="text-slate-300">{c.outcome_reason}</span></div>
          </div>
        )}
        <div className="p-4 overflow-y-auto flex-1"><Chat c={c} /></div>
        {c.recording_url && (
          <div className="px-4 pb-4">
            <audio controls src={c.recording_url} className="w-full" />
          </div>
        )}
      </div>
    </div>
  );
};

/** Every AI call with this person, newest first; nothing at all when there are none. */
export const AICallsCard: React.FC<{ phone: string; version?: string }> = ({ phone, version }) => {
  const [calls, setCalls] = useState<AICall[] | null>(null);
  const [open, setOpen] = useState<AICall | null>(null);
  useEffect(() => {
    let live = true;
    fetchAICalls(phone).then(r => { if (live) setCalls(r); }).catch(() => { if (live) setCalls([]); });
    return () => { live = false; };
  }, [phone, version]);
  if (!calls || !calls.length) return null;
  return (
    <section className="space-y-2.5">
      <div className="text-[11px] uppercase tracking-wider text-slate-400 font-semibold flex items-center gap-1.5">
        <Icon name="support_agent" className="text-[16px] text-[#f9ab10]" />AI calls
        <span className="ml-auto px-1.5 py-0.5 rounded-full bg-slate-800 text-slate-300 tabular-nums normal-case tracking-normal">{calls.length}</span>
      </div>
      {calls.map(c => (
        <article key={c.call_id} className="rounded-xl overflow-hidden border border-slate-800 bg-slate-950 shadow-sm">
          <button onClick={() => setOpen(c)} className="block w-full text-left cursor-pointer hover:brightness-110 transition">
            <Header c={c} />
          </button>
          <div className="p-3 space-y-2.5">
            {c.outcome_reason && <div className="text-[11.5px] text-slate-400 leading-snug">{c.outcome_reason}</div>}
            <Chat c={c} limit={2} />
            {c.turns.length > 0 && <button onClick={() => setOpen(c)}
              className="w-full h-8 rounded-lg text-[12px] font-semibold text-[#0a3543] inline-flex items-center justify-center gap-1.5 hover:brightness-110 cursor-pointer"
              style={{ background: '#f9ab10' }}>
              <Icon name="forum" className="text-[16px]" />Poori call dekhein ({c.turns.length})
            </button>}
          </div>
        </article>
      ))}
      {open && <Modal c={open} onClose={() => setOpen(null)} />}
    </section>
  );
};
