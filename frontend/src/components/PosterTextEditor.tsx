import React from 'react';
import type { StudioPoster } from '../api/whatsapp';

// The poster fields a reviewer is most likely to reword, in reading order.
export const POSTER_EDIT_FIELDS: { key: keyof StudioPoster; label: string }[] = [
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

/** Only what the reviewer changed, ready to send as an edit; empty when nothing did. */
export const posterChanges = (original: Partial<StudioPoster> | undefined, fields: Partial<StudioPoster>): Partial<StudioPoster> => {
  const changed: Partial<StudioPoster> = {};
  if (!original) return changed;
  POSTER_EDIT_FIELDS.forEach(({ key }) => {
    if ((fields[key] ?? '') !== (original[key] ?? '')) (changed as any)[key] = fields[key];
  });
  if (JSON.stringify(fields.benefits) !== JSON.stringify(original.benefits)) changed.benefits = fields.benefits;
  return changed;
};

/**
 * The text on a draft's poster, to correct before approving.
 *
 * Saving sets the poster again on the same photo, so no image allowance is
 * spent, and the agent is shown each correction before it writes again.
 */
export const PosterTextEditor: React.FC<{
  fields: Partial<StudioPoster>;
  onChange: (next: Partial<StudioPoster>) => void;
  inputClassName: string;
}> = ({ fields, onChange, inputClassName }) => (
  <div className="flex flex-col gap-2 text-xs text-slate-400">
    <div className="font-semibold text-slate-200">Text on the image</div>
    <div className="text-[11px] text-slate-500">
      Saving puts this text on the same photo again: no new image is made, and the agent learns from what you changed.
    </div>
    {POSTER_EDIT_FIELDS.filter(({ key }) => fields[key] !== undefined).map(({ key, label }) => (
      <label key={key} className="flex flex-col gap-1">{label}
        <input value={(fields[key] as string) || ''} className={inputClassName}
          onChange={e => onChange({ ...fields, [key]: e.target.value })} />
      </label>
    ))}
    {(fields.benefits || []).map((b, i) => (
      <label key={i} className="flex flex-col gap-1">Benefit {i + 1}
        <input value={b.text} className={inputClassName} onChange={e => onChange({
          ...fields, benefits: (fields.benefits || []).map((x, j) => j === i ? { ...x, text: e.target.value } : x),
        })} />
      </label>
    ))}
  </div>
);
