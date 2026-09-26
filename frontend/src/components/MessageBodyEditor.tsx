import React, { useRef, useState } from 'react';

/**
 * The message body, with the formatting WhatsApp actually understands.
 *
 * WhatsApp has no rich-text format: bold is a pair of asterisks in the text
 * itself, and that is exactly what Meta stores. So this edits plain text and
 * inserts the markers, rather than keeping hidden state that would have to be
 * serialised back into the same characters anyway.
 *
 * The variable list is deliberately short. Only the placeholders the send path
 * can resolve are offered — anything else would survive into the template Meta
 * approves and then arrive in the recipient's message as literal text.
 */

interface Props {
  value: string;
  onChange: (next: string) => void;
  placeholder?: string;
}

/** The only placeholders whatsapp_service can substitute at send time. */
const VARIABLES: { token: string; label: string; hint: string }[] = [
  { token: '{{name}}', label: 'Business name', hint: "The recipient's business name" },
  { token: '{{link}}', label: 'Tracking link', hint: 'Per-recipient link to the campaign page' },
];

const FORMATS: { key: string; icon: string; title: string; wrap: [string, string] }[] = [
  { key: 'bold', icon: 'format_bold', title: 'Bold  *text*', wrap: ['*', '*'] },
  { key: 'italic', icon: 'format_italic', title: 'Italic  _text_', wrap: ['_', '_'] },
  { key: 'strike', icon: 'strikethrough_s', title: 'Strikethrough  ~text~', wrap: ['~', '~'] },
  { key: 'mono', icon: 'code', title: 'Monospace  ```text```', wrap: ['```', '```'] },
];

const EMOJI_GROUPS: { name: string; emoji: string[] }[] = [
  { name: 'Common', emoji: ['🙏', '👍', '✅', '✨', '🎉', '🔥', '⭐', '❗', '❓', '💯', '👉', '📌'] },
  { name: 'Business', emoji: ['🏦', '🏪', '💼', '💰', '💳', '📈', '📊', '🧾', '🤝', '🏆', '🎯', '🛒'] },
  { name: 'Contact', emoji: ['📞', '📱', '💬', '✉️', '📧', '🔗', '📍', '🕒', '📅', '🚀', '⚡', '🔔'] },
];

export const MessageBodyEditor: React.FC<Props> = ({ value, onChange, placeholder }) => {
  const ref = useRef<HTMLTextAreaElement>(null);
  const [emojiOpen, setEmojiOpen] = useState(false);
  const [varsOpen, setVarsOpen] = useState(false);

  /**
   * Replaces the current selection and puts the caret back where the writer
   * expects it — inside the markers when nothing was selected, after the
   * inserted text when something was.
   */
  const spliceAtCursor = (before: string, after: string, fallbackInside = '') => {
    const el = ref.current;
    if (!el) return;

    const start = el.selectionStart;
    const end = el.selectionEnd;
    const selected = value.slice(start, end);
    const inner = selected || fallbackInside;
    const next = value.slice(0, start) + before + inner + after + value.slice(end);

    onChange(next);

    // The value lands on the next render, so the caret is restored after it.
    requestAnimationFrame(() => {
      el.focus();
      const caret = selected
        ? start + before.length + inner.length + after.length
        : start + before.length + inner.length;
      el.setSelectionRange(caret, caret);
    });
  };

  const insert = (text: string) => spliceAtCursor(text, '');

  return (
    <div className="border border-slate-700 rounded overflow-hidden focus-within:border-emerald-500 transition-colors">
      <div className="flex items-center gap-0.5 px-1.5 py-1 bg-slate-900 border-b border-slate-800 relative">
        {FORMATS.map(f => (
          <button
            key={f.key}
            type="button"
            title={f.title}
            onClick={() => spliceAtCursor(f.wrap[0], f.wrap[1], 'text')}
            className="w-7 h-7 flex items-center justify-center rounded text-slate-400
                       hover:text-slate-100 hover:bg-slate-800 transition-colors cursor-pointer"
          >
            <span className="material-symbols-outlined text-[17px]">{f.icon}</span>
          </button>
        ))}

        <span className="w-px h-4 bg-slate-700 mx-1" />

        {/* Emoji */}
        <button
          type="button"
          title="Insert emoji"
          onClick={() => { setEmojiOpen(v => !v); setVarsOpen(false); }}
          className={`w-7 h-7 flex items-center justify-center rounded transition-colors cursor-pointer
                      ${emojiOpen ? 'text-amber-300 bg-slate-800' : 'text-slate-400 hover:text-slate-100 hover:bg-slate-800'}`}
        >
          <span className="material-symbols-outlined text-[17px]">mood</span>
        </button>

        {/* Variables */}
        <button
          type="button"
          title="Insert a variable"
          onClick={() => { setVarsOpen(v => !v); setEmojiOpen(false); }}
          className={`h-7 px-2 flex items-center gap-1 rounded text-[11px] font-mono-code transition-colors cursor-pointer
                      ${varsOpen ? 'text-sky-300 bg-slate-800' : 'text-slate-400 hover:text-slate-100 hover:bg-slate-800'}`}
        >
          <span className="material-symbols-outlined text-[15px]">data_object</span>
          Variable
        </button>

        <span className="ml-auto text-[10px] text-slate-600 pr-1 tabular-nums">
          {value.length}
        </span>

        {emojiOpen && (
          <div className="absolute top-full left-0 mt-1 z-20 w-64 bg-slate-900 border border-slate-700
                          rounded shadow-xl p-2 flex flex-col gap-2">
            {EMOJI_GROUPS.map(g => (
              <div key={g.name}>
                <div className="text-[10px] uppercase tracking-wider text-slate-500 mb-1">{g.name}</div>
                <div className="grid grid-cols-6 gap-0.5">
                  {g.emoji.map(e => (
                    <button
                      key={e}
                      type="button"
                      onClick={() => { insert(e); setEmojiOpen(false); }}
                      className="h-8 rounded text-lg hover:bg-slate-800 transition-colors cursor-pointer"
                    >
                      {e}
                    </button>
                  ))}
                </div>
              </div>
            ))}
          </div>
        )}

        {varsOpen && (
          <div className="absolute top-full left-0 mt-1 z-20 w-72 bg-slate-900 border border-slate-700
                          rounded shadow-xl p-1.5 flex flex-col gap-0.5">
            {VARIABLES.map(v => (
              <button
                key={v.token}
                type="button"
                onClick={() => { insert(v.token); setVarsOpen(false); }}
                className="text-left px-2 py-1.5 rounded hover:bg-slate-800 transition-colors cursor-pointer"
              >
                <div className="flex items-center gap-2">
                  <span className="font-mono-code text-xs text-sky-400">{v.token}</span>
                  <span className="text-xs text-slate-300">{v.label}</span>
                </div>
                <div className="text-[10px] text-slate-500 mt-0.5">{v.hint}</div>
              </button>
            ))}
            <p className="text-[10px] text-slate-500 px-2 py-1.5 border-t border-slate-800 mt-0.5">
              Only these two are filled in when sending. Any other {'{{...}}'} is
              sent to the recipient exactly as written.
            </p>
          </div>
        )}
      </div>

      <textarea
        ref={ref}
        value={value}
        onChange={e => onChange(e.target.value)}
        onClick={() => { setEmojiOpen(false); setVarsOpen(false); }}
        className="w-full bg-slate-950 px-3 py-2 text-sm text-slate-200 outline-none h-40 resize-y block"
        placeholder={placeholder}
      />
    </div>
  );
};
