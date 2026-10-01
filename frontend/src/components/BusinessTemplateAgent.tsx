import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  approveStudioDraft, editStudioDraft, fetchBusinessDrafts, fetchSheetSettings, fetchStudioStatus,
  rejectStudioDraft, stashAudience, writeBusinessDrafts,
} from '../api/whatsapp';
import type { SheetSettings, StudioDraft } from '../api/whatsapp';
import { LANGUAGES, readSheet } from './SheetTemplateBuilder';
import type { Sheet } from './SheetTemplateBuilder';
import { WhatsAppPreview } from './WhatsAppPreview';
import { formatDateTime } from '../utils/datetime';

// The agent writes templates for the businesses in an export, learning from
// how earlier templates did. A draft reaches Meta only when someone approves
// it here.

const STATUS: Record<string, { label: string; cls: string }> = {
  GENERATING: { label: 'Agent is writing…', cls: 'text-sky-300' },
  AWAITING_APPROVAL: { label: 'Awaiting your review', cls: 'text-amber-300' },
  GENERATION_FAILED: { label: 'Writing failed', cls: 'text-rose-300' },
  REJECTED_BY_REVIEWER: { label: 'Rejected by reviewer', cls: 'text-slate-400' },
  PENDING: { label: 'Approved — Meta is reviewing', cls: 'text-sky-300' },
  APPROVED: { label: 'Approved by Meta — ready to send', cls: 'text-emerald-300' },
  REJECTED: { label: 'Rejected by Meta', cls: 'text-rose-300' },
};
const statusOf = (s: string) => STATUS[s] || { label: s, cls: 'text-slate-300' };
const META_WAITING = (s: string) => !['GENERATING', 'AWAITING_APPROVAL', 'GENERATION_FAILED',
  'REJECTED_BY_REVIEWER', 'APPROVED', 'REJECTED', 'DISABLED'].includes(s);

const inputCls = 'h-9 px-2 bg-slate-950 border border-slate-700 rounded text-sm text-slate-100';
const btn = 'h-8 px-3 rounded text-xs font-mono-code font-semibold flex items-center gap-1.5 disabled:opacity-50';

/** The body with each blank shown as the first business would read it. */
const filled = (d: StudioDraft) => (d.body || '').replace(
  /\{\{([a-z][a-z0-9_]*)\}\}/g,
  (m, k) => (k === 'link' ? 'https://…/r/…' : d.generation?.examples?.[k] || m),
);

export const BusinessTemplateAgent: React.FC = () => {
  const [ready, setReady] = useState<{ ready: boolean; error: string | null } | null>(null);
  const [settings, setSettings] = useState<SheetSettings | null>(null);
  const [sheet, setSheet] = useState<Sheet | null>(null);
  const [count, setCount] = useState(2);
  const [brief, setBrief] = useState('');
  const [language, setLanguage] = useState('');
  const [linkTarget, setLinkTarget] = useState('');
  const [reading, setReading] = useState(false);
  const [starting, setStarting] = useState(false);
  const [notice, setNotice] = useState<{ kind: 'ok' | 'error'; text: string } | null>(null);
  const [drafts, setDrafts] = useState<StudioDraft[]>([]);

  const say = (kind: 'ok' | 'error', text: string) => {
    setNotice({ kind, text });
    setTimeout(() => setNotice(null), 10000);
  };

  const load = useCallback(async () => {
    try { setDrafts(await fetchBusinessDrafts()); } catch (e: any) { say('error', e.message); }
  }, []);

  useEffect(() => {
    fetchStudioStatus().then(setReady).catch(() => setReady({ ready: false, error: 'Could not reach the server.' }));
    fetchSheetSettings().then(s => { setSettings(s); setLinkTarget(s.default_link_target); }).catch(() => {});
    load();
  }, [load]);

  // Writing takes under a minute; Meta's review minutes to a day.
  const writing = drafts.some(d => d.status === 'GENERATING');
  const atMeta = drafts.some(d => META_WAITING(d.status));
  useEffect(() => {
    if (!writing && !atMeta) return;
    const t = setInterval(load, writing ? 4000 : 30000);
    return () => clearInterval(t);
  }, [writing, atMeta, load]);

  const handleFile = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    e.target.value = '';
    if (!file) return;
    setReading(true);
    try {
      setSheet(await readSheet(file));
    } catch (err: any) {
      setSheet(null);
      say('error', `Could not read the file: ${err.message}`);
    } finally {
      setReading(false);
    }
  };

  const summary = useMemo(() => {
    if (!sheet) return null;
    const col = (name: string) => sheet.headers.find(h => h.trim().toLowerCase() === name);
    const tally = (name: string) => {
      const h = col(name);
      const counts: Record<string, number> = {};
      if (h) sheet.rows.forEach(r => { if (r[h]) counts[r[h]] = (counts[r[h]] || 0) + 1; });
      return Object.entries(counts).sort((a, b) => b[1] - a[1]);
    };
    return { states: tally('state'), categories: tally('category'), hasName: !!col('name'), hasPhone: !!col('phone') };
  }, [sheet]);

  const write = async () => {
    if (!sheet) return;
    setStarting(true);
    try {
      await writeBusinessDrafts({
        rows: sheet.rows, count, brief: brief.trim() || null, language: language || null,
        link_target: linkTarget.trim() || undefined, source_name: sheet.fileName,
      });
      setBrief('');
      await load();
      say('ok', `The agent is writing ${count} template${count > 1 ? 's' : ''}. It reads every past template's results first; this takes under a minute.`);
    } catch (e: any) {
      say('error', e.message);
    } finally {
      setStarting(false);
    }
  };

  const startCampaign = (d: StudioDraft) => {
    if (sheet) {
      const nameCol = sheet.headers.find(h => h.toLowerCase() === 'name') || '';
      const phoneCol = sheet.headers.find(h => /phone|mobile/i.test(h)) || '';
      stashAudience({
        label: `${sheet.fileName} · ${sheet.rows.length.toLocaleString()} businesses`,
        template_id: d.template_id,
        needs_validation: true,
        contacts: sheet.rows.map(r => ({ phone: r[phoneCol], name: r[nameCol], variables: r })),
      });
    }
    window.location.hash = 'whatsapp-campaign';
  };

  return (
    <div className="space-y-6">
      {ready && !ready.ready && (
        <div className="p-3 rounded border border-amber-600/50 bg-amber-900/20 text-amber-200 text-sm">
          The agent cannot write yet: {ready.error} Drafts already written can still be reviewed.
        </div>
      )}
      {notice && (
        <div className={`p-3 rounded border text-sm ${notice.kind === 'ok'
          ? 'border-emerald-600/50 bg-emerald-900/20 text-emerald-200'
          : 'border-rose-600/50 bg-rose-900/20 text-rose-200'}`}>{notice.text}</div>
      )}

      <div className="p-4 rounded-lg border border-slate-800 bg-slate-900 space-y-4">
        <div className="text-sm text-slate-300">
          Upload businesses exported from <b>Business Data</b>. The agent writes templates addressed to each
          business, using their name and details as blanks, and learns from how every earlier template did.
          You review each draft; it goes to Meta only when you approve it.
        </div>

        <label className="flex flex-col items-center justify-center gap-1 p-6 border-2 border-dashed border-slate-700 rounded-lg cursor-pointer hover:border-slate-500">
          <input type="file" accept=".csv,.xlsx,.xls" className="hidden" onChange={handleFile} />
          <span className="material-symbols-outlined text-3xl text-slate-500">upload_file</span>
          <span className="text-sm font-semibold text-slate-300">
            {reading ? 'Reading…' : sheet ? `${sheet.fileName} — ${sheet.rows.length.toLocaleString()} businesses` : 'Choose a Business Data export (CSV or Excel)'}
          </span>
          {sheet && <span className="text-xs text-slate-500">Choose another file to replace it</span>}
        </label>

        {sheet && summary && (
          <>
            {!summary.hasName && (
              <div className="text-xs text-rose-300">This file has no “name” column, so it does not look like a Business Data export.</div>
            )}
            <div className="grid md:grid-cols-2 gap-3 text-xs text-slate-400">
              <div><span className="text-slate-500">States: </span>{summary.states.slice(0, 5).map(([s, n]) => `${s} (${n})`).join(', ') || '—'}</div>
              <div><span className="text-slate-500">Kinds of business: </span>{summary.categories.slice(0, 6).map(([s, n]) => `${s} (${n})`).join(', ') || '—'}</div>
            </div>

            <div className="flex flex-wrap items-end gap-4">
              <label className="text-xs text-slate-400 flex flex-col gap-1">
                Variants
                <select value={count} onChange={e => setCount(Number(e.target.value))} className={inputCls}>
                  {[1, 2, 3].map(n => <option key={n} value={n}>{n}</option>)}
                </select>
              </label>
              <label className="text-xs text-slate-400 flex flex-col gap-1">
                Language
                <select value={language} onChange={e => setLanguage(e.target.value)} className={inputCls}>
                  <option value="">From the businesses' state</option>
                  {LANGUAGES.map(l => <option key={l.code} value={l.code}>{l.label}</option>)}
                </select>
              </label>
              <label className="text-xs text-slate-400 flex flex-col gap-1 flex-1 min-w-[260px]">
                Anything this round should try? (optional)
                <input value={brief} onChange={e => setBrief(e.target.value)} maxLength={1000}
                  placeholder="e.g. lead with extra income for shopkeepers; a festive tone" className={`${inputCls} px-3`} />
              </label>
            </div>
            <label className="text-xs text-slate-400 flex flex-col gap-1">
              The tracked link in each message opens
              <input value={linkTarget} onChange={e => setLinkTarget(e.target.value)} className={`${inputCls} font-mono-code`} />
            </label>
            {settings && (
              <div className={`text-xs ${settings.tracking_enabled ? 'text-slate-400' : 'text-amber-300'}`}>
                {settings.tracking_enabled
                  ? 'The agent writes the link into the message. Each business gets its own, so every visit is recorded against it.'
                  : 'Visits cannot be tracked on this server yet: PUBLIC_BASE_URL is not set, so the link in the message opens the page directly and nobody’s visit is recorded.'}
              </div>
            )}

            <button onClick={write} disabled={starting || !ready?.ready || !summary.hasName}
              className="h-9 px-4 bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 text-white text-xs font-mono-code font-semibold rounded flex items-center gap-2">
              <span className="material-symbols-outlined text-[16px]">auto_awesome</span>
              {starting ? 'Starting…' : 'Write templates'}
            </button>
          </>
        )}
      </div>

      {drafts.length === 0 ? (
        <div className="text-sm text-slate-500 py-6 text-center">No templates written for business data yet.</div>
      ) : (
        <div className="grid xl:grid-cols-2 gap-5">
          {drafts.map(d => (
            <DraftCard key={d.template_id} draft={d} hasSheet={!!sheet} onChanged={load} say={say}
              onCampaign={() => startCampaign(d)} />
          ))}
        </div>
      )}
    </div>
  );
};

const DraftCard: React.FC<{
  draft: StudioDraft;
  hasSheet: boolean;
  onChanged: () => void;
  onCampaign: () => void;
  say: (kind: 'ok' | 'error', text: string) => void;
}> = ({ draft: d, hasSheet, onChanged, onCampaign, say }) => {
  const g = d.generation || {};
  const st = statusOf(d.status);
  const [mode, setMode] = useState<'view' | 'edit' | 'approve' | 'reject'>('view');
  const [busy, setBusy] = useState(false);
  const [body, setBody] = useState(d.body);
  const [footer, setFooter] = useState(d.footer || '');
  const callButton = (d.buttons || []).find(b => b.type === 'QUICK_REPLY');
  const [callLabel, setCallLabel] = useState(callButton?.text || '');
  const [category, setCategory] = useState('MARKETING');
  const [reason, setReason] = useState('');

  const act = async (fn: () => Promise<void>) => {
    setBusy(true);
    try { await fn(); } catch (e: any) { say('error', e.message); } finally { setBusy(false); }
  };

  const save = () => act(async () => {
    const out = await editStudioDraft(d.template_id, { body, footer, callback_button: callLabel });
    setMode('view');
    onChanged();
    say(out.warnings.length ? 'error' : 'ok', out.warnings.length
      ? `Saved, but the checker still flags: ${out.warnings.join('; ')}` : 'Saved.');
  });
  const approve = () => act(async () => {
    const out = await approveStudioDraft(d.template_id, category);
    setMode('view');
    onChanged();
    say(out.status === 'success' ? 'ok' : 'error', out.status === 'success'
      ? 'Approved and submitted to Meta. This page follows Meta’s review.'
      : `Meta refused the submission: ${out.error}`);
  });
  const reject = () => act(async () => {
    await rejectStudioDraft(d.template_id, reason);
    setMode('view');
    onChanged();
    say('ok', 'Rejected. The agent reads your reason before writing the next round.');
  });

  return (
    <div className="p-4 rounded-lg border border-slate-800 bg-slate-900 space-y-3">
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="text-sm font-semibold text-slate-100">{d.name}</div>
          <div className="text-xs text-slate-500">
            {d.target_state || 'Mixed states'} · {d.language_code} · {formatDateTime(d.created_at)}
            {g.audience ? ` · ${g.audience.rows.toLocaleString()} businesses` : ''}
          </div>
        </div>
        <div className={`text-xs font-semibold text-right ${st.cls}`}>{st.label}</div>
      </div>

      {d.status === 'GENERATING' && (
        <div className="py-8 flex items-center justify-center gap-3 text-sm text-slate-400">
          <div className="w-5 h-5 border-2 border-sky-400 border-t-transparent rounded-full animate-spin" />
          Reading past results and writing…
        </div>
      )}
      {d.status === 'GENERATION_FAILED' && <div className="text-sm text-rose-300">{g.error}</div>}

      {d.body && d.status !== 'GENERATING' && (
        <>
          {g.angle && <div className="text-xs text-slate-300"><span className="text-slate-500">Idea it tests: </span>{g.angle}</div>}
          {g.learned && (
            <div className="text-xs text-slate-300">
              <span className="text-slate-500">What it learned from: </span>{g.learned}
              {g.learned_from && (
                <span className="text-slate-500"> ({g.learned_from.templates} templates, {g.learned_from.sends.toLocaleString()} sends, {g.learned_from.with_responses} with responses)</span>
              )}
            </div>
          )}

          {mode === 'edit' ? (
            <div className="space-y-2">
              <textarea value={body} onChange={e => setBody(e.target.value)} rows={10}
                className="w-full p-2 bg-slate-950 border border-slate-700 rounded text-sm text-slate-100" />
              <div className="text-[11px] text-slate-500">
                Blanks you can use: {(g.allowed_fields || ['name']).map(f => `{{${f}}}`).join(', ')}, and {'{{link}}'} once for the tracked link (not as the last thing in the message)
              </div>
              <div className="flex flex-wrap gap-2">
                <input value={footer} onChange={e => setFooter(e.target.value)} placeholder="Footer" className={`${inputCls} flex-1`} />
                <input value={callLabel} onChange={e => setCallLabel(e.target.value)} placeholder="Call-back button" className={`${inputCls} w-40`} />
              </div>
              <div className="flex gap-2">
                <button onClick={save} disabled={busy} className={`${btn} bg-emerald-600 hover:bg-emerald-500 text-white`}>Save</button>
                <button onClick={() => setMode('view')} className={`${btn} bg-slate-800 text-slate-200`}>Cancel</button>
              </div>
            </div>
          ) : (
            <div className="grid md:grid-cols-[1fr_260px] gap-3">
              <pre className="whitespace-pre-wrap text-sm text-slate-100 bg-slate-950 border border-slate-800 rounded p-3 font-sans">{d.body}</pre>
              <WhatsAppPreview businessName={g.examples?.name || ''} templateBody={filled(d)}
                footer={d.footer} buttons={d.buttons} />
            </div>
          )}

          {(g.variables?.length ?? 0) > 0 && mode !== 'edit' && (
            <div className="text-xs text-slate-400">
              Filled per business: {g.variables!.map(v => `{{${v}}}`).join(', ')}
              {d.body.includes('{{link}}') && <> · {'{{link}}'} opens <span className="font-mono-code break-all">{g.link_target}</span>{g.tracked ? ', tracked per business' : ', untracked'}</>}
            </div>
          )}
          {(g.copy_warnings?.length ?? 0) > 0 && (
            <div className="text-xs text-amber-300">Checker notes: {g.copy_warnings!.join('; ')}</div>
          )}
          {d.status === 'REJECTED' && g.rejected_reason && (
            <div className="text-xs text-rose-300">Meta’s reason: {g.rejected_reason.replace(/_/g, ' ').toLowerCase()}</div>
          )}
          {d.status === 'REJECTED_BY_REVIEWER' && d.review_note && (
            <div className="text-xs text-slate-400">Your reason: {d.review_note}</div>
          )}
        </>
      )}

      {d.status === 'AWAITING_APPROVAL' && mode === 'approve' && (
        <div className="flex flex-wrap items-center gap-2">
          <select value={category} onChange={e => setCategory(e.target.value)} className={inputCls}>
            <option value="MARKETING">Marketing</option>
            <option value="UTILITY">Utility</option>
          </select>
          <button onClick={approve} disabled={busy} className={`${btn} bg-emerald-600 hover:bg-emerald-500 text-white`}>
            {busy ? 'Submitting…' : 'Approve and submit to Meta'}
          </button>
          <button onClick={() => setMode('view')} className={`${btn} bg-slate-800 text-slate-200`}>Cancel</button>
        </div>
      )}
      {d.status === 'AWAITING_APPROVAL' && mode === 'reject' && (
        <div className="flex flex-wrap items-center gap-2">
          <input value={reason} onChange={e => setReason(e.target.value)} placeholder="Why? The agent reads this next round."
            className={`${inputCls} flex-1 min-w-[240px] px-3`} />
          <button onClick={reject} disabled={busy || reason.trim().length < 3} className={`${btn} bg-rose-700 hover:bg-rose-600 text-white`}>Reject</button>
          <button onClick={() => setMode('view')} className={`${btn} bg-slate-800 text-slate-200`}>Cancel</button>
        </div>
      )}
      {d.status === 'AWAITING_APPROVAL' && mode === 'view' && (
        <div className="flex flex-wrap gap-2">
          <button onClick={() => setMode('approve')} className={`${btn} bg-emerald-600 hover:bg-emerald-500 text-white`}>
            <span className="material-symbols-outlined text-[16px]">check</span>Approve
          </button>
          <button onClick={() => setMode('edit')} className={`${btn} bg-slate-800 hover:bg-slate-700 border border-slate-700 text-slate-200`}>
            <span className="material-symbols-outlined text-[16px]">edit</span>Edit text
          </button>
          <button onClick={() => setMode('reject')} className={`${btn} bg-slate-800 hover:bg-slate-700 border border-slate-700 text-rose-300`}>
            <span className="material-symbols-outlined text-[16px]">close</span>Reject
          </button>
        </div>
      )}
      {d.status === 'APPROVED' && (
        <button onClick={onCampaign} className={`${btn} bg-sky-600 hover:bg-sky-500 text-white`}>
          <span className="material-symbols-outlined text-[16px]">campaign</span>
          {hasSheet ? 'Start a campaign with these businesses' : 'Use in a campaign'}
        </button>
      )}
    </div>
  );
};
