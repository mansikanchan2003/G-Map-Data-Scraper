import React, { useEffect, useState } from 'react';
import {
  fetchDispositionOptions, handOver, recordDisposition,
  type ConversationDetail, type Disposition, type DispositionOption,
} from '../api/inbox';
import { formatDateTime } from '../utils/datetime';

/**
 * Handing a chat between the bot and a person, and recording its outcome.
 *
 * The bar above the thread says who is handling the chat: the bot, or a
 * person since when. "Take over" quiets the bot (a reply by hand does the
 * same); "Hand back to the bot" asks for the outcome so far and lets the bot
 * ask its question again. The outcome (disposition) shows beside it and can
 * be changed at any time.
 */

const GROUP_STYLE: Record<string, string> = {
  positive: 'border-emerald-800/60 bg-emerald-950 text-emerald-300',
  follow_up: 'border-amber-800/60 bg-amber-950 text-amber-300',
  negative: 'border-rose-800/60 bg-rose-950 text-rose-300',
  other: 'border-slate-700 bg-slate-800 text-slate-300',
};
const GROUP_LABEL: Record<string, string> = {
  positive: 'Going well', follow_up: 'Follow up', negative: 'Closed', other: 'Other',
};

let cached: DispositionOption[] | null = null;
export const useDispositionOptions = () => {
  const [opts, setOpts] = useState<DispositionOption[]>(cached || []);
  useEffect(() => {
    if (cached) return;
    fetchDispositionOptions().then(o => { cached = o; setOpts(o); }).catch(() => {});
  }, []);
  return opts;
};

export const groupOf = (opts: DispositionOption[], key?: string | null) =>
  opts.find(o => o.key === key)?.group || 'other';

/** A disposition as a small coloured chip. */
export const DispositionChip: React.FC<{ d: Disposition | null; opts: DispositionOption[]; compact?: boolean }> = ({ d, opts, compact }) => {
  if (!d) return null;
  return (
    <span title={`${d.label}${d.note ? ` — ${d.note}` : ''}\n${d.source === 'bot' ? 'From the bot' : `Recorded by ${d.by}`}`}
      className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded border text-[10.5px] font-semibold whitespace-nowrap ${GROUP_STYLE[groupOf(opts, d.key)]}`}>
      {!compact && <span className="material-symbols-outlined text-[13px]">{d.source === 'bot' ? 'smart_toy' : 'person'}</span>}
      {d.label}
    </span>
  );
};

/**
 * Choose an outcome (and a note). Used when handing back to the bot, when a
 * question is resolved, and to record or change the outcome at any time.
 */
export const DispositionDialog: React.FC<{
  title: string;
  hint?: string;
  confirm: string;
  current?: string | null;
  askResume?: boolean;
  onCancel: () => void;
  onConfirm: (key: string, note: string, resume: boolean) => Promise<void>;
}> = ({ title, hint, confirm, current, askResume, onCancel, onConfirm }) => {
  const opts = useDispositionOptions();
  const [key, setKey] = useState<string>(current || '');
  const [note, setNote] = useState('');
  const [resume, setResume] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const go = async () => {
    if (!key) { setError('Choose an outcome first.'); return; }
    setBusy(true); setError(null);
    try { await onConfirm(key, note.trim(), resume); }
    catch (e: any) { setError(e.message || 'Something went wrong'); setBusy(false); }
  };
  const groups = ['positive', 'follow_up', 'negative', 'other'];
  return (
    <div className="fixed inset-0 z-50 bg-black/50 flex items-center justify-center p-4" onClick={onCancel}>
      <div className="w-full max-w-lg rounded-xl border border-slate-700 bg-slate-900 p-4 shadow-xl max-h-[90vh] overflow-y-auto"
        onClick={e => e.stopPropagation()}>
        <h3 className="text-[15px] font-semibold text-slate-100">{title}</h3>
        {hint && <p className="text-[12.5px] text-slate-400 mt-1">{hint}</p>}
        <div className="mt-3 space-y-2.5">
          {groups.map(g => (
            <div key={g}>
              <div className="text-[10.5px] uppercase tracking-wider text-slate-500 mb-1">{GROUP_LABEL[g]}</div>
              <div className="flex flex-wrap gap-1.5">
                {opts.filter(o => o.group === g).map(o => (
                  <button key={o.key} onClick={() => setKey(o.key)}
                    className={`px-2.5 py-1 rounded-full border text-[12px] cursor-pointer ${key === o.key
                      ? `${GROUP_STYLE[g]} ring-2 ring-sky-500` : 'border-slate-700 text-slate-300 hover:bg-slate-800'}`}>
                    {o.label}
                  </button>
                ))}
              </div>
            </div>
          ))}
        </div>
        <textarea value={note} onChange={e => setNote(e.target.value)} rows={2} maxLength={500}
          placeholder="Note (optional), e.g. call after 6 PM, asked about the devices"
          className="mt-3 w-full px-2.5 py-2 rounded-lg border border-slate-700 bg-slate-950 text-[13px] text-slate-200 outline-none focus:border-sky-500 resize-none" />
        {askResume && (
          <label className="mt-2 flex items-center gap-2 text-[12.5px] text-slate-300 cursor-pointer">
            <input type="checkbox" checked={resume} onChange={e => setResume(e.target.checked)} />
            The bot asks its last question again, so they carry on where they left off
          </label>
        )}
        {error && <div className="mt-2 text-[12px] text-rose-300">{error}</div>}
        <div className="mt-4 flex justify-end gap-2">
          <button onClick={onCancel} className="h-9 px-3 rounded-lg text-sm text-slate-400 hover:text-slate-200 cursor-pointer">Cancel</button>
          <button onClick={go} disabled={busy}
            className="h-9 px-4 rounded-lg bg-emerald-500 text-white text-sm font-semibold hover:opacity-90 disabled:opacity-50 cursor-pointer">
            {busy ? 'Saving…' : confirm}
          </button>
        </div>
      </div>
    </div>
  );
};

const who = (email: string | null) => email ? email.split('@')[0].replace(/[._]/g, ' ').replace(/\b\w/g, c => c.toUpperCase()) : 'Someone';

/** Who is handling the chat, the handover buttons, and the outcome. */
export const HandoverBar: React.FC<{
  conv: ConversationDetail;
  botActive: boolean;
  readOnly?: boolean;
  onChanged: () => void;
}> = ({ conv, botActive, readOnly, onChanged }) => {
  const opts = useDispositionOptions();
  const [dialog, setDialog] = useState<null | 'back' | 'record'>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const withPerson = conv.bot_paused && !!conv.handled_by;
  // The bot has something to carry on with: a step it waits at, in a chat from a campaign.
  const botCanCarryOn = conv.from_campaign && !!conv.bot_step;

  const takeOver = async () => {
    setBusy(true); setError(null);
    try { await handOver(conv.phone, 'person'); onChanged(); }
    catch (e: any) { setError(e.message); }
    finally { setBusy(false); }
  };

  return (
    <div className={`flex flex-wrap items-center gap-x-3 gap-y-1.5 px-3 py-1.5 border-b text-[12px] ${withPerson
      ? 'border-violet-800/60 bg-violet-950 text-violet-200' : 'border-slate-800 bg-slate-900 text-slate-400'}`}>
      <span className="inline-flex items-center gap-1.5 min-w-0">
        <span className="material-symbols-outlined text-[16px]">{withPerson ? 'support_agent' : botActive ? 'smart_toy' : 'chat'}</span>
        {withPerson
          ? <span><b className="font-semibold">{who(conv.handled_by)}</b> is handling this chat{conv.handled_since ? ` since ${formatDateTime(conv.handled_since)}` : ''}; the bot is quiet.</span>
          : botActive
            ? <span>The bot is handling this chat. A reply by hand takes it over.</span>
            : <span>{conv.bot_paused ? 'The bot is paused here.' : 'Nobody automatic answers here; reply by hand.'}</span>}
      </span>
      <span className="inline-flex items-center gap-1.5">
        <span className="text-slate-500">Outcome:</span>
        <DispositionChip d={conv.disposition} opts={opts} />
        {!readOnly && (
          <button onClick={() => setDialog('record')} className="text-sky-300 hover:underline cursor-pointer">Change</button>
        )}
      </span>
      <span className="flex-1" />
      {!readOnly && withPerson && botCanCarryOn && (
        <button onClick={() => setDialog('back')} disabled={busy}
          className="inline-flex items-center gap-1 px-2.5 py-1 rounded border border-emerald-700 bg-emerald-950 text-emerald-300 font-semibold hover:bg-emerald-900 cursor-pointer disabled:opacity-50">
          <span className="material-symbols-outlined text-[15px]">smart_toy</span>Hand back to the bot
        </button>
      )}
      {!readOnly && withPerson && !botCanCarryOn && (
        <button onClick={() => setDialog('back')} disabled={busy}
          className="inline-flex items-center gap-1 px-2.5 py-1 rounded border border-slate-700 text-slate-300 hover:bg-slate-800 cursor-pointer disabled:opacity-50">
          <span className="material-symbols-outlined text-[15px]">done_all</span>Done with this chat
        </button>
      )}
      {!readOnly && !withPerson && (
        <button onClick={takeOver} disabled={busy}
          className="inline-flex items-center gap-1 px-2.5 py-1 rounded border border-violet-700 text-violet-300 hover:bg-violet-950 cursor-pointer disabled:opacity-50">
          <span className="material-symbols-outlined text-[15px]">support_agent</span>Take over
        </button>
      )}
      {error && <span className="w-full text-rose-300">{error}</span>}

      {dialog === 'back' && (
        <DispositionDialog
          title={botCanCarryOn ? 'Hand the chat back to the bot' : 'Finish with this chat'}
          hint={botCanCarryOn ? 'Record how the chat stands; the bot then carries on, and any open ticket is solved.'
            : 'Record how the chat ended; any open ticket is solved.'}
          confirm={botCanCarryOn ? 'Hand back' : 'Save'} current={conv.disposition?.source === 'team' ? conv.disposition.key : null}
          askResume={botCanCarryOn}
          onCancel={() => setDialog(null)}
          onConfirm={async (key, note, resume) => {
            await handOver(conv.phone, 'bot', key, note, botCanCarryOn && resume);
            setDialog(null); onChanged();
          }} />
      )}
      {dialog === 'record' && (
        <DispositionDialog title="Record the outcome of this chat" confirm="Save"
          current={conv.disposition?.key}
          onCancel={() => setDialog(null)}
          onConfirm={async (key, note) => { await recordDisposition(conv.phone, key, note); setDialog(null); onChanged(); }} />
      )}
    </div>
  );
};
