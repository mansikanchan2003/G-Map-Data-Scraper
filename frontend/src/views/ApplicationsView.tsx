import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  fetchApplications, addApplicationComment, deleteApplicationComment, removeApplication,
  restoreApplication, documentUrl, type Application, type ApplicationStats,
} from '../api/applications';
import { formatDateTime } from '../utils/datetime';

type Filter = 'all' | 'pin' | 'strong' | 'not' | 'submitted';

const FILTERS: { key: Filter; label: string; hint: string; tone: string; pick: (a: Application) => boolean }[] = [
  { key: 'all', label: 'Total applications', hint: 'Started onboarding on WhatsApp', tone: 'text-slate-100', pick: () => true },
  { key: 'pin', label: 'PIN qualified', hint: 'PIN within our area', tone: 'text-sky-400', pick: a => a.pin_qualified },
  { key: 'strong', label: 'Strongly qualified', hint: 'PIN + 12th or above + can invest ₹5 lakh', tone: 'text-emerald-400', pick: a => a.strongly_qualified },
  { key: 'not', label: 'Not qualified', hint: 'Outside area, below 12th or cannot invest', tone: 'text-rose-400', pick: a => a.not_qualified },
  { key: 'submitted', label: 'Submitted', hint: 'Uploaded documents and submitted', tone: 'text-amber-400', pick: a => a.submitted },
];

const VERDICT_STYLE: Record<string, string> = {
  'Strongly qualified': 'bg-emerald-950/50 border-emerald-700 text-emerald-300',
  'PIN qualified': 'bg-sky-950/50 border-sky-700 text-sky-300',
  'Not qualified': 'bg-rose-950/50 border-rose-700 text-rose-300',
  'In progress': 'bg-slate-800 border-slate-700 text-slate-300',
};

const yesNo = (v: boolean | null | undefined) => (v === true ? 'Yes' : v === false ? 'No' : '—');

const csvCell = (v: unknown) => `"${String(v ?? '').replace(/"/g, '""')}"`;

/**
 * Everyone who started onboarding through the WhatsApp bot: how far they got,
 * whether they qualify, their documents, and the team's comments.
 */
export const ApplicationsView: React.FC<{ readOnly?: boolean }> = ({ readOnly }) => {
  const [items, setItems] = useState<Application[]>([]);
  const [stats, setStats] = useState<ApplicationStats | null>(null);
  const [showRemoved, setShowRemoved] = useState(false);
  const [filter, setFilter] = useState<Filter>('all');
  const [search, setSearch] = useState('');
  const [stage, setStage] = useState('');
  const [open, setOpen] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetchApplications(showRemoved);
      setItems(res.items);
      setStats(res.stats);
      setError(null);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [showRemoved]);

  useEffect(() => { load(); }, [load]);

  const leads = useMemo(() => items.filter(a => a.submitted)
    .sort((a, b) => (b.submitted_at || '').localeCompare(a.submitted_at || '')), [items]);
  // Opens the application at its comment history, with the box ready to type in.
  const [commentFocus, setCommentFocus] = useState<string | null>(null);
  const openComments = (phone: string) => { setOpen(phone); setCommentFocus(phone); };
  const openRow = (phone: string) => {
    setFilter('all'); setStage(''); setSearch(''); setOpen(phone);
    setTimeout(() => document.getElementById(`app-${phone}`)?.scrollIntoView({ behavior: 'smooth', block: 'center' }), 50);
  };

  const stages = useMemo(() => Array.from(new Set(items.map(a => a.stage))).sort(), [items]);
  const shown = useMemo(() => {
    const q = search.trim().toLowerCase();
    const pick = FILTERS.find(f => f.key === filter)!.pick;
    return items.filter(a => pick(a)
      && (!stage || a.stage === stage)
      && (!q || [a.name, a.phone, a.pincode, a.state, a.district, a.tehsil, a.category, a.source?.campaign].some(v => (v || '').toLowerCase().includes(q))));
  }, [items, filter, search, stage]);

  const exportCsv = () => {
    const head = ['Name', 'Phone', 'Category (persona)', 'PIN code', 'State', 'District', 'Tehsil', 'Qualification', 'Verdict', 'Not qualified because', 'Franchise background',
      'Can invest ₹5 lakh', 'Stage', 'Documents', 'Required documents', 'Submitted at', 'Campaign', 'Comments'];
    const rows = shown.map(a => [a.name, a.phone, a.category, a.pincode, a.state, a.district, a.tehsil, a.qualification, a.verdict, a.not_qualified_reasons.join('; '),
      yesNo(a.franchise_background), yesNo(a.can_invest), a.stage, `${a.documents_count}/${a.documents_total}`,
      a.required_documents_done ? 'Done' : 'Missing', a.submitted_at ? formatDateTime(a.submitted_at) : '',
      a.source?.campaign, a.comments.map(c => `${c.author}: ${c.body}`).join(' | ')]);
    const csv = [head, ...rows].map(r => r.map(csvCell).join(',')).join('\n');
    const url = URL.createObjectURL(new Blob(['﻿' + csv], { type: 'text/csv;charset=utf-8' }));
    const link = document.createElement('a');
    link.href = url;
    link.download = `applications-${new Date().toISOString().slice(0, 10)}.csv`;
    link.click();
    URL.revokeObjectURL(url);
  };

  const remove = async (a: Application) => {
    if (!confirm(`Remove ${a.name || a.phone} from Applications?\n\nThe WhatsApp chat and uploaded documents are kept, and it can be restored from "Removed".`)) return;
    try { await removeApplication(a.phone); await load(); } catch (e: any) { alert(e.message); }
  };
  const restore = async (a: Application) => {
    try { await restoreApplication(a.phone); await load(); } catch (e: any) { alert(e.message); }
  };

  const total = stats?.total || 0;
  const funnel = [
    { label: 'Applied', value: total },
    { label: 'PIN qualified', value: stats?.pin_qualified || 0 },
    { label: 'Strongly qualified', value: stats?.strongly_qualified || 0 },
    { label: 'Submitted', value: stats?.submitted || 0 },
  ];

  return (
    <div className="flex-1 overflow-y-auto bg-slate-950 text-slate-100">
      <div className="px-6 py-4 border-b border-slate-800 bg-slate-900 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Applications</h1>
          <p className="text-xs text-slate-400 mt-0.5">People who started CSP onboarding through the WhatsApp bot</p>
        </div>
        <div className="flex items-center gap-2">
          <button onClick={() => { setShowRemoved(v => !v); setOpen(null); }}
            className={`h-8 px-3 rounded border text-xs font-semibold ${showRemoved
              ? 'bg-amber-950/40 border-amber-700 text-amber-300' : 'bg-slate-800 border-slate-700 text-slate-300'}`}>
            {showRemoved ? '← Back to applications' : `Removed (${stats?.removed ?? 0})`}
          </button>
          <button onClick={load} className="h-8 px-3 rounded border border-slate-700 bg-slate-800 text-xs text-slate-200 flex items-center gap-1">
            <span className={`material-symbols-outlined text-[16px] ${loading ? 'animate-spin' : ''}`}>refresh</span> Refresh
          </button>
        </div>
      </div>

      <div className="p-4 lg:p-6 space-y-4">
        {error && <div className="p-3 rounded border border-rose-800 bg-rose-950/60 text-rose-200 text-sm">{error}</div>}

        {!showRemoved && <LeadsBlock leads={leads} onOpen={openRow} />}

        {!showRemoved && (
          <>
            {/* The five totals; each one filters the table. */}
            <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
              {FILTERS.map(f => {
                const value = f.key === 'all' ? stats?.total : f.key === 'pin' ? stats?.pin_qualified
                  : f.key === 'strong' ? stats?.strongly_qualified : f.key === 'not' ? stats?.not_qualified : stats?.submitted;
                return (
                  <button key={f.key} onClick={() => setFilter(f.key)}
                    className={`text-left p-3 rounded-lg border transition-colors ${filter === f.key
                      ? 'border-sky-600 bg-sky-950/30' : 'border-slate-800 bg-slate-900 hover:border-slate-600'}`}>
                    <div className={`text-2xl font-bold ${f.tone}`}>{value ?? '—'}</div>
                    <div className="text-xs font-semibold text-slate-200 mt-0.5">{f.label}</div>
                    <div className="text-[10.5px] text-slate-500 mt-0.5">{f.hint}</div>
                  </button>
                );
              })}
            </div>

            {/* How far people get. */}
            <div className="p-4 rounded-lg border border-slate-800 bg-slate-900">
              <div className="text-xs font-semibold text-slate-300 mb-3">Application funnel</div>
              <div className="space-y-2.5">
                {funnel.map(step => {
                  const pct = total ? Math.round((step.value / total) * 100) : 0;
                  return (
                    <div key={step.label}>
                      <div className="flex justify-between text-[11px] text-slate-400 mb-1">
                        <span>{step.label}</span><span>{step.value} · {pct}%</span>
                      </div>
                      <div className="h-2.5 rounded bg-slate-800 overflow-hidden">
                        <div className="h-full rounded bg-sky-600" style={{ width: `${pct}%` }} />
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          </>
        )}

        {/* Search, stage and export. */}
        <div className="flex flex-wrap items-center gap-2">
          <input value={search} onChange={e => setSearch(e.target.value)} placeholder="Search name, phone, PIN, area, category or campaign"
            className="flex-1 min-w-[220px] h-9 px-3 rounded border border-slate-700 bg-slate-900 text-sm text-slate-200 outline-none" />
          <select value={stage} onChange={e => setStage(e.target.value)}
            className="h-9 px-2 rounded border border-slate-700 bg-slate-900 text-sm text-slate-200">
            <option value="">All stages</option>
            {stages.map(s => <option key={s} value={s}>{s}</option>)}
          </select>
          <button onClick={exportCsv} disabled={!shown.length}
            className="h-9 px-3 rounded border border-emerald-700 bg-emerald-950/40 text-emerald-300 text-sm font-semibold disabled:opacity-40 flex items-center gap-1">
            <span className="material-symbols-outlined text-[16px]">download</span> Export CSV
          </button>
          <span className="text-xs text-slate-500">{shown.length} shown</span>
        </div>

        <div className="rounded-lg border border-slate-800 bg-slate-900 overflow-x-auto">
          <table className="w-full text-sm select-text">
            <thead className="bg-slate-950 text-[10.5px] uppercase tracking-wider text-slate-400">
              <tr>
                {['Name', 'Phone', 'Category (persona)', 'PIN code', 'State', 'District', 'Tehsil', 'Qualification', 'Verdict', 'Stage', 'Documents', 'Submitted', 'Comments', ''].map(h => (
                  <th key={h} className="px-3 py-2 text-left font-semibold whitespace-nowrap">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800">
              {loading && !items.length ? (
                <tr><td colSpan={14} className="px-3 py-10 text-center text-slate-500">Loading applications…</td></tr>
              ) : !shown.length ? (
                <tr><td colSpan={14} className="px-3 py-10 text-center text-slate-500">
                  {showRemoved ? 'No removed applications.' : 'No applications match.'}
                </td></tr>
              ) : shown.map(a => (
                <React.Fragment key={a.phone}>
                  <tr id={`app-${a.phone}`} className={`hover:bg-slate-800/40 ${open === a.phone ? 'bg-slate-800/40' : ''}`}>
                    <td className="px-3 py-2">
                      <div className="font-semibold text-slate-100">{a.name || '—'}</div>
                    </td>
                    <td className="px-3 py-2 font-mono text-xs text-slate-300 whitespace-nowrap">{a.phone}</td>
                    <td className="px-3 py-2 text-xs whitespace-nowrap">
                      {a.category
                        ? <span className="px-2 py-0.5 rounded bg-indigo-950/50 border border-indigo-800 text-indigo-200">{a.category}</span>
                        : <span className="text-slate-500" title="Not reached through a campaign from Business Data">—</span>}
                    </td>
                    <td className="px-3 py-2 font-mono text-xs text-slate-200 whitespace-nowrap">
                      {a.pincode || <span className="text-slate-500">—</span>}
                      {a.pincode_unchecked && (
                        <div className="font-sans text-[10px] text-amber-400/90" title="Typed in the chat, but the bot could not find it on the map and asked again">unchecked</div>
                      )}
                    </td>
                    <td className="px-3 py-2 text-xs text-slate-300 whitespace-nowrap">{a.state || '—'}</td>
                    <td className="px-3 py-2 text-xs text-slate-300 whitespace-nowrap">{a.district || '—'}</td>
                    <td className="px-3 py-2 text-xs text-slate-300 whitespace-nowrap">{a.tehsil || '—'}</td>
                    <td className="px-3 py-2 text-slate-300 whitespace-nowrap">{a.qualification || '—'}</td>
                    <td className="px-3 py-2">
                      <span className={`inline-block px-2 py-0.5 rounded border text-[11px] font-semibold whitespace-nowrap ${VERDICT_STYLE[a.verdict]}`}
                        title={a.not_qualified_reasons.join(', ') || undefined}>{a.verdict}</span>
                      {a.not_qualified && <div className="text-[10.5px] text-rose-300/80 mt-0.5">{a.not_qualified_reasons.join(', ')}</div>}
                    </td>
                    <td className="px-3 py-2 text-slate-300 text-xs">{a.stage}</td>
                    <td className="px-3 py-2 whitespace-nowrap">
                      <span className="text-slate-200">{a.documents_count}/{a.documents_total}</span>
                      <span className={`ml-1.5 text-[10.5px] ${a.required_documents_done ? 'text-emerald-400' : 'text-slate-500'}`}>
                        {a.required_documents_done ? '✓ required' : a.documents_count ? 'required missing' : ''}
                      </span>
                    </td>
                    <td className="px-3 py-2 text-xs whitespace-nowrap">
                      {a.submitted ? <span className="text-amber-300">{formatDateTime(a.submitted_at)}</span> : <span className="text-slate-500">—</span>}
                    </td>
                    <td className="px-3 py-2 text-xs text-slate-300 min-w-[200px] max-w-[260px]">
                      {a.comments.length ? (() => {
                        const last = a.comments[a.comments.length - 1];
                        return (
                          <button onClick={() => openComments(a.phone)} className="block w-full text-left" title={last.body}>
                            <span className="block truncate text-slate-200">{last.body}</span>
                            <span className="block text-[10.5px] text-slate-500">
                              {formatDateTime(last.created_at)} · {last.author}
                              {a.comments.length > 1 && <span className="text-sky-400"> · {a.comments.length} comments</span>}
                            </span>
                          </button>
                        );
                      })() : <span className="text-slate-500">—</span>}
                      {!readOnly && !showRemoved && (
                        <button onClick={() => openComments(a.phone)}
                          className="mt-1 text-[11px] font-semibold text-emerald-400 hover:text-emerald-300">+ Add comment</button>
                      )}
                    </td>
                    <td className="px-3 py-2 whitespace-nowrap text-right">
                      <button onClick={() => setOpen(open === a.phone ? null : a.phone)}
                        className="px-2 py-1 rounded border border-slate-700 text-xs text-sky-300 hover:bg-slate-800">
                        {open === a.phone ? 'Hide' : 'Details'}
                      </button>
                      {!readOnly && (showRemoved ? (
                        <button onClick={() => restore(a)} className="ml-1.5 px-2 py-1 rounded border border-emerald-800 text-xs text-emerald-300 hover:bg-emerald-950/40">Restore</button>
                      ) : (
                        <button onClick={() => remove(a)} title="Remove from Applications (the chat and documents are kept)"
                          className="ml-1.5 px-2 py-1 rounded border border-rose-900 text-xs text-rose-300 hover:bg-rose-950/40">Delete</button>
                      ))}
                    </td>
                  </tr>
                  {open === a.phone && (
                    <tr><td colSpan={14} className="px-3 pb-4 pt-1 bg-slate-950/60">
                      <ApplicationDetails app={a} readOnly={readOnly} onChanged={load}
                        focusComment={commentFocus === a.phone} onFocused={() => setCommentFocus(null)} />
                    </td></tr>
                  )}
                </React.Fragment>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};

/** Leads: everyone who has submitted their documents, newest first. */
const LeadsBlock: React.FC<{ leads: Application[]; onOpen: (phone: string) => void }> = ({ leads, onOpen }) => (
  <div className="rounded-lg border border-amber-700/70 bg-amber-950/20">
    <div className="px-4 py-3 border-b border-amber-800/50 flex flex-wrap items-center justify-between gap-2">
      <div className="flex items-center gap-2">
        <span className="material-symbols-outlined text-amber-400 text-[20px]">star</span>
        <h2 className="text-sm font-semibold text-amber-200">Leads</h2>
        <span className="px-2 py-0.5 rounded-full bg-amber-500/20 text-amber-300 text-xs font-bold">{leads.length}</span>
      </div>
      <span className="text-[11px] text-amber-200/70">People who have submitted their documents</span>
    </div>
    {leads.length === 0 ? (
      <div className="px-4 py-4 text-sm text-slate-400">No one has submitted their documents yet.</div>
    ) : (
      <div className="p-3 grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-2.5">
        {leads.map(a => (
          <div key={a.phone} className="p-3 rounded-lg border border-slate-800 bg-slate-900">
            <div className="flex items-start justify-between gap-2">
              <div className="min-w-0">
                <div className="font-semibold text-slate-100 truncate">{a.name || a.phone}</div>
                <div className="text-xs font-mono text-slate-400">{a.phone}</div>
              </div>
              <span className={`shrink-0 px-2 py-0.5 rounded border text-[10.5px] font-semibold ${VERDICT_STYLE[a.verdict]}`}>{a.verdict}</span>
            </div>
            <div className="mt-2 text-xs text-slate-300">
              {[a.pincode, a.tehsil, a.district, a.state].filter(Boolean).join(' · ') || 'No PIN'}
            </div>
            <div className="mt-1 flex flex-wrap gap-x-3 text-[11px] text-slate-400">
              <span>{a.qualification || '—'}</span>
              <span>Docs {a.documents_count}/{a.documents_total}{a.required_documents_done ? ' ✓' : ''}</span>
              <span>Submitted {formatDateTime(a.submitted_at)}</span>
            </div>
            <div className="mt-2.5 flex gap-2 text-xs">
              <button onClick={() => onOpen(a.phone)} className="px-2.5 py-1 rounded border border-slate-700 text-sky-300 hover:bg-slate-800">Details</button>
              <a href={`#inbox/${a.phone.replace(/\D/g, '')}`} className="px-2.5 py-1 rounded border border-slate-700 text-sky-300 hover:bg-slate-800">Open chat</a>
              {a.drive_folder_url && (
                <a href={a.drive_folder_url} target="_blank" rel="noreferrer" className="px-2.5 py-1 rounded border border-slate-700 text-sky-300 hover:bg-slate-800">Drive</a>
              )}
            </div>
          </div>
        ))}
      </div>
    )}
  </div>
);

const Field: React.FC<{ label: string; value: React.ReactNode }> = ({ label, value }) => (
  <div>
    <div className="text-[10px] uppercase tracking-wider text-slate-500">{label}</div>
    <div className="text-sm text-slate-200 mt-0.5">{value || '—'}</div>
  </div>
);

const ApplicationDetails: React.FC<{
  app: Application; readOnly?: boolean; onChanged: () => void; focusComment?: boolean; onFocused?: () => void;
}> = ({ app, readOnly, onChanged, focusComment, onFocused }) => {
  const [draft, setDraft] = useState('');
  const [saving, setSaving] = useState(false);
  const box = React.useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    if (!focusComment) return;
    box.current?.scrollIntoView({ behavior: 'smooth', block: 'center' });
    box.current?.focus();
    onFocused?.();
  }, [focusComment]);

  const add = async () => {
    if (!draft.trim()) return;
    setSaving(true);
    // The box empties and keeps focus, ready for the next comment.
    try { await addApplicationComment(app.phone, draft.trim()); setDraft(''); onChanged(); box.current?.focus(); }
    catch (e: any) { alert(e.message); }
    finally { setSaving(false); }
  };
  const drop = async (id: string) => {
    if (!confirm('Delete this comment?')) return;
    try { await deleteApplicationComment(id); onChanged(); } catch (e: any) { alert(e.message); }
  };

  return (
    <div className="space-y-4 pt-2">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 p-3 rounded border border-slate-800 bg-slate-900">
        <Field label="PIN code" value={app.pincode && [app.pincode, app.tehsil, app.district, app.state].filter(Boolean).join(' · ')} />
        <Field label="Nearest target PIN" value={app.place && `${app.place}${app.distance_km ? ` · ${app.distance_km} km away` : ''}`} />
        <Field label="Qualification" value={app.qualification} />
        <Field label="Franchise background" value={yesNo(app.franchise_background)} />
        <Field label="Can invest ₹5 lakh" value={yesNo(app.can_invest)} />
        <Field label="Campaign" value={app.source?.campaign} />
        <Field label="Business" value={app.source && [app.source.business_name, app.source.category, app.source.district].filter(Boolean).join(' · ')} />
        <Field label="Started" value={formatDateTime(app.started_at)} />
        <Field label="Last message" value={formatDateTime(app.last_message_at)} />
      </div>

      <div className="flex flex-wrap gap-2 text-xs">
        <a href={`#inbox/${app.phone.replace(/\D/g, '')}`} className="px-2.5 py-1.5 rounded border border-slate-700 text-sky-300 hover:bg-slate-800">Open chat in Inbox</a>
        {app.drive_folder_url && (
          <a href={app.drive_folder_url} target="_blank" rel="noreferrer" className="px-2.5 py-1.5 rounded border border-slate-700 text-sky-300 hover:bg-slate-800">Drive folder</a>
        )}
      </div>

      <div>
        <div className="text-xs font-semibold text-slate-300 mb-1.5">Documents ({app.documents_count}/{app.documents_total})</div>
        {app.documents.length ? (
          <ul className="space-y-1">
            {app.documents.map(d => (
              <li key={d.document_id} className="flex items-center justify-between gap-3 text-sm px-3 py-1.5 rounded bg-slate-900 border border-slate-800">
                <span className="text-slate-200 truncate">{d.label}{d.name && <span className="text-slate-500 text-xs"> · {d.name}</span>}</span>
                <a href={d.drive_url || documentUrl(d.document_id)} target="_blank" rel="noreferrer" className="text-xs text-sky-300 hover:underline shrink-0">Open</a>
              </li>
            ))}
          </ul>
        ) : <div className="text-sm text-slate-500">No documents uploaded yet.</div>}
      </div>

      <div>
        <div className="text-xs font-semibold text-slate-300 mb-1.5">
          Comment history {app.comments.length > 0 && <span className="text-slate-500 font-normal">({app.comments.length}, oldest first)</span>}
        </div>
        <ol className="space-y-1.5">
          {app.comments.map((c, i) => (
            <li key={c.comment_id} className="flex gap-2.5 px-3 py-2 rounded bg-slate-900 border border-slate-800 text-sm">
              <span className="shrink-0 h-5 w-5 rounded-full bg-slate-800 text-[10.5px] text-slate-300 flex items-center justify-center font-semibold">{i + 1}</span>
              <div className="flex-1 min-w-0">
                <div className="flex justify-between gap-2 text-[11px]">
                  <span><span className="text-sky-300 font-semibold">{formatDateTime(c.created_at)}</span>
                    <span className="text-slate-500"> · {c.author}</span></span>
                  {!readOnly && <button onClick={() => drop(c.comment_id)} className="text-rose-400 hover:text-rose-300">Delete</button>}
                </div>
                <div className="text-slate-200 whitespace-pre-wrap mt-0.5">{c.body}</div>
              </div>
            </li>
          ))}
          {!app.comments.length && <li className="text-sm text-slate-500">No comments yet.</li>}
        </ol>
        {!readOnly && (
          <div className="flex gap-2 mt-2">
            <textarea ref={box} value={draft} onChange={e => setDraft(e.target.value)} rows={2} maxLength={2000}
              onKeyDown={e => { if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) add(); }}
              placeholder={app.comments.length ? 'Add another comment, e.g. what happened on the call (Ctrl+Enter to save)'
                : 'Add a comment for the team (the applicant does not see it)'}
              className="flex-1 px-3 py-2 rounded border border-slate-700 bg-slate-900 text-sm text-slate-200 outline-none" />
            <button onClick={add} disabled={saving || !draft.trim()}
              className="self-end h-9 px-4 rounded bg-emerald-600 hover:bg-emerald-500 text-white text-sm font-semibold disabled:opacity-40">
              {saving ? 'Saving…' : app.comments.length ? 'Add another' : 'Add'}
            </button>
          </div>
        )}
      </div>
    </div>
  );
};
