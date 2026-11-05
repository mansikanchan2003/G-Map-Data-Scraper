import React, { useEffect, useMemo, useState } from 'react';
import { fetchDispositionLeads, type DispositionLead, type DispositionLeads } from '../api/inbox';
import { formatDateTime } from '../utils/datetime';

/**
 * The candidates behind a count on the Dispositions tab (the user,
 * 2026-11-05): a pop-up opened from a category or a sub-category, with each
 * candidate's name and number, their business and its category, where they
 * are (district, state, PIN), the SBI branch nearest them with its code and
 * AO, the campaign that reached them, and the next action item.
 *
 * The banner keeps Eko's teal and gold in either theme; the rest uses the
 * theme ramps the light theme redefines.
 */

const Icon: React.FC<{ name: string; className?: string }> = ({ name, className = '' }) =>
  <span className={`material-symbols-outlined ${className}`} aria-hidden="true">{name}</span>;

const TEAL = 'linear-gradient(120deg, #0a3543 0%, #16435a 55%, #1d5a6e 100%)';
const GOLD = '#f9ab10';
const ACCENT: Record<string, string> = { positive: '#34d399', follow_up: '#f9ab10', negative: '#fb7185', other: '#94a3b8' };

const initials = (name: string) =>
  name.replace(/^\+/, '').split(/\s+/).filter(Boolean).slice(0, 2).map(w => w[0]).join('').toUpperCase() || '?';
const chat = (phone: string) => `#inbox/${phone.replace(/\D/g, '')}`;

const Fact: React.FC<{ icon: string; label: string; children: React.ReactNode; tint: string }> = ({ icon, label, children, tint }) => (
  <div className="flex gap-2.5 min-w-0">
    <span className={`h-7 w-7 rounded-lg flex items-center justify-center shrink-0 ${tint}`}><Icon name={icon} className="text-[16px]" /></span>
    <div className="min-w-0">
      <div className="text-[10.5px] uppercase tracking-wider font-semibold text-slate-500">{label}</div>
      <div className="text-[12.5px] text-slate-200 leading-snug break-words">{children}</div>
    </div>
  </div>
);

const LeadCard: React.FC<{ l: DispositionLead }> = ({ l }) => {
  const place = [l.district, l.state].filter(Boolean).join(', ');
  return (
    <article className="rounded-xl border border-slate-800 bg-slate-900 overflow-hidden flex flex-col">
      <header className="flex items-center gap-3 px-4 py-3 border-b border-slate-800 bg-slate-950/50">
        <span className="h-10 w-10 rounded-full flex items-center justify-center text-[13px] font-bold text-white shrink-0"
          style={{ background: TEAL }}>{initials(l.name || l.phone)}</span>
        <div className="min-w-0 flex-1">
          <a href={chat(l.phone)} className="block text-[14px] font-semibold text-slate-100 hover:text-sky-300 truncate">{l.name || l.phone}</a>
          <div className="text-[12px] text-slate-400 tabular-nums">{l.phone}</div>
        </div>
        <div className="text-right shrink-0">
          <span className="inline-block px-2 py-0.5 rounded-full text-[11px] font-semibold bg-slate-800 text-slate-200">{l.disposition}</span>
          {l.since && <div className="text-[10.5px] text-slate-500 mt-1">{formatDateTime(l.since)}</div>}
        </div>
      </header>

      <div className="p-4 grid gap-3 sm:grid-cols-2 flex-1">
        <Fact icon="storefront" label="Business · category" tint="bg-sky-950 text-sky-300">
          {l.business_name || '—'}{l.category && <span className="text-slate-400"> · {l.category}</span>}
        </Fact>
        <Fact icon="location_on" label="District, state, PIN" tint="bg-violet-950 text-violet-300">
          {place || '—'}{l.pincode && <span className="text-slate-400"> · {l.pincode}</span>}
        </Fact>
        <Fact icon="account_balance" label="Nearest SBI branch" tint="bg-emerald-950 text-emerald-300">
          {l.branch ? (
            <>
              <b className="text-slate-100">{l.branch.branch_code}</b> · {l.branch.branch_name}
              <span className="block text-slate-400">AO: {l.branch.ao || '—'} · {l.branch.distance_km} km</span>
            </>
          ) : <span className="text-slate-400">None of ours within 50 km</span>}
        </Fact>
        <Fact icon="campaign" label="Came from campaign" tint="bg-amber-950 text-amber-300">
          {l.campaign || '—'}
        </Fact>
        {(l.language || l.stage) && (
          <Fact icon="translate" label="Language · step" tint="bg-slate-800 text-slate-300">
            {[l.language, l.stage].filter(Boolean).join(' · ')}
          </Fact>
        )}
      </div>

      <footer className="mx-4 mb-4 rounded-lg px-3 py-2.5 flex items-start gap-2.5 border border-amber-800/60 bg-amber-950">
        <Icon name="next_plan" className="text-[18px] text-amber-300 mt-[1px]" />
        <div className="min-w-0 flex-1">
          <div className="text-[10.5px] uppercase tracking-wider font-semibold text-amber-300">Next action item</div>
          {l.next ? (
            <>
              <div className="text-[12.5px] text-slate-100 font-medium leading-snug">{l.next.text}</div>
              <div className="text-[11px] text-slate-400 mt-0.5">{l.next.owner}{l.next.when ? ` · ${formatDateTime(l.next.when)}` : ''}</div>
            </>
          ) : (
            <div className="text-[12.5px] text-slate-300">{l.documents_submitted ? 'With Eko Acquisition: AutoGMap\'s part is done' : 'Nothing planned'}</div>
          )}
        </div>
        <a href={chat(l.phone)} className="text-[11.5px] font-semibold text-sky-300 hover:underline whitespace-nowrap self-center">Chat kholein</a>
      </footer>
    </article>
  );
};

/** The pop-up: a banner with the count, a search, and the candidates as a grid of cards. */
export const DispositionLeadsModal: React.FC<{ dkey: string; onClose: () => void }> = ({ dkey, onClose }) => {
  const [data, setData] = useState<DispositionLeads | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [q, setQ] = useState('');
  useEffect(() => { fetchDispositionLeads(dkey).then(setData).catch(e => setError(e.message)); }, [dkey]);
  useEffect(() => {
    const key = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', key);
    return () => window.removeEventListener('keydown', key);
  }, [onClose]);

  const shown = useMemo(() => {
    const t = q.trim().toLowerCase();
    if (!data || !t) return data?.leads || [];
    return data.leads.filter(l => [l.name, l.phone, l.district, l.state, l.pincode, l.category, l.campaign, l.business_name]
      .some(v => (v || '').toLowerCase().includes(t)));
  }, [data, q]);

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center bg-slate-950/80 backdrop-blur-sm p-3 sm:p-6 overflow-y-auto"
      onClick={onClose} role="dialog" aria-modal="true">
      <div className="w-full max-w-6xl my-auto rounded-2xl overflow-hidden border border-slate-800 bg-slate-950 shadow-2xl"
        onClick={e => e.stopPropagation()}>
        <header className="px-5 py-4 text-white" style={{ background: TEAL }}>
          <div className="flex items-start gap-3.5">
            <span className="h-12 w-12 rounded-2xl flex items-center justify-center text-[22px] font-bold text-[#0a3543] shrink-0"
              style={{ background: data ? ACCENT[data.group] || GOLD : GOLD }}>{data ? data.count : '…'}</span>
            <div className="min-w-0 flex-1">
              <div className="text-[11px] uppercase tracking-[0.14em] font-semibold" style={{ color: GOLD }}>
                {data && data.category !== data.label ? data.category : 'Disposition'}
              </div>
              <h3 className="text-[19px] font-semibold leading-tight">{data?.label || 'Loading…'}</h3>
              {data?.action && <p className="text-[12.5px] text-white/75 mt-1">Sheet ka action: {data.action}</p>}
            </div>
            <button onClick={onClose} aria-label="Close"
              className="h-8 w-8 rounded-lg bg-white/10 hover:bg-white/20 flex items-center justify-center cursor-pointer shrink-0">
              <Icon name="close" className="text-[19px]" />
            </button>
          </div>
          {data && data.count > 0 && (
            <label className="mt-3.5 flex items-center gap-2 h-9 px-3 rounded-lg bg-white/10 focus-within:bg-white/15 max-w-md">
              <Icon name="search" className="text-[18px] text-white/70" />
              <input value={q} onChange={e => setQ(e.target.value)} placeholder="Naam, number, jagah, category, campaign…"
                className="flex-1 bg-transparent text-[13px] text-white placeholder:text-white/50 outline-none" />
            </label>
          )}
        </header>

        <div className="p-4 sm:p-5">
          {error && <div className="p-3 rounded-lg border border-rose-800/60 bg-rose-950 text-rose-300 text-sm">Could not load: {error}</div>}
          {!data && !error && <div className="grid gap-4 md:grid-cols-2">{[0, 1, 2, 3].map(i => <div key={i} className="h-56 rounded-xl bg-slate-900 animate-pulse" />)}</div>}
          {data && (shown.length ? (
            <div className="grid gap-4 md:grid-cols-2">{shown.map(l => <LeadCard key={l.phone} l={l} />)}</div>
          ) : (
            <div className="py-12 flex flex-col items-center gap-2 text-center">
              <Icon name="person_search" className="text-[32px] text-slate-500" />
              <span className="text-[13px] text-slate-400">{data.count ? 'Is search se koi nahi mila.' : 'Is disposition mein abhi koi candidate nahi.'}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};
