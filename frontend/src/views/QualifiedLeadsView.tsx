import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  fetchQualifiedLeads, addApplicationComment, type QualifiedLead, type QualifiedStats,
} from '../api/applications';
import { formatDateTime } from '../utils/datetime';

/**
 * Everyone who ever reached Qualified or Strongly qualified, kept for good:
 * why, when, where, the nearest SBI branch (code, AO, region), where they
 * stand now, and the team's comments. Opened from the Applications tab.
 */

type Level = 'all' | 'Strongly qualified' | 'Qualified' | 'Not qualified for SBI branch code' | 'submitted' | 'dropped';

const Icon: React.FC<{ name: string; className?: string }> = ({ name, className = '' }) =>
  <span className={`material-symbols-outlined ${className}`}>{name}</span>;
const csvCell = (v: unknown) => `"${String(v ?? '').replace(/"/g, '""')}"`;
const place = (a: QualifiedLead) => [a.tehsil, a.district, a.state].filter(Boolean).join(', ');
const branchText = (a: QualifiedLead) => a.branch
  ? `${a.branch.code} ${a.branch.name || ''}`.trim() + (a.branch.distance_km != null ? ` · ${a.branch.distance_km} km` : '')
  : '';

const LEVEL_STYLE: Record<string, string> = {
  'Strongly qualified': 'bg-emerald-950 text-emerald-300 border-emerald-800/60',
  Qualified: 'bg-sky-950 text-sky-300 border-sky-800/60',
  'Not qualified for SBI branch code': 'bg-violet-950 text-violet-300 border-violet-800/60',
};

const Info: React.FC<{ icon: string; label: string; children: React.ReactNode }> = ({ icon, label, children }) => (
  <div className="min-w-0">
    <div className="flex items-center gap-1 text-[10.5px] uppercase tracking-wider text-slate-500">
      <Icon name={icon} className="text-[14px]" />{label}
    </div>
    <div className="text-[13px] text-slate-200 mt-0.5 break-words">{children || '—'}</div>
  </div>
);

const Comments: React.FC<{ lead: QualifiedLead; readOnly?: boolean; onChanged: () => void }> = ({ lead, readOnly, onChanged }) => {
  const [draft, setDraft] = useState('');
  const [saving, setSaving] = useState(false);
  const add = async () => {
    if (!draft.trim()) return;
    setSaving(true);
    try { await addApplicationComment(lead.phone, draft.trim()); setDraft(''); onChanged(); }
    catch (e: any) { alert(e.message); }
    finally { setSaving(false); }
  };
  return (
    <div>
      <div className="text-[10.5px] uppercase tracking-wider text-slate-500 mb-1.5">Comments ({lead.comments.length})</div>
      <ol className="space-y-1.5">
        {lead.comments.map(c => (
          <li key={c.comment_id} className="text-[12.5px] px-2.5 py-1.5 rounded-lg bg-slate-950 border border-slate-800">
            <span className="text-slate-400 text-[11px]">{c.author} · {formatDateTime(c.created_at)}</span>
            <div className="text-slate-200 whitespace-pre-wrap">{c.body}</div>
          </li>
        ))}
        {!lead.comments.length && <li className="text-[12.5px] text-slate-500">No comments yet.</li>}
      </ol>
      {!readOnly && (
        <div className="mt-2 flex gap-2">
          <input value={draft} onChange={e => setDraft(e.target.value)} maxLength={2000}
            onKeyDown={e => { if (e.key === 'Enter') add(); }}
            placeholder="Add a comment, e.g. what happened on the call"
            className="flex-1 min-w-0 h-8 px-2.5 rounded-lg border border-slate-800 bg-slate-950 text-[12.5px] text-slate-200 outline-none focus:border-sky-500" />
          <button onClick={add} disabled={saving || !draft.trim()}
            className="h-8 px-3 rounded-lg bg-emerald-500 text-white text-[12.5px] font-semibold disabled:opacity-40">
            {saving ? '…' : 'Add'}
          </button>
        </div>
      )}
    </div>
  );
};

const LeadCard: React.FC<{ lead: QualifiedLead; readOnly?: boolean; onChanged: () => void }> = ({ lead: a, readOnly, onChanged }) => (
  <div className="rounded-xl border border-slate-800 bg-slate-900 p-4 shadow-sm">
    <div className="flex flex-wrap items-start justify-between gap-3">
      <div className="min-w-0">
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-[15px] font-semibold text-slate-100">{a.name || a.phone}</span>
          <span className={`px-2 py-0.5 rounded-full border text-[11px] font-semibold ${LEVEL_STYLE[a.level]}`}>{a.level}</span>
          {a.submitted && <span className="px-2 py-0.5 rounded-full bg-emerald-500 text-white text-[11px] font-semibold">Documents submitted</span>}
          {a.removed && <span className="px-2 py-0.5 rounded-full bg-slate-800 text-slate-400 text-[11px]">Removed from Applications</span>}
        </div>
        <div className="text-[12.5px] text-slate-400 mt-0.5">{a.phone}{a.category ? ` · ${a.category}` : ''}{a.campaign ? ` · ${a.campaign}` : ''}</div>
      </div>
      <a href={`#inbox/${a.phone.replace(/\D/g, '')}`}
        className="h-8 px-3 rounded-lg bg-sky-600 text-white text-[12.5px] font-medium hover:opacity-90 flex items-center gap-1.5 shrink-0">
        <Icon name="chat" className="text-[16px]" />Open chat
      </a>
    </div>

    <div className={`mt-3 rounded-lg px-3 py-2 text-[12.5px] border ${a.still_qualified
      ? 'border-slate-800 bg-slate-950 text-slate-300' : 'border-amber-800/60 bg-amber-950 text-amber-300'}`}>
      <b className="font-semibold">Status:</b> {a.stage}{a.still_qualified ? '' : ` · ${a.now}`}
    </div>

    <div className="grid gap-4 mt-3 md:grid-cols-[1.1fr_1fr_1fr]">
      <div>
        <div className="text-[10.5px] uppercase tracking-wider text-slate-500 mb-1">Why {a.level.toLowerCase()}</div>
        <ul className="space-y-0.5">
          {a.why.map((w, i) => {
            const missing = w.includes('not answered');
            return (
              <li key={i} className={`flex gap-1.5 text-[13px] ${missing ? 'text-slate-500' : 'text-slate-200'}`}>
                <Icon name={missing ? 'radio_button_unchecked' : 'check_circle'}
                  className={`text-[16px] mt-px ${missing ? 'text-slate-600' : 'text-emerald-400'}`} />{w}
              </li>
            );
          })}
        </ul>
      </div>
      <div className="grid grid-cols-2 gap-3 content-start">
        <Info icon="call_received" label="Lead came in">{a.lead_at && formatDateTime(a.lead_at)}</Info>
        <Info icon="verified" label="Qualified on">{a.qualified_at && formatDateTime(a.qualified_at)}</Info>
        {a.strongly_qualified_at && <Info icon="workspace_premium" label="Strongly qualified on">{formatDateTime(a.strongly_qualified_at)}</Info>}
        {a.submitted_at && <Info icon="task_alt" label="Submitted on">{formatDateTime(a.submitted_at)}</Info>}
      </div>
      <div className="grid grid-cols-2 gap-3 content-start">
        <Info icon="pin_drop" label="PIN code">{a.pincode}</Info>
        <Info icon="map" label="Tehsil, district, state">{place(a)}</Info>
        <Info icon="account_balance" label="Nearest SBI branch">{branchText(a)}</Info>
        <Info icon="apartment" label="AO · Region">{a.branch && [a.branch.ao, a.branch.region && `RBO ${a.branch.region}`].filter(Boolean).join(' · ')}</Info>
      </div>
    </div>

    <div className="mt-4 pt-3 border-t border-slate-800">
      <Comments lead={a} readOnly={readOnly} onChanged={onChanged} />
    </div>
  </div>
);

export const QualifiedLeadsView: React.FC<{ readOnly?: boolean; onBack: () => void }> = ({ readOnly, onBack }) => {
  const [items, setItems] = useState<QualifiedLead[]>([]);
  const [stats, setStats] = useState<QualifiedStats | null>(null);
  const [level, setLevel] = useState<Level>('all');
  const [search, setSearch] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try { const r = await fetchQualifiedLeads(); setItems(r.items); setStats(r.stats); setError(null); }
    catch (e: any) { setError(e.message); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { load(); }, [load]);

  const shown = useMemo(() => {
    const q = search.trim().toLowerCase();
    return items.filter(a => (level === 'all' || (level === 'submitted' ? a.submitted : level === 'dropped' ? !a.still_qualified : a.level === level))
      && (!q || [a.name, a.phone, a.pincode, a.state, a.district, a.tehsil, a.branch?.code, a.branch?.name, a.branch?.ao, a.category]
        .some(v => (v || '').toLowerCase().includes(q))));
  }, [items, level, search]);

  const exportCsv = () => {
    const head = ['Name', 'Phone', 'Level', 'Why', 'Status', 'Lead came in', 'Qualified on', 'Strongly qualified on', 'Submitted on',
      'PIN code', 'Tehsil', 'District', 'State', 'Nearest SBI branch code', 'Branch name', 'AO', 'Region (RBO)', 'Distance (km)',
      'Category', 'Campaign', 'Comments'];
    const rows = shown.map(a => [a.name, a.phone, a.level, a.why.join('; '), a.still_qualified ? a.stage : `${a.stage} · ${a.now}`,
      a.lead_at && formatDateTime(a.lead_at), a.qualified_at && formatDateTime(a.qualified_at),
      a.strongly_qualified_at && formatDateTime(a.strongly_qualified_at), a.submitted_at && formatDateTime(a.submitted_at),
      a.pincode, a.tehsil, a.district, a.state, a.branch?.code, a.branch?.name, a.branch?.ao, a.branch?.region, a.branch?.distance_km,
      a.category, a.campaign, a.comments.map(c => `${formatDateTime(c.created_at)} ${c.author}: ${c.body}`).join(' | ')]);
    const csv = [head, ...rows].map(r => r.map(csvCell).join(',')).join('\n');
    const url = URL.createObjectURL(new Blob(['﻿' + csv], { type: 'text/csv;charset=utf-8' }));
    const link = document.createElement('a');
    link.href = url;
    link.download = `qualified-leads-${new Date().toISOString().slice(0, 10)}.csv`;
    link.click();
    URL.revokeObjectURL(url);
  };

  const tiles: { key: Level; label: string; value?: number; icon: string; tint: string }[] = [
    { key: 'all', label: 'All qualified', value: stats?.total, icon: 'groups', tint: 'bg-slate-800 text-slate-300' },
    { key: 'Strongly qualified', label: 'Strongly qualified', value: stats?.strongly_qualified, icon: 'workspace_premium', tint: 'bg-emerald-950 text-emerald-300' },
    { key: 'Qualified', label: 'Qualified', value: stats?.qualified, icon: 'verified', tint: 'bg-sky-950 text-sky-300' },
    { key: 'Not qualified for SBI branch code', label: 'Not qualified for SBI branch code', value: stats?.other_proposal, icon: 'swap_horiz', tint: 'bg-violet-950 text-violet-300' },
    { key: 'submitted', label: 'Documents submitted', value: stats?.submitted, icon: 'task_alt', tint: 'bg-emerald-950 text-emerald-300' },
    { key: 'dropped', label: 'Not qualified now', value: stats?.dropped, icon: 'trending_down', tint: 'bg-amber-950 text-amber-300' },
  ];

  return (
    <div className="flex-1 overflow-y-auto bg-slate-950 text-slate-100">
      <div className="px-4 sm:px-6 pt-6 pb-2 max-w-[1500px] mx-auto flex flex-wrap items-end justify-between gap-4">
        <div>
          <button onClick={onBack} className="text-[13px] text-sky-300 hover:underline flex items-center gap-1 mb-1">
            <Icon name="arrow_back" className="text-[16px]" />Applications
          </button>
          <h1 className="text-2xl font-semibold tracking-tight text-slate-100">Qualified leads</h1>
          <p className="text-sm text-slate-500 mt-1">Everyone who reached Qualified or Strongly qualified, kept even if they later answer otherwise; and those outside our SBI branch area, for another proposal (BT, HDFC…).</p>
        </div>
        <div className="flex items-center gap-2">
          <button onClick={exportCsv} disabled={!shown.length}
            className="h-9 px-3.5 rounded-lg border border-slate-800 bg-slate-900 hover:bg-slate-800 text-sm font-medium text-slate-300 flex items-center gap-1.5 shadow-sm disabled:opacity-40">
            <Icon name="download" className="text-[18px]" />Download CSV
          </button>
          <button onClick={load} className="h-9 px-3.5 rounded-lg border border-slate-800 bg-slate-900 hover:bg-slate-800 text-sm font-medium text-slate-300 flex items-center gap-1.5 shadow-sm">
            <Icon name="sync" className={`text-[18px] ${loading ? 'animate-spin' : ''}`} />Refresh
          </button>
        </div>
      </div>

      <div className="px-4 sm:px-6 py-4 max-w-[1500px] mx-auto space-y-4">
        {error && <div className="p-3 rounded-lg border border-rose-800/60 bg-rose-950 text-rose-300 text-sm">{error}</div>}
        <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-6 gap-3">
          {tiles.map(t => (
            <button key={t.key} onClick={() => setLevel(t.key)}
              className={`text-left p-3.5 rounded-xl border bg-slate-900 shadow-sm ${level === t.key ? 'border-transparent ring-2 ring-sky-500' : 'border-slate-800 hover:border-slate-700'}`}>
              <div className="flex items-center justify-between">
                <span className={`h-8 w-8 rounded-lg flex items-center justify-center ${t.tint}`}><Icon name={t.icon} className="text-[18px]" /></span>
                <span className="text-2xl font-bold tabular-nums text-slate-100">{t.value ?? '—'}</span>
              </div>
              <div className="text-[13px] font-semibold text-slate-100 mt-2">{t.label}</div>
            </button>
          ))}
        </div>
        <div className="relative max-w-md">
          <Icon name="search" className="absolute left-2.5 top-2 text-[18px] text-slate-500" />
          <input value={search} onChange={e => setSearch(e.target.value)} placeholder="Search name, phone, PIN, district, branch, AO…"
            className="w-full h-9 pl-9 pr-3 rounded-lg border border-slate-800 bg-slate-900 text-sm text-slate-200 outline-none focus:border-sky-500" />
        </div>
        <div className="space-y-3">
          {shown.map(a => <LeadCard key={a.phone} lead={a} readOnly={readOnly} onChanged={load} />)}
          {!loading && !shown.length && (
            <div className="p-8 text-center text-sm text-slate-500 rounded-xl border border-dashed border-slate-800">
              {items.length ? 'No qualified leads match this filter.' : 'No qualified leads yet.'}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
