import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  fetchSheetSettings, fetchSheetTemplates, stashAudience, templateFromMessages,
} from '../api/whatsapp';
import type { FromMessagesResult, SheetOutcome, SheetSettings, SheetTemplate } from '../api/whatsapp';
import { WhatsAppPreview } from './WhatsAppPreview';
import { formatDateTime } from '../utils/datetime';

// A sheet of messages the team already wrote, one per person, turned back into
// the one template they share. The wording is the team's own, so it goes to
// Meta straight away; this page then follows Meta's review until it is ready.

export const LANGUAGES: { code: string; label: string }[] = [
  { code: 'en_US', label: 'English (US)' },
  { code: 'en', label: 'English' },
  { code: 'hi', label: 'Hindi' },
  { code: 'mr', label: 'Marathi' },
  { code: 'pa', label: 'Punjabi' },
  { code: 'gu', label: 'Gujarati' },
  { code: 'bn', label: 'Bengali' },
  { code: 'ta', label: 'Tamil' },
  { code: 'te', label: 'Telugu' },
  { code: 'kn', label: 'Kannada' },
  { code: 'ml', label: 'Malayalam' },
];

// Unicode block per script, for guessing the language from the messages.
// Devanagari is Hindi or Marathi; Hindi is the guess and can be changed.
const SCRIPTS: [string, RegExp][] = [
  ['hi', /[ऀ-ॿ]/g], ['pa', /[਀-੿]/g], ['gu', /[઀-૿]/g],
  ['bn', /[ঀ-৿]/g], ['ta', /[஀-௿]/g], ['te', /[ఀ-౿]/g],
  ['kn', /[ಀ-೿]/g], ['ml', /[ഀ-ൿ]/g],
];

const guessLanguage = (text: string) => {
  let best = 'en_US';
  let most = 0;
  for (const [code, re] of SCRIPTS) {
    const n = (text.match(re) || []).length;
    if (n > most) { most = n; best = code; }
  }
  return best;
};

export const guessColumn = (headers: string[], words: string[]) =>
  headers.find(h => words.some(w => h.toLowerCase().includes(w))) || '';

const OUTCOME: Record<SheetOutcome, { label: string; cls: string; icon: string }> = {
  ready: { label: 'Approved — ready to send', cls: 'border-emerald-600/50 bg-emerald-900/20 text-emerald-200', icon: 'check_circle' },
  created: { label: 'Submitted to Meta — waiting for review', cls: 'border-sky-600/50 bg-sky-900/20 text-sky-200', icon: 'schedule' },
  pending: { label: 'Waiting for Meta’s review', cls: 'border-sky-600/50 bg-sky-900/20 text-sky-200', icon: 'schedule' },
  rejected: { label: 'Rejected by Meta', cls: 'border-rose-600/50 bg-rose-900/20 text-rose-200', icon: 'block' },
  failed: { label: 'Could not submit to Meta', cls: 'border-rose-600/50 bg-rose-900/20 text-rose-200', icon: 'error' },
};

const isWaiting = (o: SheetOutcome) => o === 'pending' || o === 'created';

const inputCls = 'h-9 px-2 bg-slate-950 border border-slate-700 rounded text-sm text-slate-100';

export interface Sheet {
  fileName: string;
  headers: string[];
  rows: Record<string, string>[];
}

/** Reads a CSV or Excel file as the text each cell shows, phone column aside. */
export const readSheet = async (file: File): Promise<Sheet> => {
  const XLSX = await import('xlsx');
  const data = await file.arrayBuffer();
  const wb = XLSX.read(data, { type: 'array' });
  const ws = wb.Sheets[wb.SheetNames[0]];
  // As displayed, so a date or an amount reads the way it was written into
  // the message ("05/10/2026", "1,500") rather than as Excel's raw number.
  const shown = XLSX.utils.sheet_to_json(ws, { header: 1, raw: false, defval: '' }) as string[][];
  // Raw, for phone numbers: a 12-digit number displays as 9.19877E+11.
  const raw = XLSX.utils.sheet_to_json(ws, { header: 1, raw: true, defval: '' }) as any[][];
  if (shown.length < 2) throw new Error('The sheet has no rows under its header.');

  const headers = shown[0].map((h, i) => String(h || '').trim() || `Column ${i + 1}`);
  const rows = shown.slice(1)
    .map((cells, r) => {
      const row: Record<string, string> = {};
      headers.forEach((h, i) => {
        const rawCell = raw[r + 1]?.[i];
        row[h] = typeof rawCell === 'number' && /phone|mobile|number|whatsapp|contact/i.test(h)
          ? String(Math.round(rawCell))
          : String(cells[i] ?? '').trim();
      });
      return row;
    })
    .filter(row => Object.values(row).some(v => v !== ''));
  return { fileName: file.name, headers, rows };
};

export const SheetTemplateBuilder: React.FC = () => {
  const [settings, setSettings] = useState<SheetSettings | null>(null);
  const [sheet, setSheet] = useState<Sheet | null>(null);
  const [messageCol, setMessageCol] = useState('');
  const [phoneCol, setPhoneCol] = useState('');
  const [category, setCategory] = useState<'MARKETING' | 'UTILITY'>('MARKETING');
  const [language, setLanguage] = useState('en_US');
  const [linkTarget, setLinkTarget] = useState('');

  const [reading, setReading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<FromMessagesResult | null>(null);
  const [history, setHistory] = useState<SheetTemplate[]>([]);

  const loadHistory = useCallback(async () => {
    try {
      const list = await fetchSheetTemplates();
      setHistory(list);
      // Keep the open result in step with Meta's review as it moves.
      setResult(r => {
        if (!r?.template) return r;
        const now = list.find(t => t.template_id === r.template!.template_id);
        return now ? { ...r, action: now.outcome, reason: now.reason, template: now } : r;
      });
    } catch {
      // The list is a convenience; the form still works without it.
    }
  }, []);

  useEffect(() => {
    fetchSheetSettings().then(s => {
      setSettings(s);
      setLinkTarget(s.default_link_target);
    }).catch(() => {});
    loadHistory();
  }, [loadHistory]);

  // Meta reviews in minutes to about a day. The page checks while anything is
  // waiting, so nobody has to come back and press a button.
  const anyWaiting = history.some(t => isWaiting(t.outcome));
  useEffect(() => {
    if (!anyWaiting) return;
    const t = setInterval(loadHistory, 30000);
    return () => clearInterval(t);
  }, [anyWaiting, loadHistory]);

  const handleFile = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    e.target.value = '';
    if (!file) return;
    setReading(true);
    setError(null);
    setResult(null);
    try {
      const s = await readSheet(file);
      setSheet(s);
      const msg = guessColumn(s.headers, ['message', 'msg', 'text', 'content', 'sms']);
      const phone = guessColumn(s.headers, ['phone', 'mobile', 'whatsapp', 'number', 'contact']);
      setMessageCol(msg);
      setPhoneCol(phone);
      if (msg) setLanguage(guessLanguage(s.rows.slice(0, 20).map(r => r[msg]).join(' ')));
    } catch (err: any) {
      setSheet(null);
      setError(`Could not read the file: ${err.message}`);
    } finally {
      setReading(false);
    }
  };

  const submit = async () => {
    if (!sheet || !messageCol || !phoneCol) return;
    setBusy(true);
    setError(null);
    try {
      const out = await templateFromMessages({
        rows: sheet.rows,
        message_column: messageCol,
        phone_column: phoneCol,
        category,
        language,
        source_name: sheet.fileName,
        add_button: false,
        link_target: linkTarget.trim() || undefined,
      });
      setResult(out);
      loadHistory();
    } catch (err: any) {
      setResult(null);
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  const startCampaign = (t: SheetTemplate) => {
    if (!sheet) return;
    const nameCol = guessColumn(sheet.headers.filter(h => h !== messageCol && h !== phoneCol), ['name']);
    stashAudience({
      label: `${sheet.fileName} · ${sheet.rows.length.toLocaleString()} rows`,
      template_id: t.template_id,
      needs_validation: true,
      contacts: sheet.rows.map(row => {
        const variables: Record<string, string> = {};
        sheet.headers.forEach(h => { if (h !== messageCol && h !== phoneCol) variables[h] = row[h]; });
        return { phone: row[phoneCol], name: nameCol ? row[nameCol] : '', variables };
      }),
    });
    window.location.hash = 'whatsapp-campaign';
  };

  const template = result?.template || null;
  const outcome = result ? OUTCOME[result.action] : null;

  // The first row's values in place of the placeholders, as the first
  // recipient would read it.
  const previewBody = useMemo(() => {
    if (!template) return '';
    return template.body
      .replace(/\{\{link\}\}/g, 'https://…/r/…')
      .replace(/\{\{([a-z][a-z0-9_]*)\}\}/g, (m, k) => template.examples[k] || m);
  }, [template]);

  const ready = sheet && messageCol && phoneCol && messageCol !== phoneCol;

  return (
    <div className="space-y-6">
      <div className="p-4 rounded-lg border border-slate-800 bg-slate-900 space-y-4">
        <div className="text-sm text-slate-300">
          Upload a sheet with each person's phone number and the full message they should get.
          The template is worked out from what changes between rows, submitted to Meta
          automatically, and checked until Meta approves it.
        </div>

        <label className="flex flex-col items-center justify-center gap-1 p-6 border-2 border-dashed border-slate-700 rounded-lg cursor-pointer hover:border-slate-500">
          <input type="file" accept=".csv,.xlsx,.xls" className="hidden" onChange={handleFile} />
          <span className="material-symbols-outlined text-3xl text-slate-500">upload_file</span>
          <span className="text-sm font-semibold text-slate-300">
            {reading ? 'Reading…' : sheet ? `${sheet.fileName} — ${sheet.rows.length.toLocaleString()} rows` : 'Choose a CSV or Excel file'}
          </span>
          {sheet && <span className="text-xs text-slate-500">Choose another file to replace it</span>}
        </label>

        {sheet && (
          <>
            <div className="flex flex-wrap items-end gap-4">
              <label className="text-xs text-slate-400 flex flex-col gap-1">
                Message column
                <select value={messageCol} onChange={e => setMessageCol(e.target.value)} className={`${inputCls} min-w-[180px]`}>
                  <option value="">Choose…</option>
                  {sheet.headers.map(h => <option key={h} value={h}>{h}</option>)}
                </select>
              </label>
              <label className="text-xs text-slate-400 flex flex-col gap-1">
                Phone column
                <select value={phoneCol} onChange={e => setPhoneCol(e.target.value)} className={`${inputCls} min-w-[180px]`}>
                  <option value="">Choose…</option>
                  {sheet.headers.map(h => <option key={h} value={h}>{h}</option>)}
                </select>
              </label>
              <label className="text-xs text-slate-400 flex flex-col gap-1">
                Category
                <select value={category} onChange={e => setCategory(e.target.value as any)} className={inputCls}>
                  <option value="MARKETING">Marketing — offers, outreach</option>
                  <option value="UTILITY">Utility — updates people asked for</option>
                </select>
              </label>
              <label className="text-xs text-slate-400 flex flex-col gap-1">
                Language
                <select value={language} onChange={e => setLanguage(e.target.value)} className={inputCls}>
                  {LANGUAGES.map(l => <option key={l.code} value={l.code}>{l.label}</option>)}
                </select>
              </label>
            </div>

            <div className="p-3 rounded border border-slate-800 bg-slate-950 space-y-3">
              <div className="text-sm text-slate-200">Tracked link in the message</div>
              <label className="text-xs text-slate-400 flex flex-col gap-1">
                Visitors land on
                <input value={linkTarget} onChange={e => setLinkTarget(e.target.value)} className={`${inputCls} font-mono-code`} />
              </label>
              {settings && (
                <div className={`text-xs ${settings.tracking_enabled ? 'text-slate-400' : 'text-amber-300'}`}>
                  {settings.tracking_enabled
                    ? 'Write a kiosk.eko.in link in the messages. It becomes each person’s own tracked link, so every visit is recorded against them and shown in Campaign History, and they land on the page above.'
                    : 'Visits cannot be tracked on this server yet: PUBLIC_BASE_URL is not set, so the link in the message opens the page directly and nobody’s visit is recorded.'}
                </div>
              )}
            </div>

            <button onClick={submit} disabled={!ready || busy}
              className="h-9 px-4 bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 text-white text-xs font-mono-code font-semibold rounded flex items-center gap-2">
              <span className="material-symbols-outlined text-[16px]">auto_fix_high</span>
              {busy ? 'Working…' : 'Make the template'}
            </button>
          </>
        )}

        {error && (
          <div className="p-3 rounded border border-rose-600/50 bg-rose-900/20 text-rose-200 text-sm whitespace-pre-line">{error}</div>
        )}
      </div>

      {result && template && outcome && (
        <div className="grid lg:grid-cols-[1fr_340px] gap-5">
          <div className="p-4 rounded-lg border border-slate-800 bg-slate-900 space-y-4">
            <div className={`p-3 rounded border text-sm flex items-start gap-2 ${outcome.cls}`}>
              <span className="material-symbols-outlined text-[18px]">{outcome.icon}</span>
              <div>
                <div className="font-semibold">{outcome.label}</div>
                {result.reason && <div className="mt-1">{result.reason}</div>}
                {isWaiting(result.action) && (
                  <div className="mt-1 text-xs opacity-80">This page checks with Meta every minute; it usually takes minutes, at most about a day.</div>
                )}
              </div>
            </div>

            <div>
              <div className="text-xs text-slate-400 mb-1">Template · {template.meta_template_name || 'not registered'} · {template.language_code} · {template.category}</div>
              <pre className="whitespace-pre-wrap text-sm text-slate-100 bg-slate-950 border border-slate-800 rounded p-3 font-sans">{template.body}</pre>
            </div>

            {template.variables.length > 0 ? (
              <table className="w-full text-xs">
                <thead className="text-slate-500 text-left">
                  <tr><th className="py-1">Placeholder</th><th>Filled from column</th><th>First row</th></tr>
                </thead>
                <tbody className="text-slate-300">
                  {template.variables.map(k => (
                    <tr key={k} className="border-t border-slate-800">
                      <td className="py-1 font-mono-code text-sky-300">{`{{${k}}}`}</td>
                      <td>{template.columns[k]}</td>
                      <td className="text-slate-400">{template.examples[k]}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : (
              <div className="text-xs text-slate-400">Every row has the same message, so nothing is filled in per person.</div>
            )}

            {template.body.includes('{{link}}') ? (
              <div className="text-xs text-slate-400">
                <span className="font-mono-code text-sky-300">{'{{link}}'}</span> is each person’s own link, opening{' '}
                <span className="font-mono-code text-slate-300 break-all">{template.link_target}</span>
                {template.tracked ? ' — every visit is recorded against them.' : ' directly, without tracking.'}
              </div>
            ) : (
              <div className="text-xs text-amber-300">
                No kiosk.eko.in link was found in the messages, so visits from this template cannot be tracked.
                Add the link to the message text and make the template again.
              </div>
            )}

            <div className="flex flex-wrap gap-2">
              {result.action === 'ready' && (
                <button onClick={() => startCampaign(template)}
                  className="h-9 px-4 bg-sky-600 hover:bg-sky-500 text-white text-xs font-mono-code font-semibold rounded flex items-center gap-2">
                  <span className="material-symbols-outlined text-[16px]">campaign</span>
                  Start a campaign with this sheet
                </button>
              )}
              {result.action !== 'ready' && (
                <button onClick={submit} disabled={busy}
                  className="h-9 px-4 bg-slate-800 hover:bg-slate-700 border border-slate-700 text-slate-200 text-xs font-mono-code font-semibold rounded">
                  {busy ? 'Checking…' : 'Check now'}
                </button>
              )}
            </div>
          </div>

          <WhatsAppPreview businessName={template.examples.name || ''} templateBody={previewBody}
            buttons={template.buttons} />
        </div>
      )}

      {history.length > 0 && (
        <div className="p-4 rounded-lg border border-slate-800 bg-slate-900">
          <div className="text-sm font-semibold text-slate-200 mb-3">Templates made from sheets</div>
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead className="text-slate-500 text-left">
                <tr><th className="py-1 pr-3">Name</th><th className="pr-3">Status</th><th className="pr-3">Rows</th><th className="pr-3">Language</th><th className="pr-3">Wording</th><th>Made</th></tr>
              </thead>
              <tbody className="text-slate-300">
                {history.map(t => (
                  <tr key={t.template_id} className="border-t border-slate-800 align-top">
                    <td className="py-1.5 pr-3">{t.name}</td>
                    <td className="pr-3">
                      <span className={t.outcome === 'ready' ? 'text-emerald-300' : isWaiting(t.outcome) ? 'text-sky-300' : 'text-rose-300'}>
                        {OUTCOME[t.outcome].label}
                      </span>
                      {t.reason && <div className="text-slate-500 max-w-[260px]">{t.reason}</div>}
                    </td>
                    <td className="pr-3">{t.rows ?? '—'}</td>
                    <td className="pr-3">{t.language_code}</td>
                    <td className="pr-3 text-slate-400 max-w-[360px] truncate" title={t.body}>{t.body}</td>
                    <td className="text-slate-500 whitespace-nowrap">{formatDateTime(t.created_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
};
