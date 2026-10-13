import React from 'react';

/**
 * What the checker found wrong with a draft, where a reviewer cannot miss it.
 *
 * These used to be one small amber line under the draft, and a Gujarati
 * template went to Meta with Hindi, Punjabi and Bengali letters in it and
 * four claims the fact sheet does not support. Each problem is now its own
 * line, grouped by kind, at the top of the draft.
 */

const kindOf = (note: string): 'script' | 'claim' | 'other' => {
  if (/characters \(|has no \w+ text/.test(note)) return 'script';
  if (note.startsWith('unsupported claim')) return 'claim';
  return 'other';
};

const GROUPS: { key: 'script' | 'claim' | 'other'; title: string; hint: string }[] = [
  { key: 'script', title: 'Wrong script', hint: 'Letters from another language. Recipients see these as mistakes.' },
  { key: 'claim', title: 'Claims the fact sheet does not support', hint: 'Meta or the bank may object; reword or remove them.' },
  { key: 'other', title: 'Other problems', hint: '' },
];

export const CheckerNotes: React.FC<{ notes?: string[] | null }> = ({ notes }) => {
  const list = (notes || []).filter(Boolean);
  if (!list.length) return null;
  return (
    <div className="rounded border border-rose-800 bg-rose-950/50 p-3 text-xs space-y-2">
      <div className="flex items-center gap-1.5 font-semibold text-rose-300">
        <span className="material-symbols-outlined text-[16px]">error</span>
        The checker found {list.length} problem{list.length > 1 ? 's' : ''}. Edit the text, or reject, before approving.
      </div>
      {GROUPS.map(g => {
        const items = list.filter(n => kindOf(n) === g.key);
        if (!items.length) return null;
        return (
          <div key={g.key}>
            <div className="text-rose-200 font-semibold">{g.title} ({items.length})</div>
            {g.hint && <div className="text-rose-300/70">{g.hint}</div>}
            <ul className="list-disc pl-5 mt-1 space-y-0.5 text-rose-100 select-text">
              {items.map((n, i) => <li key={i} className="break-words">{n}</li>)}
            </ul>
          </div>
        );
      })}
    </div>
  );
};

/** The tick a reviewer gives to approve a draft that still has problems. */
export const ApproveAnyway: React.FC<{ count: number; checked: boolean; onChange: (v: boolean) => void }> = ({ count, checked, onChange }) => {
  if (!count) return null;
  return (
    <label className="flex items-center gap-2 text-xs text-rose-200 cursor-pointer">
      <input type="checkbox" checked={checked} onChange={e => onChange(e.target.checked)} className="accent-rose-500" />
      I have read the {count} problem{count > 1 ? 's' : ''} above and want to submit it to Meta anyway
    </label>
  );
};
