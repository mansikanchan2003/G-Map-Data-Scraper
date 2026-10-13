import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  fetchBotSettings, fetchConversation, fetchConversations, markConversationRead,
  saveBotSettings, saveDocumentsToDrive, sendInboxMessage, setBotPaused, documentUrl, mediaUrl,
  type BotSettings, type ConversationDetail, type ConversationSummary, type ThreadMessage,
} from '../api/inbox';

/**
 * Every conversation with the business number, and the place to answer it.
 *
 * A thread shows what the person sent, what the onboarding bot and the team
 * replied, and the campaign messages that reached the same number, so a
 * reply is read under what it answers. Typing back is possible only inside
 * Meta's 24-hour window, and the page says so rather than offering a box
 * that would be refused.
 */

const LIST_POLL_MS = 8000;
const THREAD_POLL_MS = 5000;

// Steps where the bot is still waiting for an answer, so it may reply on its
// own; at any other step the conversation is a person's to handle.
const BOT_WAITING = ['CHOOSE_LANG', 'AWAIT_PIN', 'AWAIT_INVEST', 'AWAIT_DOCS', 'AWAIT_UPLOAD', 'AWAIT_WEBINAR', 'AWAIT_AVAILABILITY'];

const LANGUAGE_NAMES: Record<string, string> = {
  en: 'English', hi: 'Hindi', mr: 'Marathi', pa: 'Punjabi', gu: 'Gujarati', bn: 'Bengali',
  ta: 'Tamil', te: 'Telugu', kn: 'Kannada', ml: 'Malayalam', or: 'Odia',
};

const errMsg = (e: unknown) => (e as { message?: string })?.message || 'Something went wrong';

const since = (iso: string | null) => {
  if (!iso) return '';
  const mins = Math.round((Date.now() - new Date(iso).getTime()) / 60000);
  if (mins < 1) return 'now';
  if (mins < 60) return `${mins}m`;
  const hrs = Math.round(mins / 60);
  if (hrs < 24) return `${hrs}h`;
  return new Date(iso).toLocaleDateString(undefined, { day: '2-digit', month: 'short' });
};

const clock = (iso: string) =>
  new Date(iso).toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' });

const dayLabel = (iso: string) => {
  const d = new Date(iso);
  const today = new Date();
  const yesterday = new Date(); yesterday.setDate(today.getDate() - 1);
  if (d.toDateString() === today.toDateString()) return 'Today';
  if (d.toDateString() === yesterday.toDateString()) return 'Yesterday';
  return d.toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' });
};

/** Time left to send a typed message, or null once the window has closed. */
const windowLeft = (iso: string | null) => {
  if (!iso) return null;
  const mins = Math.floor((new Date(iso).getTime() - Date.now()) / 60000);
  if (mins <= 0) return null;
  if (mins < 60) return `${mins}m left`;
  return `${Math.floor(mins / 60)}h ${mins % 60}m left`;
};

const sizeLabel = (bytes: number) =>
  bytes < 1024 * 1024 ? `${Math.max(1, Math.round(bytes / 1024))} KB` : `${(bytes / 1024 / 1024).toFixed(1)} MB`;

const initials = (name: string | null, phone: string) => {
  const src = (name || '').trim();
  if (!src) return phone.slice(-2);
  return src.split(/\s+/).slice(0, 2).map(w => w[0]?.toUpperCase()).join('');
};

// --- Small pieces ------------------------------------------------------------

const BotChip: React.FC<{ step: string | null; label: string | null; paused: boolean }> = ({ step, label, paused }) => {
  if (!step) return null;
  const waiting = BOT_WAITING.includes(step);
  const cls = paused
    ? 'border-slate-700 bg-slate-800 text-slate-400'
    : step === 'SUBMITTED'
      ? 'border-emerald-800 bg-emerald-950 text-emerald-300'
      : step === 'HANDOVER'
        ? 'border-amber-800 bg-amber-950 text-amber-300'
        : waiting
          ? 'border-sky-800 bg-sky-950 text-sky-300'
          : 'border-slate-700 bg-slate-800 text-slate-300';
  return (
    <span className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded border text-[10px] font-semibold whitespace-nowrap ${cls}`}>
      <span className="material-symbols-outlined text-[12px]">{paused ? 'pause' : 'smart_toy'}</span>
      {paused ? 'Bot paused' : label || step}
    </span>
  );
};

const Ticks: React.FC<{ status: string | null }> = ({ status }) => {
  if (!status) return null;
  if (status === 'FAILED') return <span className="material-symbols-outlined text-[14px] text-rose-400" title="Not delivered">error</span>;
  const read = status === 'READ';
  const double = status === 'DELIVERED' || read;
  return (
    <span className={`material-symbols-outlined text-[14px] ${read ? 'text-sky-400' : 'text-slate-500'}`}
      title={status.charAt(0) + status.slice(1).toLowerCase()}>
      {double ? 'done_all' : 'done'}
    </span>
  );
};

/** WhatsApp's *bold* and _italic_, so a message reads here as it does on the phone. */
const formatted = (text: string): React.ReactNode[] =>
  text.split(/(\*[^*\n]+\*|_[^_\n]+_)/g).map((part, i) => {
    if (/^\*[^*\n]+\*$/.test(part)) return <strong key={i}>{part.slice(1, -1)}</strong>;
    if (/^_[^_\n]+_$/.test(part)) return <em key={i}>{part.slice(1, -1)}</em>;
    return part;
  });

const MEDIA_KINDS = ['image', 'video', 'audio', 'document', 'sticker'];

/** A file someone sent, shown the way WhatsApp would show it. */
const Media: React.FC<{ m: ThreadMessage }> = ({ m }) => {
  const [failed, setFailed] = useState(false);
  const p = m.payload || {};
  const src = mediaUrl(m.id);
  const label = (m.body || '').match(/^\[([^\]]+)\]/)?.[1] || 'File';

  if (failed || p.fetch_error && !p.available) {
    return (
      <div className="flex items-center gap-2 text-xs text-slate-400">
        <span className="material-symbols-outlined text-[18px]">broken_image</span>
        <span>{label} could not be loaded from WhatsApp{p.fetch_error ? `: ${p.fetch_error}` : '.'}</span>
      </div>
    );
  }
  if (m.kind === 'image' || m.kind === 'sticker') {
    return (
      <a href={src} target="_blank" rel="noreferrer" className="block">
        <img src={src} alt={label} loading="lazy" onError={() => setFailed(true)}
          className={`rounded-md bg-slate-800 ${m.kind === 'sticker' ? 'w-32 h-32 object-contain bg-transparent' : 'max-h-80 w-auto max-w-full object-contain'}`} />
      </a>
    );
  }
  if (m.kind === 'video') {
    return <video src={src} controls preload="metadata" onError={() => setFailed(true)} className="rounded-md max-h-80 w-full bg-black" />;
  }
  if (m.kind === 'audio') {
    return <audio src={src} controls preload="metadata" onError={() => setFailed(true)} className="w-64 max-w-full" />;
  }
  const name = p.filename || 'Document';
  return (
    <div className="flex items-center gap-2 rounded-md border border-slate-700 bg-slate-950/60 px-2.5 py-2 w-60 max-w-full">
      <span className="material-symbols-outlined text-[22px] text-slate-400">
        {(p.mime_type || '').includes('pdf') ? 'picture_as_pdf' : 'description'}
      </span>
      <div className="min-w-0 flex-1">
        <div className="text-sm text-slate-100 truncate">{name}</div>
        {p.size && <div className="text-[10px] text-slate-500">{sizeLabel(p.size)}</div>}
      </div>
      <a href={src} target="_blank" rel="noreferrer" title="Open" className="text-sky-400 hover:text-sky-300 shrink-0">
        <span className="material-symbols-outlined text-[18px]">open_in_new</span>
      </a>
      <a href={mediaUrl(m.id, true)} title="Download" className="text-sky-400 hover:text-sky-300 shrink-0">
        <span className="material-symbols-outlined text-[18px]">download</span>
      </a>
    </div>
  );
};

const Bubble: React.FC<{ m: ThreadMessage }> = ({ m }) => {
  const out = m.direction === 'OUT';
  const tapped = m.direction === 'IN' && (m.kind === 'button' || m.kind === 'interactive');

  let who: React.ReactNode = null;
  if (out) {
    if (m.kind === 'campaign') {
      who = <><span className="material-symbols-outlined text-[12px]">campaign</span>Campaign · {m.campaign}</>;
    } else if (m.sent_by === 'bot') {
      who = <><span className="material-symbols-outlined text-[12px]">smart_toy</span>Bot</>;
    } else if (m.sent_by) {
      who = <><span className="material-symbols-outlined text-[12px]">person</span>{m.sent_by}</>;
    }
  }

  const buttons: string[] =
    m.kind === 'buttons' && Array.isArray(m.payload) ? m.payload.map((b: any) => b.title)
      : m.kind === 'campaign' && Array.isArray(m.payload) ? m.payload
        : [];

  return (
    <div className={`flex ${out ? 'justify-end' : 'justify-start'}`}>
      <div className={`max-w-[85%] sm:max-w-[70%] rounded-lg px-3 py-2 border shadow-sm ${
        out
          ? m.status === 'FAILED'
            ? 'bg-rose-950/60 border-rose-900'
            : m.kind === 'campaign' ? 'bg-slate-800/70 border-slate-700' : 'bg-emerald-950 border-emerald-900'
          : 'bg-slate-900 border-slate-800'
      }`}>
        {who && (
          <div className="flex items-center gap-1 text-[10px] font-semibold text-slate-400 mb-1 truncate">{who}</div>
        )}
        {tapped ? (
          <div className="flex items-center gap-1.5 text-sm text-amber-300">
            <span className="material-symbols-outlined text-[16px]">touch_app</span>
            Tapped “{m.body}”
          </div>
        ) : m.direction === 'IN' && MEDIA_KINDS.includes(m.kind) ? (
          <div className="flex flex-col gap-1.5">
            <Media m={m} />
            {/* The caption, without the "[Photo]" label the list preview uses. */}
            {(m.body || '').replace(/^\[[^\]]+\]\s*/, '') && m.kind !== 'document' && (
              <div className="text-sm text-slate-100 whitespace-pre-wrap break-words select-text">
                {formatted((m.body || '').replace(/^\[[^\]]+\]\s*/, ''))}
              </div>
            )}
          </div>
        ) : (
          <div className="text-sm text-slate-100 whitespace-pre-wrap break-words select-text">
            {m.body ? formatted(m.body) : (m.kind === 'campaign' ? 'Template message' : '')}
          </div>
        )}
        {buttons.length > 0 && (
          <div className="flex flex-wrap gap-1 mt-2">
            {buttons.map(b => (
              <span key={b} className="text-[11px] px-2 py-0.5 rounded-full border border-sky-800 text-sky-300 bg-sky-950/60">{b}</span>
            ))}
          </div>
        )}
        {m.kind === 'link' && m.payload?.url && (
          <a href={m.payload.url} target="_blank" rel="noreferrer"
            className="mt-2 flex items-center justify-center gap-1 text-[12px] font-semibold px-2 py-1 rounded border border-sky-800 text-sky-300 bg-sky-950/60 hover:bg-sky-900/60">
            <span className="material-symbols-outlined text-[14px]">open_in_new</span>{m.payload.text}
          </a>
        )}
        {m.status === 'FAILED' && m.error_reason && (
          <div className="text-[11px] text-rose-300 mt-1.5">{m.error_reason}</div>
        )}
        <div className="flex items-center justify-end gap-1 mt-1 text-[10px] text-slate-500">
          {clock(m.created_at)}
          {out && <Ticks status={m.status} />}
        </div>
      </div>
    </div>
  );
};

// --- Bot settings ------------------------------------------------------------

const BotSettingsPanel: React.FC<{ onClose: () => void }> = ({ onClose }) => {
  const [settings, setSettings] = useState<BotSettings | null>(null);
  const [enabled, setEnabled] = useState(true);
  const [triggers, setTriggers] = useState('');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    fetchBotSettings().then(s => {
      setSettings(s);
      setEnabled(s.enabled);
      setTriggers(s.triggers.join(', '));
    }).catch(e => setError(errMsg(e)));
  }, []);

  const save = async () => {
    setSaving(true); setError(null); setSaved(false);
    try {
      const s = await saveBotSettings(enabled, triggers.split(',').map(t => t.trim()).filter(Boolean));
      setSettings(s);
      setSaved(true);
    } catch (e) {
      setError(errMsg(e));
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 bg-black/70 flex items-center justify-center p-4" onClick={onClose}>
      <div className="w-full max-w-lg max-h-[90vh] overflow-y-auto bg-slate-900 border border-slate-700 rounded-lg p-5 shadow-xl select-text"
        onClick={e => e.stopPropagation()}>
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-sm font-semibold text-slate-100 flex items-center gap-2">
            <span className="material-symbols-outlined text-[18px] text-sky-400">smart_toy</span>Onboarding bot
          </h2>
          <button onClick={onClose} className="text-slate-500 hover:text-slate-200 cursor-pointer" aria-label="Close">
            <span className="material-symbols-outlined text-[20px]">close</span>
          </button>
        </div>

        {!settings && !error && <div className="text-xs text-slate-500">Loading…</div>}
        {settings && (
          <div className="flex flex-col gap-4 text-xs">
            <label className="flex items-start gap-3 cursor-pointer" data-edit>
              <input type="checkbox" checked={enabled} onChange={e => setEnabled(e.target.checked)} className="mt-0.5 accent-sky-500" />
              <span>
                <span className="block text-slate-100 font-semibold">Answer automatically</span>
                <span className="text-slate-400">When off, nothing is sent on its own; every conversation waits for a person.</span>
              </span>
            </label>

            <div data-edit>
              <label className="block text-slate-300 font-semibold mb-1" htmlFor="bot-triggers">Buttons that start it</label>
              <input id="bot-triggers" value={triggers} onChange={e => setTriggers(e.target.value)}
                placeholder="Interested"
                className="w-full bg-slate-950 border border-slate-700 rounded px-2.5 py-2 text-slate-100 focus:outline-none focus:border-sky-500" />
              <p className="text-slate-500 mt-1">Quick-reply button labels on a campaign, separated by commas. Case and punctuation are ignored, so “Interested?” matches.</p>
            </div>

            <div className="rounded border border-slate-800 bg-slate-950 p-3 text-slate-400 leading-relaxed">
              <div className="text-slate-300 font-semibold mb-1">What it does</div>
              <p className="mb-1.5">
                It answers only people an AutoGMap campaign reached. Everyone else who writes to this
                shared number is shown here but left for a person.
              </p>
              <ol className="list-decimal pl-4 space-y-0.5">
                <li>Asks them to choose English, Hindi or their campaign's language, and speaks it from then on.</li>
                <li>Asks for their PIN code.</li>
                <li>Checks it is one of our PINs or within {settings.radius_km} km of one.</li>
                <li>Asks whether they can invest ₹5 Lakh — Yes / No.</li>
                <li>Lists the documents needed and asks if they have them — Yes / No.</li>
                <li>Sends the upload link; after they submit, thanks them.</li>
              </ol>
              <p className="mt-1.5">
                The <span className="text-slate-300">Webinar</span> button instead asks if they can join tomorrow's
                webinar; a yes, or the time they suggest, is emailed to you so the link can be sent.
              </p>
              <div className="text-slate-300 font-semibold mt-3 mb-1">Documents asked for</div>
              <ul className="list-disc pl-4 space-y-0.5">
                {settings.documents.map(d => (
                  <li key={d.key}>
                    {d.label}
                    <span className={d.required ? 'text-rose-400 ml-1' : 'text-slate-500 ml-1'}>
                      · {d.required ? 'required' : 'optional'}
                    </span>
                  </li>
                ))}
              </ul>
            </div>

            {!settings.public_base_url_set && (
              <div className="rounded border border-amber-800 bg-amber-950/60 text-amber-300 p-2.5">
                PUBLIC_BASE_URL is not set, so upload links point at localhost and will not open on a phone.
              </div>
            )}
            <div className={`rounded border p-2.5 ${settings.drive_configured
              ? 'border-emerald-900 bg-emerald-950/50 text-emerald-300'
              : 'border-amber-800 bg-amber-950/60 text-amber-300'}`}>
              {settings.drive_configured
                ? 'Submitted documents are copied to Google Drive.'
                : 'Google Drive is not set up (GOOGLE_DRIVE_FOLDER_ID), so documents stay on the server.'}
              {settings.drive_service_account && (
                <span className="block mt-1 text-slate-400">
                  The folder must be in a shared drive, with <span className="font-mono-code text-slate-300">{settings.drive_service_account}</span> as Content manager.
                </span>
              )}
            </div>

            {error && <div className="text-rose-400">{error}</div>}
            <div className="flex items-center justify-end gap-2" data-edit>
              {saved && <span className="text-emerald-400 mr-auto">Saved</span>}
              <button onClick={onClose} className="px-3 py-1.5 rounded border border-slate-700 text-slate-300 hover:bg-slate-800 cursor-pointer">Close</button>
              <button onClick={save} disabled={saving}
                className="px-3 py-1.5 rounded bg-sky-600 text-white font-semibold hover:bg-sky-500 disabled:opacity-50 cursor-pointer">
                {saving ? 'Saving…' : 'Save'}
              </button>
            </div>
          </div>
        )}
        {!settings && error && <div className="text-xs text-rose-400">{error}</div>}
      </div>
    </div>
  );
};

// --- Details: who, the bot, documents ----------------------------------------

const Details: React.FC<{
  conv: ConversationDetail;
  onChanged: () => void;
}> = ({ conv, onChanged }) => {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const coverage = conv.bot_data?.coverage;
  const notInDrive = conv.document_files.filter(d => !d.drive_url);
  const driveError = notInDrive.find(d => d.drive_error)?.drive_error;

  const togglePause = async () => {
    setBusy(true); setError(null);
    try { await setBotPaused(conv.phone, !conv.bot_paused); onChanged(); }
    catch (e) { setError(errMsg(e)); }
    finally { setBusy(false); }
  };

  const retryDrive = async () => {
    setBusy(true); setError(null);
    try { await saveDocumentsToDrive(conv.phone); onChanged(); }
    catch (e) { setError(errMsg(e)); }
    finally { setBusy(false); }
  };

  const Row = ({ label, value }: { label: string; value: React.ReactNode }) => (
    <div className="flex justify-between gap-3 py-1">
      <span className="text-slate-500">{label}</span>
      <span className="text-slate-200 text-right break-words min-w-0">{value}</span>
    </div>
  );

  return (
    <div className="flex flex-col gap-4 text-xs select-text">
      <section>
        <h3 className="text-[10px] font-mono-code uppercase tracking-wider text-slate-500 mb-1.5">Contact</h3>
        <Row label="Phone" value={<span className="font-mono-code">{conv.phone}</span>} />
        {conv.category && <Row label="Category" value={conv.category} />}
        {(conv.district || conv.state) && <Row label="Area" value={[conv.district, conv.state].filter(Boolean).join(', ')} />}
        <a href={`https://wa.me/${conv.phone.replace(/\D/g, '')}`} target="_blank" rel="noreferrer"
          className="inline-flex items-center gap-1 mt-1 text-sky-400 hover:text-sky-300">
          <span className="material-symbols-outlined text-[14px]">open_in_new</span>Open in WhatsApp
        </a>
      </section>

      <section>
        <h3 className="text-[10px] font-mono-code uppercase tracking-wider text-slate-500 mb-1.5">Onboarding bot</h3>
        {!conv.from_campaign ? (
          <p className="text-slate-500">
            Not from an AutoGMap campaign, so the bot does not reply. This number is shared with
            other teams; reply here by hand if it is ours to answer.
          </p>
        ) : conv.bot_step ? (
          <>
            <Row label="Step" value={<BotChip step={conv.bot_step} label={conv.bot_step_label} paused={false} />} />
            {conv.bot_data?.lang && <Row label="Language" value={LANGUAGE_NAMES[conv.bot_data.lang] || conv.bot_data.lang} />}
            {conv.bot_data?.webinar && (
              <Row label="Webinar" value={conv.bot_data.webinar.answer === 'yes'
                ? 'Coming tomorrow'
                : `Available: ${conv.bot_data.webinar.availability || '—'}`} />
            )}
            {coverage?.pincode && <Row label="PIN code" value={<span className="font-mono-code">{coverage.pincode}</span>} />}
            {coverage?.nearest_pincode && coverage.nearest_pincode !== coverage.pincode && (
              <Row label="Nearest of ours" value={`${coverage.nearest_pincode} · ${coverage.distance_km} km`} />
            )}
            {coverage?.place && <Row label="Area" value={coverage.place} />}
            {conv.bot_data?.can_invest !== undefined && (
              <Row label="Can invest ₹5L" value={conv.bot_data.can_invest ? 'Yes' : 'No'} />
            )}
            {conv.upload_url && !conv.documents_submitted_at && (
              <Row label="Upload link" value={
                <a href={conv.upload_url} target="_blank" rel="noreferrer" className="text-sky-400 hover:text-sky-300">open</a>
              } />
            )}
          </>
        ) : (
          <p className="text-slate-500">Not started. It starts when they tap a trigger button on a campaign.</p>
        )}
        {conv.from_campaign && (
          <>
            <button data-edit onClick={togglePause} disabled={busy}
              className={`mt-2 w-full inline-flex items-center justify-center gap-1.5 px-2 py-1.5 rounded border font-semibold cursor-pointer disabled:opacity-50 ${
                conv.bot_paused
                  ? 'border-sky-800 bg-sky-950 text-sky-300 hover:bg-sky-900'
                  : 'border-slate-700 bg-slate-800 text-slate-300 hover:bg-slate-700'}`}>
              <span className="material-symbols-outlined text-[16px]">{conv.bot_paused ? 'play_arrow' : 'pause'}</span>
              {conv.bot_paused ? 'Let the bot answer again' : 'Pause the bot here'}
            </button>
            <p className="text-slate-500 mt-1">
              {conv.bot_paused
                ? 'Paused: the bot will not answer this person until you resume it.'
                : 'Pause it to take this conversation over by hand.'}
            </p>
          </>
        )}
      </section>

      <section>
        <div className="flex items-center justify-between mb-1.5">
          <h3 className="text-[10px] font-mono-code uppercase tracking-wider text-slate-500">
            Documents {conv.document_files.length > 0 && `(${conv.document_files.length})`}
          </h3>
          {conv.drive_folder_url && (
            <a href={conv.drive_folder_url} target="_blank" rel="noreferrer"
              className="inline-flex items-center gap-1 text-sky-400 hover:text-sky-300">
              <span className="material-symbols-outlined text-[14px]">folder</span>Drive folder
            </a>
          )}
        </div>
        {conv.documents_submitted_at && (
          <p className="text-emerald-400 mb-1.5">Submitted {since(conv.documents_submitted_at)} ago</p>
        )}
        {conv.document_files.length === 0 ? (
          <p className="text-slate-500">None uploaded.</p>
        ) : (
          <ul className="flex flex-col gap-1.5">
            {conv.document_files.map(d => (
              <li key={d.document_id} className="flex items-center gap-2 rounded border border-slate-800 bg-slate-950 px-2 py-1.5">
                <span className="material-symbols-outlined text-[18px] text-slate-500">
                  {d.content_type === 'application/pdf' ? 'picture_as_pdf' : 'image'}
                </span>
                <div className="min-w-0 flex-1">
                  <div className="text-slate-200 truncate">{d.label}</div>
                  <div className="text-[10px] text-slate-500 truncate">{d.original_name} · {sizeLabel(d.size_bytes)}</div>
                </div>
                {d.drive_url ? (
                  <a href={d.drive_url} target="_blank" rel="noreferrer" title="Open in Google Drive"
                    className="text-sky-400 hover:text-sky-300 shrink-0">
                    <span className="material-symbols-outlined text-[18px]">add_to_drive</span>
                  </a>
                ) : (
                  <>
                    <a href={documentUrl(d.document_id)} target="_blank" rel="noreferrer" title="View"
                      className="text-sky-400 hover:text-sky-300 shrink-0">
                      <span className="material-symbols-outlined text-[18px]">visibility</span>
                    </a>
                    <a href={documentUrl(d.document_id, true)} title="Download"
                      className="text-sky-400 hover:text-sky-300 shrink-0">
                      <span className="material-symbols-outlined text-[18px]">download</span>
                    </a>
                  </>
                )}
              </li>
            ))}
          </ul>
        )}
        {conv.documents_submitted_at && notInDrive.length > 0 && (
          <div className="mt-2 rounded border border-amber-800 bg-amber-950/50 p-2 text-amber-300">
            {notInDrive.length} file{notInDrive.length > 1 ? 's are' : ' is'} not in Google Drive yet.
            {driveError && <span className="block text-amber-400/80 mt-1 break-words">{driveError}</span>}
            <button data-edit onClick={retryDrive} disabled={busy}
              className="mt-2 inline-flex items-center gap-1 px-2 py-1 rounded border border-amber-700 hover:bg-amber-900/50 font-semibold cursor-pointer disabled:opacity-50">
              <span className="material-symbols-outlined text-[14px]">refresh</span>Try again
            </button>
          </div>
        )}
      </section>
      {error && <div className="text-rose-400">{error}</div>}
    </div>
  );
};

// --- The view ----------------------------------------------------------------

export const InboxView: React.FC<{ readOnly?: boolean }> = ({ readOnly = false }) => {
  const [conversations, setConversations] = useState<ConversationSummary[]>([]);
  const [listError, setListError] = useState<string | null>(null);
  const [loadingList, setLoadingList] = useState(true);
  const [query, setQuery] = useState('');
  const [filter, setFilter] = useState<'all' | 'autogmap' | 'unread' | 'bot' | 'docs'>('all');
  const [selected, setSelected] = useState<string | null>(() => {
    // A link such as #inbox/919876543210 opens that conversation.
    const m = window.location.hash.match(/^#inbox\/(\d+)/);
    return m ? `+${m[1]}` : null;
  });
  const [detail, setDetail] = useState<ConversationDetail | null>(null);
  const [threadError, setThreadError] = useState<string | null>(null);
  const [draft, setDraft] = useState('');
  const [sending, setSending] = useState(false);
  const [sendError, setSendError] = useState<string | null>(null);
  const [showSettings, setShowSettings] = useState(false);
  const [showDetails, setShowDetails] = useState(false);
  const scroller = useRef<HTMLDivElement>(null);
  const selectedRef = useRef(selected);
  selectedRef.current = selected;
  const lastCount = useRef(0);
  const [, setTick] = useState(0);

  const loadList = useCallback(async () => {
    try {
      setConversations(await fetchConversations(query));
      setListError(null);
    } catch (e) {
      setListError(errMsg(e));
    } finally {
      setLoadingList(false);
    }
  }, [query]);

  const loadThread = useCallback(async (phone: string) => {
    try {
      const d = await fetchConversation(phone);
      // A slow answer for a conversation since closed must not replace the open one.
      if (phone !== selectedRef.current) return;
      setDetail(d);
      setThreadError(null);
      // Reading it here is reading it; a member's view-only account cannot
      // record that, and need not.
      if (d.unread > 0 && !readOnly) {
        markConversationRead(phone).then(loadList).catch(() => {});
      }
    } catch (e) {
      setThreadError(errMsg(e));
    }
  }, [readOnly, loadList]);

  // The list, refreshed while the tab is open; the query is debounced.
  useEffect(() => {
    const t = setTimeout(loadList, 250);
    const i = setInterval(loadList, LIST_POLL_MS);
    return () => { clearTimeout(t); clearInterval(i); };
  }, [loadList]);

  // The open thread, refreshed more often.
  useEffect(() => {
    setDetail(null);
    setSendError(null);
    lastCount.current = 0;
    if (!selected) return;
    loadThread(selected);
    const i = setInterval(() => loadThread(selected), THREAD_POLL_MS);
    return () => clearInterval(i);
  }, [selected, loadThread]);

  // Following a link to another conversation while the inbox is open.
  useEffect(() => {
    const onHash = () => {
      const m = window.location.hash.match(/^#inbox\/(\d+)/);
      if (m) setSelected(`+${m[1]}`);
    };
    window.addEventListener('hashchange', onHash);
    return () => window.removeEventListener('hashchange', onHash);
  }, []);

  // The countdown on the reply window moves without a refetch.
  useEffect(() => {
    const i = setInterval(() => setTick(t => t + 1), 30000);
    return () => clearInterval(i);
  }, []);

  // Keep the newest message in view when one arrives, unless the reader has
  // scrolled up to read something older.
  useEffect(() => {
    const el = scroller.current;
    const count = detail?.messages.length ?? 0;
    if (!el || count === lastCount.current) return;
    const nearBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 160;
    if (lastCount.current === 0 || nearBottom) el.scrollTop = el.scrollHeight;
    lastCount.current = count;
  }, [detail?.messages.length]);

  const open = (phone: string) => {
    setSelected(phone);
    setShowDetails(false);
    window.history.replaceState(null, '', `#inbox/${phone.replace(/\D/g, '')}`);
  };

  const close = () => {
    setSelected(null);
    window.history.replaceState(null, '', '#inbox');
  };

  const send = async () => {
    const body = draft.trim();
    if (!body || !selected || sending) return;
    setSending(true);
    setSendError(null);
    try {
      await sendInboxMessage(selected, body);
      setDraft('');
      await loadThread(selected);
      loadList();
    } catch (e) {
      setSendError(errMsg(e));
      // A refused send is still recorded, so the thread shows it marked failed.
      loadThread(selected);
    } finally {
      setSending(false);
    }
  };

  const shown = useMemo(() => conversations.filter(c =>
    filter === 'autogmap' ? c.from_campaign
    : filter === 'unread' ? c.unread > 0
      : filter === 'bot' ? !!c.bot_step && BOT_WAITING.includes(c.bot_step) && !c.bot_paused
        : filter === 'docs' ? c.documents > 0
          : true,
  ), [conversations, filter]);

  const unreadTotal = conversations.filter(c => c.unread > 0).length;
  const left = detail ? windowLeft(detail.window_expires_at) : null;
  const botActive = !!detail?.bot_step && BOT_WAITING.includes(detail.bot_step) && !detail.bot_paused;

  // Messages grouped under a date line.
  const grouped = useMemo(() => {
    const out: { day: string; items: ThreadMessage[] }[] = [];
    for (const m of detail?.messages ?? []) {
      const day = dayLabel(m.created_at);
      if (!out.length || out[out.length - 1].day !== day) out.push({ day, items: [] });
      out[out.length - 1].items.push(m);
    }
    return out;
  }, [detail?.messages]);

  return (
    <div className="flex-1 flex min-h-0 overflow-hidden">
      {/* Conversation list */}
      <aside className={`${selected ? 'hidden md:flex' : 'flex'} w-full md:w-80 lg:w-96 shrink-0 flex-col border-r border-slate-800 bg-slate-900/40 min-h-0`}>
        <div className="p-3 border-b border-slate-800 flex flex-col gap-2">
          <div className="flex items-center justify-between">
            <h1 className="text-sm font-semibold text-slate-100 flex items-center gap-2">
              Inbox
              {unreadTotal > 0 && (
                <span className="text-[10px] font-bold px-1.5 py-0.5 rounded-full bg-emerald-500 text-slate-950">{unreadTotal}</span>
              )}
            </h1>
            <button onClick={() => setShowSettings(true)} title="Onboarding bot settings"
              className="inline-flex items-center gap-1 text-[11px] text-slate-400 hover:text-slate-200 px-2 py-1 rounded hover:bg-slate-800 cursor-pointer">
              <span className="material-symbols-outlined text-[16px]">smart_toy</span>Bot
            </button>
          </div>
          <div className="relative">
            <span className="material-symbols-outlined text-[16px] text-slate-500 absolute left-2 top-1/2 -translate-y-1/2">search</span>
            <input value={query} onChange={e => setQuery(e.target.value)} placeholder="Search name or number"
              className="w-full bg-slate-950 border border-slate-800 rounded pl-8 pr-2 py-1.5 text-xs text-slate-100 focus:outline-none focus:border-sky-600" />
          </div>
          <div className="flex gap-1 overflow-x-auto">
            {([['all', 'All'], ['autogmap', 'From AutoGMap'], ['unread', 'Unread'], ['bot', 'With bot'], ['docs', 'Documents']] as const).map(([k, label]) => (
              <button key={k} onClick={() => setFilter(k)}
                className={`text-[11px] px-2 py-1 rounded-full border whitespace-nowrap cursor-pointer ${
                  filter === k ? 'border-sky-600 bg-sky-950 text-sky-300' : 'border-slate-800 text-slate-400 hover:text-slate-200'}`}>
                {label}
              </button>
            ))}
          </div>
        </div>

        <div className="flex-1 overflow-y-auto min-h-0">
          {loadingList && <div className="p-4 text-xs text-slate-500">Loading…</div>}
          {listError && <div className="p-4 text-xs text-rose-400">{listError}</div>}
          {!loadingList && !listError && shown.length === 0 && (
            <div className="p-6 text-center text-xs text-slate-500 leading-relaxed">
              <span className="material-symbols-outlined text-[32px] text-slate-700 block mb-2">forum</span>
              {conversations.length === 0
                ? 'No messages yet. When someone writes to the business number or taps a quick-reply button, the conversation appears here.'
                : 'Nothing matches this filter.'}
            </div>
          )}
          <ul>
            {shown.map(c => {
              const active = c.phone === selected;
              return (
                <li key={c.phone}>
                  <button onClick={() => open(c.phone)}
                    className={`w-full text-left flex gap-3 px-3 py-2.5 border-b border-slate-800/70 cursor-pointer ${
                      active ? 'bg-sky-950/50' : 'hover:bg-slate-800/50'}`}>
                    <span className="w-9 h-9 shrink-0 rounded-full bg-slate-800 text-slate-300 text-xs font-bold flex items-center justify-center">
                      {initials(c.name, c.phone)}
                    </span>
                    <span className="min-w-0 flex-1">
                      <span className="flex items-center justify-between gap-2">
                        <span className={`text-sm truncate ${c.unread ? 'font-semibold text-slate-100' : 'text-slate-200'}`}>
                          {c.name || c.phone}
                        </span>
                        <span className={`text-[10px] shrink-0 ${c.unread ? 'text-emerald-400' : 'text-slate-500'}`}>{since(c.last_message_at)}</span>
                      </span>
                      <span className="flex items-center justify-between gap-2 mt-0.5">
                        <span className="text-xs text-slate-400 truncate">
                          {c.last_direction === 'OUT' && <span className="text-slate-500">You: </span>}
                          {c.last_message || '—'}
                        </span>
                        {c.unread > 0 && (
                          <span className="text-[10px] font-bold min-w-[18px] h-[18px] px-1 rounded-full bg-emerald-500 text-slate-950 flex items-center justify-center shrink-0">
                            {c.unread}
                          </span>
                        )}
                      </span>
                      {(c.from_campaign || c.bot_step || c.documents > 0) && (
                        <span className="flex items-center gap-1.5 mt-1 flex-wrap">
                          {c.from_campaign && (
                            <span title="Reached by an AutoGMap campaign"
                              className="inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded border border-amber-800 bg-amber-950/60 text-amber-300 text-[10px] font-semibold whitespace-nowrap">
                              <span className="material-symbols-outlined text-[12px]">campaign</span>AutoGMap
                            </span>
                          )}
                          <BotChip step={c.bot_step} label={c.bot_step_label} paused={c.bot_paused} />
                          {c.documents > 0 && (
                            <span className="inline-flex items-center gap-0.5 text-[10px] text-slate-400">
                              <span className="material-symbols-outlined text-[12px]">attach_file</span>{c.documents}
                            </span>
                          )}
                        </span>
                      )}
                    </span>
                  </button>
                </li>
              );
            })}
          </ul>
        </div>
      </aside>

      {/* Thread */}
      <section className={`${selected ? 'flex' : 'hidden md:flex'} flex-1 flex-col min-w-0 min-h-0`}>
        {!selected ? (
          <div className="flex-1 flex items-center justify-center text-xs text-slate-500 p-6 text-center">
            <div>
              <span className="material-symbols-outlined text-[40px] text-slate-700 block mb-2">chat</span>
              Pick a conversation to read it and reply.
            </div>
          </div>
        ) : (
          <>
            <header className="flex items-center gap-3 px-3 py-2 border-b border-slate-800 bg-slate-900/60">
              <button onClick={close} className="md:hidden text-slate-400 hover:text-slate-100 cursor-pointer" aria-label="Back to conversations">
                <span className="material-symbols-outlined text-[22px]">arrow_back</span>
              </button>
              <span className="w-9 h-9 shrink-0 rounded-full bg-slate-800 text-slate-300 text-xs font-bold flex items-center justify-center">
                {initials(detail?.name ?? null, selected)}
              </span>
              <div className="min-w-0 flex-1">
                <div className="text-sm font-semibold text-slate-100 truncate">{detail?.name || selected}</div>
                <div className="flex items-center gap-2 text-[11px] text-slate-400">
                  <span className="font-mono-code">{selected}</span>
                  {detail && <BotChip step={detail.bot_step} label={detail.bot_step_label} paused={detail.bot_paused} />}
                </div>
              </div>
              <button onClick={() => setShowDetails(s => !s)} title="Details and documents"
                className={`xl:hidden inline-flex items-center gap-1 text-[11px] px-2 py-1 rounded border cursor-pointer ${
                  showDetails ? 'border-sky-700 text-sky-300 bg-sky-950' : 'border-slate-700 text-slate-300 hover:bg-slate-800'}`}>
                <span className="material-symbols-outlined text-[16px]">info</span>
                {detail && detail.document_files.length > 0 && <span>{detail.document_files.length}</span>}
              </button>
            </header>

            <div className="flex-1 flex min-h-0">
              <div className="flex-1 flex flex-col min-w-0 min-h-0">
                {showDetails && detail && (
                  <div className="xl:hidden border-b border-slate-800 bg-slate-900 p-3 max-h-[55%] overflow-y-auto">
                    <Details conv={detail} onChanged={() => { loadThread(selected); loadList(); }} />
                  </div>
                )}
                <div ref={scroller} className="flex-1 overflow-y-auto min-h-0 px-3 sm:px-5 py-4 bg-slate-950">
                  {threadError && <div className="text-xs text-rose-400 mb-3">{threadError}</div>}
                  {!detail && !threadError && <div className="text-xs text-slate-500">Loading…</div>}
                  {grouped.map(g => (
                    <div key={g.day} className="flex flex-col gap-2 mb-3">
                      <div className="flex justify-center my-1">
                        <span className="text-[10px] px-2 py-0.5 rounded-full bg-slate-800 text-slate-400">{g.day}</span>
                      </div>
                      {g.items.map(m => <Bubble key={m.id} m={m} />)}
                    </div>
                  ))}
                </div>

                {/* Composer */}
                {!readOnly && detail && (
                  <div className="border-t border-slate-800 bg-slate-900/60 p-2.5" data-edit>
                    {left ? (
                      <>
                        {botActive && (
                          <div className="text-[11px] text-sky-300 mb-1.5 flex items-center gap-1">
                            <span className="material-symbols-outlined text-[14px]">smart_toy</span>
                            The bot is answering this person. Pause it from the details panel to take over.
                          </div>
                        )}
                        <div className="flex items-end gap-2">
                          <textarea value={draft} onChange={e => setDraft(e.target.value)}
                            onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(); } }}
                            rows={Math.min(5, Math.max(1, draft.split('\n').length))}
                            maxLength={4096}
                            placeholder="Type a reply"
                            title="Enter sends; Shift+Enter starts a new line"
                            className="flex-1 resize-none bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-100 focus:outline-none focus:border-emerald-600 select-text" />
                          <button onClick={send} disabled={!draft.trim() || sending} aria-label="Send"
                            className="w-10 h-10 shrink-0 rounded-full bg-emerald-600 hover:bg-emerald-500 text-white flex items-center justify-center disabled:opacity-40 cursor-pointer">
                            {sending
                              ? <span className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
                              : <span className="material-symbols-outlined text-[20px]">send</span>}
                          </button>
                        </div>
                        <div className="flex justify-between mt-1 text-[10px] text-slate-500">
                          <span className="text-rose-400">{sendError}</span>
                          <span title="Meta allows a typed message only within 24 hours of the person's last message.">Reply window: {left}</span>
                        </div>
                      </>
                    ) : (
                      // Said plainly rather than shown as a dead box: the
                      // reason it cannot be done is the useful part.
                      <div className="text-[11px] text-slate-400 flex items-start gap-2 px-1 py-1">
                        <span className="material-symbols-outlined text-[16px] text-slate-500">schedule</span>
                        <span>
                          {detail.window_expires_at
                            ? 'The 24-hour reply window has closed. Meta allows a typed message only within 24 hours of their last message; an approved template from a campaign is the only way to reach them now.'
                            : 'They have not written to us, so a typed message cannot be sent. Reach them with a campaign template.'}
                        </span>
                      </div>
                    )}
                  </div>
                )}
              </div>

              {detail && (
                <aside className="hidden xl:block w-80 shrink-0 border-l border-slate-800 bg-slate-900/40 p-4 overflow-y-auto">
                  <Details conv={detail} onChanged={() => { loadThread(selected); loadList(); }} />
                </aside>
              )}
            </div>
          </>
        )}
      </section>

      {showSettings && <BotSettingsPanel onClose={() => setShowSettings(false)} />}
    </div>
  );
};
