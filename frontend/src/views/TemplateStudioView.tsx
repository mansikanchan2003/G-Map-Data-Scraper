import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  approveStudioDraft, editStudioDraft, fetchStudioDrafts, fetchStudioPerformance,
  fetchStudioRules, fetchStudioStates, fetchStudioStatus, generateStudioDrafts,
  rejectStudioDraft, requestNewPhoto,
} from '../api/whatsapp';
import type {
  StudioDraft, StudioPerformance, StudioPoster, StudioRules, StudioState,
} from '../api/whatsapp';
import { getApiBaseUrl } from '../api';
import { WhatsAppPreview } from '../components/WhatsAppPreview';
import { SheetTemplateBuilder } from '../components/SheetTemplateBuilder';

// Two ways to make a template. From a messages sheet: the team's own wording
// is read back into one template and submitted to Meta automatically. AI
// drafts: the agent writes, a person decides, and nothing reaches Meta except
// through the Approve button.

type Mode = 'sheet' | 'agent';
const MODE_KEY = 'autogmap-studio-mode';

const readMode = (): Mode => {
  try { return localStorage.getItem(MODE_KEY) === 'agent' ? 'agent' : 'sheet'; } catch { return 'sheet'; }
};

type Tab = 'review' | 'working' | 'approved' | 'rejected';

const TAB_STATUSES: Record<Tab, (s: string) => boolean> = {
  review: s => s === 'AWAITING_APPROVAL',
  working: s => s === 'GENERATING' || s === 'GENERATION_FAILED',
  approved: s => !['AWAITING_APPROVAL', 'GENERATING', 'GENERATION_FAILED', 'REJECTED_BY_REVIEWER'].includes(s),
  rejected: s => s === 'REJECTED_BY_REVIEWER',
};

const TAB_LABELS: Record<Tab, string> = {
  review: 'Awaiting approval',
  working: 'In progress / failed',
  approved: 'Approved',
  rejected: 'Rejected',
};

const mediaUrl = (headerContent: string | null) => {
  if (!headerContent) return null;
  try {
    const data = JSON.parse(headerContent);
    return data.media_id ? `${getApiBaseUrl()}/api/v1/whatsapp/media/${data.media_id}` : null;
  } catch {
    return null;
  }
};

const pct = (v: number | null) => (v == null ? '—' : `${(v * 100).toFixed(1)}%`);

// The poster fields a reviewer is most likely to reword, in reading order.
const POSTER_EDIT_FIELDS: { key: keyof StudioPoster; label: string }[] = [
  { key: 'headline_line1', label: 'Headline, line 1' },
  { key: 'headline_line2', label: 'Headline, line 2' },
  { key: 'headline_highlight', label: 'Highlighted phrase (from line 2)' },
  { key: 'subline', label: 'Sub-line' },
  { key: 'callout', label: 'Callout box' },
  { key: 'callout_highlight', label: 'Highlighted phrase (from callout)' },
  { key: 'benefits_title', label: 'Benefits title' },
  { key: 'cta', label: 'Apply button on poster' },
  { key: 'opportunity_title', label: 'Opportunity card title' },
  { key: 'opportunity_text', label: 'Opportunity card text' },
  { key: 'sign_title', label: 'Signboard: Customer Service Point' },
  { key: 'bank_name', label: 'Signboard: State Bank of India' },
  { key: 'phone_label', label: 'Footer: call label' },
  { key: 'web_label', label: 'Footer: website label' },
];

export const TemplateStudioView: React.FC = () => {
  const [mode, setModeState] = useState<Mode>(readMode);
  const setMode = (m: Mode) => {
    setModeState(m);
    try { localStorage.setItem(MODE_KEY, m); } catch { /* remembered only when storage allows */ }
  };
  const [ready, setReady] = useState<{ ready: boolean; error: string | null } | null>(null);
  const [states, setStates] = useState<StudioState[]>([]);
  const [rules, setRules] = useState<StudioRules | null>(null);
  const [drafts, setDrafts] = useState<StudioDraft[]>([]);
  const [performance, setPerformance] = useState<StudioPerformance[]>([]);
  const [tab, setTab] = useState<Tab>('review');
  const [showRules, setShowRules] = useState(false);

  const [state, setState] = useState('');
  const [count, setCount] = useState(2);
  const [brief, setBrief] = useState('');
  const [generating, setGenerating] = useState(false);
  const [notice, setNotice] = useState<{ kind: 'ok' | 'error'; text: string } | null>(null);

  const [zoom, setZoom] = useState<string | null>(null);
  const [editing, setEditing] = useState<StudioDraft | null>(null);
  const [approving, setApproving] = useState<StudioDraft | null>(null);
  const [rejecting, setRejecting] = useState<StudioDraft | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);

  const say = (kind: 'ok' | 'error', text: string) => {
    setNotice({ kind, text });
    setTimeout(() => setNotice(null), 8000);
  };

  const loadDrafts = useCallback(async () => {
    try { setDrafts(await fetchStudioDrafts()); } catch (e: any) { say('error', e.message); }
  }, []);

  useEffect(() => {
    fetchStudioStatus().then(setReady).catch(() => setReady({ ready: false, error: 'Could not reach the server' }));
    fetchStudioRules().then(setRules).catch(() => {});
    fetchStudioPerformance().then(setPerformance).catch(() => {});
    fetchStudioStates().then(list => {
      setStates(list);
      const first = list.find(s => s.language_code);
      if (first) setState(first.state);
    }).catch(() => {});
    loadDrafts();
  }, [loadDrafts]);

  // A round takes a minute or more per variant, so the page polls while
  // anything is still being made rather than asking the reviewer to refresh.
  const anyGenerating = drafts.some(d => d.status === 'GENERATING');
  useEffect(() => {
    if (!anyGenerating) return;
    const t = setInterval(loadDrafts, 5000);
    return () => clearInterval(t);
  }, [anyGenerating, loadDrafts]);

  const counts = useMemo(() => {
    const c = { review: 0, working: 0, approved: 0, rejected: 0 } as Record<Tab, number>;
    drafts.forEach(d => (Object.keys(TAB_STATUSES) as Tab[]).forEach(t => { if (TAB_STATUSES[t](d.status)) c[t]++; }));
    return c;
  }, [drafts]);

  const visible = drafts.filter(d => TAB_STATUSES[tab](d.status));
  const selectedState = states.find(s => s.state === state);

  const handleGenerate = async () => {
    if (!state) return;
    setGenerating(true);
    try {
      await generateStudioDrafts(state, count, brief);
      setBrief('');
      setTab('working');
      await loadDrafts();
      say('ok', `The agent is writing ${count} ${selectedState?.language || ''} variant(s) for ${state}. Each takes a minute or two.`);
    } catch (e: any) {
      say('error', e.message);
    } finally {
      setGenerating(false);
    }
  };

  const handleNewPhoto = async (d: StudioDraft) => {
    setBusyId(d.template_id);
    try {
      await requestNewPhoto(d.template_id);
      setTab('working');
      await loadDrafts();
    } catch (e: any) { say('error', e.message); } finally { setBusyId(null); }
  };

  return (
    <div className="flex-1 flex flex-col min-w-0 h-full bg-slate-950 text-slate-100 p-6 overflow-y-auto">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-semibold text-slate-100 tracking-tight">Template Studio</h1>
          <p className="text-xs text-slate-400 mt-0.5">
            {mode === 'sheet'
              ? 'Turn a sheet of written-out messages into one template. It goes to Meta automatically.'
              : "The agent writes templates in each state's language. Nothing is sent to Meta until you approve it."}
          </p>
        </div>
        {mode === 'agent' && <button
          onClick={() => setShowRules(v => !v)}
          className="h-8 px-3 bg-slate-800 hover:bg-slate-700 border border-slate-700 text-slate-200 text-xs font-mono-code font-semibold rounded flex items-center gap-1.5"
        >
          <span className="material-symbols-outlined text-[16px]">rule</span>
          {showRules ? 'Hide rules' : "Agent's rules"}
        </button>}
      </div>

      <div className="flex gap-1 mb-6 p-1 rounded-lg bg-slate-900 border border-slate-800 w-fit">
        {([['sheet', 'From a messages sheet', 'table_view'], ['agent', 'AI drafts', 'auto_awesome']] as const).map(([m, label, icon]) => (
          <button key={m} onClick={() => setMode(m)}
            className={`px-3 py-1.5 rounded text-xs font-semibold flex items-center gap-1.5 ${mode === m
              ? 'bg-sky-900/50 text-sky-300' : 'text-slate-400 hover:text-slate-200'}`}>
            <span className="material-symbols-outlined text-[16px]">{icon}</span>{label}
          </button>
        ))}
      </div>

      {mode === 'sheet' && <SheetTemplateBuilder />}

      {mode === 'agent' && <>

      {mode === 'agent' && ready && !ready.ready && (
        <div className="mb-4 p-3 rounded border border-amber-600/50 bg-amber-900/20 text-amber-200 text-sm">
          The agent cannot run yet: {ready.error} Drafts already made can still be reviewed.
        </div>
      )}
      {notice && (
        <div className={`mb-4 p-3 rounded border text-sm ${notice.kind === 'ok'
          ? 'border-emerald-600/50 bg-emerald-900/20 text-emerald-200'
          : 'border-rose-600/50 bg-rose-900/20 text-rose-200'}`}>{notice.text}</div>
      )}

      {mode === 'agent' && showRules && rules && (
        <div className="mb-6 grid md:grid-cols-3 gap-4 text-xs">
          {([['Image rules', rules.image_rules], ['Copy rules', rules.copy_rules], ['Facts it may claim', rules.facts]] as const).map(([title, items]) => (
            <div key={title} className="p-4 rounded-lg border border-slate-800 bg-slate-900">
              <div className="font-semibold text-slate-200 mb-2">{title}</div>
              <ul className="space-y-1.5 text-slate-400 list-disc pl-4">{items.map(i => <li key={i}>{i}</li>)}</ul>
            </div>
          ))}
        </div>
      )}

      {/* Generate */}
      <div className="mb-6 p-4 rounded-lg border border-slate-800 bg-slate-900 flex flex-wrap items-end gap-4">
        <label className="text-xs text-slate-400 flex flex-col gap-1">
          State
          <select value={state} onChange={e => setState(e.target.value)}
            className="h-9 px-2 bg-slate-950 border border-slate-700 rounded text-sm text-slate-100 min-w-[220px]">
            {states.map(s => (
              <option key={s.state} value={s.state} disabled={!s.language_code}>
                {s.state} — {s.language || 'no language set'}
              </option>
            ))}
          </select>
        </label>
        <label className="text-xs text-slate-400 flex flex-col gap-1">
          Variants
          <select value={count} onChange={e => setCount(Number(e.target.value))}
            className="h-9 px-2 bg-slate-950 border border-slate-700 rounded text-sm text-slate-100">
            {[1, 2, 3, 4].map(n => <option key={n} value={n}>{n}</option>)}
          </select>
        </label>
        <label className="text-xs text-slate-400 flex flex-col gap-1 flex-1 min-w-[260px]">
          What should this round try? (optional)
          <input value={brief} onChange={e => setBrief(e.target.value)} maxLength={1000}
            placeholder="e.g. focus on shopkeepers who already handle cash; a festive tone"
            className="h-9 px-3 bg-slate-950 border border-slate-700 rounded text-sm text-slate-100" />
        </label>
        <button onClick={handleGenerate} disabled={generating || !state || !ready?.ready}
          className="h-9 px-4 bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 text-white text-xs font-mono-code font-semibold rounded flex items-center gap-2">
          <span className="material-symbols-outlined text-[16px]">auto_awesome</span>
          {generating ? 'Starting...' : 'Generate drafts'}
        </button>
      </div>

      {/* Drafts */}
      <div className="flex gap-1 mb-4 border-b border-slate-800">
        {(Object.keys(TAB_LABELS) as Tab[]).map(t => (
          <button key={t} onClick={() => setTab(t)}
            className={`px-3 py-2 text-xs font-semibold border-b-2 -mb-px ${tab === t
              ? 'border-sky-500 text-sky-300' : 'border-transparent text-slate-400 hover:text-slate-200'}`}>
            {TAB_LABELS[t]} <span className="ml-1 text-slate-500">{counts[t]}</span>
          </button>
        ))}
      </div>

      {visible.length === 0 ? (
        <div className="text-sm text-slate-500 py-10 text-center">Nothing here yet.</div>
      ) : (
        <div className="grid xl:grid-cols-2 gap-5 mb-10">
          {visible.map(d => (
            <DraftCard key={d.template_id} draft={d} busy={busyId === d.template_id}
              onZoom={setZoom} onEdit={() => setEditing(d)} onApprove={() => setApproving(d)}
              onReject={() => setRejecting(d)} onNewPhoto={() => handleNewPhoto(d)} />
          ))}
        </div>
      )}

      <PerformanceTable rows={performance} />
      </>}

      {zoom && (
        <div onClick={() => setZoom(null)} className="fixed inset-0 z-50 bg-black/80 flex items-center justify-center p-6 cursor-zoom-out">
          <img src={zoom} alt="Poster" className="max-w-full max-h-full rounded shadow-2xl" />
        </div>
      )}
      {editing && (
        <EditModal draft={editing} onClose={() => setEditing(null)} onSaved={async (warnings) => {
          setEditing(null);
          await loadDrafts();
          say(warnings.length ? 'error' : 'ok', warnings.length
            ? `Saved, but the checker still flags: ${warnings.join('; ')}`
            : 'Saved and re-rendered.');
        }} />
      )}
      {approving && (
        <ApproveModal draft={approving} onClose={() => setApproving(null)} onDone={async (msg, ok) => {
          setApproving(null);
          await loadDrafts();
          fetchStudioPerformance().then(setPerformance).catch(() => {});
          say(ok ? 'ok' : 'error', msg);
        }} />
      )}
      {rejecting && (
        <RejectModal draft={rejecting} onClose={() => setRejecting(null)} onDone={async () => {
          setRejecting(null);
          await loadDrafts();
          say('ok', 'Rejected. The reason will steer the next round for this state.');
        }} />
      )}
    </div>
  );
};

// ---------------------------------------------------------------------------

const DraftCard: React.FC<{
  draft: StudioDraft; busy: boolean;
  onZoom: (url: string) => void; onEdit: () => void; onApprove: () => void;
  onReject: () => void; onNewPhoto: () => void;
}> = ({ draft, busy, onZoom, onEdit, onApprove, onReject, onNewPhoto }) => {
  const img = mediaUrl(draft.header_content);
  const gen = draft.generation || {};
  const check = gen.photo_check;
  const awaiting = draft.status === 'AWAITING_APPROVAL';

  return (
    <div className="rounded-lg border border-slate-800 bg-slate-900 overflow-hidden flex flex-col">
      {draft.status === 'GENERATING' ? (
        <div className="aspect-[3/2] flex flex-col items-center justify-center gap-3 bg-slate-950 text-slate-400 text-sm">
          <div className="w-7 h-7 border-2 border-sky-400 border-t-transparent rounded-full animate-spin" />
          Writing copy, taking the photo, setting the poster…
        </div>
      ) : img ? (
        <img src={img} alt="Poster" onClick={() => onZoom(img)} className="w-full aspect-[3/2] object-cover cursor-zoom-in bg-slate-950" />
      ) : (
        <div className="aspect-[3/2] flex items-center justify-center bg-slate-950 text-rose-300 text-sm px-6 text-center">
          {gen.error || 'No poster'}
        </div>
      )}

      <div className="p-4 flex flex-col gap-3 flex-1">
        <div className="flex flex-wrap items-center gap-2 text-[11px]">
          <span className="px-2 py-0.5 rounded bg-slate-800 text-slate-300">{draft.target_state}</span>
          <span className="px-2 py-0.5 rounded bg-slate-800 text-slate-300">{draft.language_code}</span>
          <span className="px-2 py-0.5 rounded bg-sky-900/40 text-sky-300">{draft.status.replace(/_/g, ' ')}</span>
          {check && (
            <span className={`px-2 py-0.5 rounded ${check.passed ? 'bg-emerald-900/40 text-emerald-300' : 'bg-amber-900/40 text-amber-300'}`}
              title={(check.issues || []).join('; ')}>
              {check.passed ? 'Photo check passed' : 'Photo check: needs a look'}
            </span>
          )}
        </div>

        {gen.angle && (
          <div className="text-sm text-slate-200">
            <span className="text-slate-500">Tests{gen.angle_key ? ` ${gen.angle_key.replace(/_/g, ' ')}` : ''}: </span>{gen.angle}
          </div>
        )}
        {check && !check.passed && (check.issues || []).length > 0 && (
          <div className="text-xs text-amber-300">Photo: {check.issues!.join('; ')}</div>
        )}
        {(gen.copy_warnings || []).length > 0 && (
          <div className="text-xs text-amber-300">Copy checker: {gen.copy_warnings!.join('; ')}</div>
        )}
        {gen.error && draft.status !== 'GENERATION_FAILED' && <div className="text-xs text-rose-300">{gen.error}</div>}
        {draft.review_note && (
          <div className="text-xs text-slate-400">
            {draft.status === 'REJECTED_BY_REVIEWER' ? 'Rejected' : 'Note'} by {draft.reviewed_by}: {draft.review_note}
          </div>
        )}
        {draft.meta_template_name && (
          <div className="text-xs text-slate-400">
            Submitted as <span className="font-mono-code">{draft.meta_template_name}</span> by {draft.reviewed_by}
          </div>
        )}

        {draft.body && (
          <details className="text-xs">
            <summary className="cursor-pointer text-slate-400 hover:text-slate-200">WhatsApp message</summary>
            <div className="mt-2 max-w-sm">
              <WhatsAppPreview businessName="" templateBody={draft.body} headerType={draft.header_type}
                headerContent={draft.header_content} footer={draft.footer} buttons={draft.buttons} />
            </div>
          </details>
        )}

        {awaiting && (
          <div className="flex flex-wrap gap-2 mt-auto pt-2">
            <button onClick={onApprove} className="h-8 px-3 bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-semibold rounded flex items-center gap-1">
              <span className="material-symbols-outlined text-[16px]">check</span>Approve &amp; submit
            </button>
            <button onClick={onEdit} className="h-8 px-3 bg-slate-800 hover:bg-slate-700 border border-slate-700 text-slate-200 text-xs font-semibold rounded">Edit text</button>
            <button onClick={onNewPhoto} disabled={busy} className="h-8 px-3 bg-slate-800 hover:bg-slate-700 border border-slate-700 text-slate-200 text-xs font-semibold rounded disabled:opacity-50">New photo</button>
            <button onClick={onReject} className="h-8 px-3 bg-rose-900/40 hover:bg-rose-900/60 border border-rose-800 text-rose-200 text-xs font-semibold rounded">Reject</button>
          </div>
        )}
        {draft.status === 'GENERATION_FAILED' && (
          <div className="flex gap-2 mt-auto pt-2">
            {/* The copy survived a photo failure, so the draft can be finished. */}
            {gen.poster && (
              <button onClick={onNewPhoto} disabled={busy} className="h-8 px-3 bg-sky-700 hover:bg-sky-600 text-white text-xs font-semibold rounded disabled:opacity-50">Retry photo</button>
            )}
            <button onClick={onReject} className="h-8 px-3 bg-slate-800 hover:bg-slate-700 border border-slate-700 text-slate-300 text-xs font-semibold rounded">Dismiss</button>
          </div>
        )}
      </div>
    </div>
  );
};

// ---------------------------------------------------------------------------

const Modal: React.FC<{ title: string; onClose: () => void; children: React.ReactNode; wide?: boolean }> = ({ title, onClose, children, wide }) => (
  <div className="fixed inset-0 z-50 bg-black/70 flex items-center justify-center p-4">
    <div className={`w-full ${wide ? 'max-w-3xl' : 'max-w-lg'} max-h-[90vh] overflow-y-auto rounded-lg border border-slate-700 bg-slate-900 p-5`}>
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-base font-semibold text-slate-100">{title}</h2>
        <button onClick={onClose} className="text-slate-400 hover:text-slate-200"><span className="material-symbols-outlined">close</span></button>
      </div>
      {children}
    </div>
  </div>
);

const inputCls = 'w-full px-3 py-2 bg-slate-950 border border-slate-700 rounded text-sm text-slate-100';

const EditModal: React.FC<{ draft: StudioDraft; onClose: () => void; onSaved: (warnings: string[]) => void }> = ({ draft, onClose, onSaved }) => {
  const poster = draft.generation?.poster;
  const buttons = draft.buttons || [];
  const [body, setBody] = useState(draft.body);
  const [footer, setFooter] = useState(draft.footer || '');
  const [apply, setApply] = useState(buttons.find(b => b.type === 'URL')?.text || '');
  const [callback, setCallback] = useState(buttons.find(b => b.type === 'QUICK_REPLY')?.text || '');
  const [fields, setFields] = useState<Partial<StudioPoster>>({ ...poster });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const save = async () => {
    setSaving(true);
    setError(null);
    const changedPoster: Partial<StudioPoster> = {};
    POSTER_EDIT_FIELDS.forEach(({ key }) => {
      if (poster && fields[key] !== poster[key]) (changedPoster as any)[key] = fields[key];
    });
    if (poster && JSON.stringify(fields.benefits) !== JSON.stringify(poster.benefits)) changedPoster.benefits = fields.benefits;
    try {
      const res = await editStudioDraft(draft.template_id, {
        body, footer, apply_button: apply, callback_button: callback,
        poster: Object.keys(changedPoster).length ? changedPoster : undefined,
      });
      onSaved(res.warnings);
    } catch (e: any) {
      setError(e.message);
      setSaving(false);
    }
  };

  return (
    <Modal title="Edit draft" onClose={onClose} wide>
      <div className="grid md:grid-cols-2 gap-5 text-xs text-slate-400">
        <div className="flex flex-col gap-3">
          <div className="font-semibold text-slate-200">WhatsApp message</div>
          <label>Body<textarea value={body} onChange={e => setBody(e.target.value)} rows={14} className={inputCls} /></label>
          <label>Footer<input value={footer} onChange={e => setFooter(e.target.value)} maxLength={60} className={inputCls} /></label>
          <label>Apply button<input value={apply} onChange={e => setApply(e.target.value)} maxLength={25} className={inputCls} /></label>
          <label>Call-back button<input value={callback} onChange={e => setCallback(e.target.value)} maxLength={25} className={inputCls} /></label>
        </div>
        {poster && (
          <div className="flex flex-col gap-3">
            <div className="font-semibold text-slate-200">Poster text</div>
            {POSTER_EDIT_FIELDS.map(({ key, label }) => (
              <label key={key}>{label}
                <input value={(fields[key] as string) || ''} className={inputCls}
                  onChange={e => setFields(f => ({ ...f, [key]: e.target.value }))} />
              </label>
            ))}
            {(fields.benefits || []).map((b, i) => (
              <label key={i}>Benefit {i + 1}
                <input value={b.text} className={inputCls} onChange={e => setFields(f => ({
                  ...f, benefits: (f.benefits || []).map((x, j) => j === i ? { ...x, text: e.target.value } : x),
                }))} />
              </label>
            ))}
          </div>
        )}
      </div>
      {error && <div className="mt-3 text-sm text-rose-300">{error}</div>}
      <div className="flex justify-end gap-2 mt-5">
        <button onClick={onClose} className="h-8 px-3 bg-slate-800 border border-slate-700 text-slate-200 text-xs rounded">Cancel</button>
        <button onClick={save} disabled={saving} className="h-8 px-4 bg-sky-600 hover:bg-sky-500 text-white text-xs font-semibold rounded disabled:opacity-50">
          {saving ? 'Saving and re-rendering...' : 'Save'}
        </button>
      </div>
    </Modal>
  );
};

const ApproveModal: React.FC<{ draft: StudioDraft; onClose: () => void; onDone: (msg: string, ok: boolean) => void }> = ({ draft, onClose, onDone }) => {
  const [category, setCategory] = useState('MARKETING');
  const [sending, setSending] = useState(false);

  const approve = async () => {
    setSending(true);
    try {
      const res = await approveStudioDraft(draft.template_id, category);
      onDone(res.status === 'success'
        ? `Submitted to Meta as ${res.draft.meta_template_name}. It can be used in a campaign once Meta approves it.`
        : `Meta did not accept the submission: ${res.error}. The draft is still awaiting approval.`, res.status === 'success');
    } catch (e: any) {
      onDone(e.message, false);
    }
  };

  return (
    <Modal title="Approve and submit to Meta" onClose={onClose}>
      <p className="text-sm text-slate-300 mb-4">
        This sends <span className="font-semibold">{draft.name}</span> ({draft.target_state}, {draft.language_code}) to Meta for review.
        Its language is fixed once Meta approves it.
      </p>
      <label className="text-xs text-slate-400 flex flex-col gap-1 mb-5">
        Category
        <select value={category} onChange={e => setCategory(e.target.value)} className="h-9 px-2 bg-slate-950 border border-slate-700 rounded text-sm text-slate-100">
          <option value="MARKETING">Marketing</option>
          <option value="UTILITY">Utility</option>
        </select>
      </label>
      <div className="flex justify-end gap-2">
        <button onClick={onClose} className="h-8 px-3 bg-slate-800 border border-slate-700 text-slate-200 text-xs rounded">Cancel</button>
        <button onClick={approve} disabled={sending} className="h-8 px-4 bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-semibold rounded disabled:opacity-50">
          {sending ? 'Submitting...' : 'Approve & submit'}
        </button>
      </div>
    </Modal>
  );
};

const RejectModal: React.FC<{ draft: StudioDraft; onClose: () => void; onDone: () => void }> = ({ draft, onClose, onDone }) => {
  const [reason, setReason] = useState('');
  const [error, setError] = useState<string | null>(null);
  const failed = draft.status === 'GENERATION_FAILED';

  const reject = async () => {
    try {
      await rejectStudioDraft(draft.template_id, reason || (failed ? 'Generation failed' : ''));
      onDone();
    } catch (e: any) {
      setError(e.message);
    }
  };

  return (
    <Modal title={failed ? 'Dismiss failed draft' : 'Reject draft'} onClose={onClose}>
      {!failed && (
        <>
          <p className="text-sm text-slate-300 mb-3">Say what is wrong. The agent reads this before writing the next round for {draft.target_state}.</p>
          <textarea value={reason} onChange={e => setReason(e.target.value)} rows={4} className={inputCls}
            placeholder="e.g. photo looks staged; headline promises too much; wrong word for 'kiosk'" />
        </>
      )}
      {error && <div className="mt-2 text-sm text-rose-300">{error}</div>}
      <div className="flex justify-end gap-2 mt-4">
        <button onClick={onClose} className="h-8 px-3 bg-slate-800 border border-slate-700 text-slate-200 text-xs rounded">Cancel</button>
        <button onClick={reject} disabled={!failed && reason.trim().length < 3}
          className="h-8 px-4 bg-rose-700 hover:bg-rose-600 text-white text-xs font-semibold rounded disabled:opacity-50">
          {failed ? 'Dismiss' : 'Reject'}
        </button>
      </div>
    </Modal>
  );
};

// ---------------------------------------------------------------------------

const PerformanceTable: React.FC<{ rows: StudioPerformance[] }> = ({ rows }) => (
  <div className="rounded-lg border border-slate-800 bg-slate-900">
    <div className="p-4 border-b border-slate-800">
      <div className="text-sm font-semibold text-slate-200">How templates are doing</div>
      <div className="text-xs text-slate-500 mt-0.5">
        What the agent learns from. Response = link visits + button taps, over delivered messages.
        "Not tracked" means Meta never reported delivery for that template, so its reads and taps are unknown.
      </div>
    </div>
    <div className="overflow-x-auto">
      <table className="w-full text-xs">
        <thead className="text-slate-500 text-left">
          <tr>{['Template', 'Made by', 'Language', 'Sent', 'Delivered', 'Read', 'Visits', 'Taps', 'Read rate', 'Response', 'By state'].map(h =>
            <th key={h} className="px-3 py-2 font-semibold whitespace-nowrap">{h}</th>)}</tr>
        </thead>
        <tbody>
          {rows.length === 0 && <tr><td colSpan={11} className="px-3 py-6 text-center text-slate-500">No campaigns yet.</td></tr>}
          {rows.map(r => (
            <tr key={r.template_id} className="border-t border-slate-800 text-slate-300">
              <td className="px-3 py-2">
                <div className="text-slate-200">{r.name}</div>
                {(r.angle_key || r.angle) && (
                  <div className="text-slate-500">{r.angle_key ? `${r.angle_key.replace(/_/g, ' ')} — ` : ''}{r.angle}</div>
                )}
              </td>
              <td className="px-3 py-2">{r.origin === 'agent' ? 'Agent' : 'Team'}</td>
              <td className="px-3 py-2">{r.language || '—'}</td>
              <td className="px-3 py-2">{r.sent}</td>
              <td className="px-3 py-2">{r.tracked ? r.delivered : <span className="text-slate-500">not tracked</span>}</td>
              <td className="px-3 py-2">{r.tracked ? r.read : '—'}</td>
              <td className="px-3 py-2">{r.visitors}</td>
              <td className="px-3 py-2">{r.tappers}</td>
              <td className="px-3 py-2">{pct(r.read_rate)}</td>
              <td className="px-3 py-2">{pct(r.response_rate)}</td>
              <td className="px-3 py-2 text-slate-500 whitespace-nowrap">
                {r.by_state.slice(0, 3).map(s => `${s.state} ${s.sent}`).join(' · ')}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  </div>
);
