import React, { useCallback, useEffect, useState } from 'react';
import { fetchNudgeTemplates, submitAllNudgeTemplates, submitNudgeTemplates, type NudgeTemplate } from '../api/inbox';

/**
 * The nudges that stand in for calls, for the team to read before any goes
 * to Meta: one per use case, in every language the bot speaks and in
 * Hinglish. Inside someone's 24-hour window they are sent as plain messages
 * already; outside it only an approved template can go, so each use case has
 * a Submit button that sends all its languages to Meta for review.
 */

const Icon: React.FC<{ name: string; className?: string }> = ({ name, className = '' }) =>
  <span className={`material-symbols-outlined ${className}`}>{name}</span>;
const LANG: Record<string, string> = {
  en: 'English', hi: 'Hindi', hinglish: 'Hinglish', gu: 'Gujarati', pa: 'Punjabi', mr: 'Marathi', bn: 'Bengali',
  ta: 'Tamil', te: 'Telugu', kn: 'Kannada', ml: 'Malayalam', or: 'Odia',
};
const STATUS: Record<string, { label: string; cls: string }> = {
  APPROVED: { label: 'Approved', cls: 'bg-emerald-950 text-emerald-300 border-emerald-800/60' },
  PENDING: { label: 'In review', cls: 'bg-sky-950 text-sky-300 border-sky-800/60' },
  REJECTED: { label: 'Rejected', cls: 'bg-rose-950 text-rose-300 border-rose-800/60' },
  FAILED: { label: 'Not accepted', cls: 'bg-rose-950 text-rose-300 border-rose-800/60' },
  NOT_SUBMITTED: { label: 'Not submitted', cls: 'bg-slate-800 text-slate-400 border-slate-700' },
};
const statusOf = (s: string) => STATUS[s] || { label: s.toLowerCase(), cls: 'bg-slate-800 text-slate-300 border-slate-700' };

export const NudgeTemplatesPanel: React.FC<{ readOnly?: boolean }> = ({ readOnly }) => {
  const [list, setList] = useState<NudgeTemplate[] | null>(null);
  const [open, setOpen] = useState<string | null>(null);
  const [lang, setLang] = useState('en');
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const load = useCallback(() => fetchNudgeTemplates().then(setList).catch(e => setError(e.message)), []);
  useEffect(() => { load(); }, [load]);

  const submit = async (t: NudgeTemplate) => {
    if (!window.confirm(`Send "${t.about}" to Meta for review, in all ${t.variants.length} languages?`)) return;
    setBusy(t.purpose); setError(null);
    try {
      const out = await submitNudgeTemplates(t.purpose);
      const failed = out.filter(o => o.error);
      if (failed.length) setError(`${failed.length} not accepted: ${failed[0].error}`);
      await load();
    } catch (e: any) { setError(e.message); }
    finally { setBusy(null); }
  };

  const submitAll = async () => {
    if (!list) return;
    const n = list.reduce((k, t) => k + t.variants.filter(v => ['NOT_SUBMITTED', 'REJECTED', 'FAILED'].includes(v.status)).length, 0);
    if (!window.confirm(`Send all ${n} nudge templates not yet with Meta for review?`)) return;
    setBusy('all'); setError(null);
    try {
      const out = await submitAllNudgeTemplates();
      const failed = Object.values(out).flat().filter(o => o.error);
      if (failed.length) setError(`${failed.length} not accepted: ${failed[0].error}`);
      await load();
    } catch (e: any) { setError(e.message); }
    finally { setBusy(null); }
  };

  if (!list) return error
    ? <div className="p-4 rounded-xl border border-rose-800/60 bg-rose-950 text-rose-300 text-sm">Could not load the nudges: {error}</div>
    : <div className="h-40 rounded-2xl bg-slate-900 border border-slate-800 animate-pulse" />;

  const approved = list.reduce((n, t) => n + t.variants.filter(v => v.status === 'APPROVED').length, 0);
  const all = list.reduce((n, t) => n + t.variants.length, 0);

  return (
    <section className="rounded-2xl border border-slate-800 bg-slate-900 p-5 shadow-sm select-text">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <h3 className="text-[15px] font-semibold text-slate-100 flex items-center gap-2">
          <span className="h-8 w-8 rounded-lg bg-emerald-950 text-emerald-300 flex items-center justify-center"><Icon name="forum" className="text-[18px]" /></span>
          Nudge templates
        </h3>
        <div className="flex flex-wrap items-center gap-3">
          <span className="text-[12px] text-slate-400"><b className="text-slate-100 tabular-nums">{approved}</b> of {all} approved by Meta</span>
          {!readOnly && list.some(t => t.variants.some(v => ['NOT_SUBMITTED', 'REJECTED', 'FAILED'].includes(v.status))) && (
            <button onClick={submitAll} disabled={busy === 'all'}
              className="inline-flex items-center gap-1.5 h-8 px-3 rounded-lg bg-emerald-600 text-white text-[12.5px] font-semibold hover:bg-emerald-500 cursor-pointer disabled:opacity-50">
              <Icon name="send" className="text-[15px]" />{busy === 'all' ? 'Submitting all…' : 'Submit all to Meta'}
            </button>
          )}
        </div>
      </div>
      <p className="text-[12.5px] text-slate-400 mt-2">
        One nudge for each use case, in every language. While someone's 24-hour window is open these go as plain messages
        already. Once it has shut, only a template Meta has approved can go, so read each one and press <b>Submit to Meta</b>.
        Until then those nudges wait (Follow-ups shows them as “Waiting”).
      </p>
      {error && <div className="mt-2 text-[12px] text-rose-300">{error}</div>}

      <ul className="mt-4 space-y-2">
        {list.map(t => {
          const isOpen = open === t.purpose;
          const counts = t.variants.reduce<Record<string, number>>((acc, v) => ({ ...acc, [v.status]: (acc[v.status] || 0) + 1 }), {});
          const shown = t.variants.find(v => v.variant === lang) || t.variants[0];
          const canSubmit = t.variants.some(v => ['NOT_SUBMITTED', 'REJECTED', 'FAILED'].includes(v.status));
          return (
            <li key={t.purpose} className="rounded-xl border border-slate-800 bg-slate-950/60">
              <button onClick={() => setOpen(isOpen ? null : t.purpose)} className="w-full flex flex-wrap items-center gap-2 px-3.5 py-2.5 text-left cursor-pointer">
                <span className="flex-1 min-w-[220px] text-[13px] font-semibold text-slate-200">{t.about}</span>
                {Object.entries(counts).map(([s, n]) => (
                  <span key={s} className={`px-2 py-0.5 rounded-full border text-[10.5px] font-semibold ${statusOf(s).cls}`}>{statusOf(s).label} {n}</span>
                ))}
                <Icon name={isOpen ? 'expand_less' : 'expand_more'} className="text-[18px] text-slate-500" />
              </button>
              {isOpen && (
                <div className="px-3.5 pb-3.5">
                  <div className="flex flex-wrap gap-1">
                    {t.variants.map(v => (
                      <button key={v.variant} onClick={() => setLang(v.variant)}
                        className={`px-2 py-0.5 rounded-md text-[11.5px] cursor-pointer border ${lang === v.variant
                          ? 'border-sky-600 bg-sky-950 text-sky-200' : 'border-slate-800 text-slate-400 hover:text-slate-200'}`}>
                        {LANG[v.variant] || v.variant}
                      </button>
                    ))}
                  </div>
                  <div className="mt-3 flex flex-wrap items-start gap-4">
                    <div className="max-w-md rounded-2xl rounded-tl-sm bg-emerald-950 border border-emerald-900 px-3.5 py-2.5 text-[13px] text-slate-100 whitespace-pre-wrap leading-relaxed">
                      {shown.text}
                    </div>
                    <div className="text-[11.5px] text-slate-500 space-y-1">
                      <div>Template <code className="text-slate-300">{shown.meta_name}</code> · {shown.meta_language}</div>
                      <div className={`inline-block px-2 py-0.5 rounded-full border text-[10.5px] font-semibold ${statusOf(shown.status).cls}`}>{statusOf(shown.status).label}</div>
                    </div>
                  </div>
                  {!readOnly && canSubmit && (
                    <button onClick={() => submit(t)} disabled={busy === t.purpose}
                      className="mt-3 inline-flex items-center gap-1.5 h-8 px-3 rounded-lg bg-emerald-600 text-white text-[12.5px] font-semibold hover:bg-emerald-500 cursor-pointer disabled:opacity-50">
                      <Icon name="send" className="text-[15px]" />{busy === t.purpose ? 'Submitting…' : `Submit to Meta (all ${t.variants.length} languages)`}
                    </button>
                  )}
                </div>
              )}
            </li>
          );
        })}
      </ul>
    </section>
  );
};
