import React from 'react';

/**
 * How interested someone is: by rules from what they did (interest_rules, 20 Nov 2026), or an
 * earlier Claude CLI read. After the 24-hour window only High and Medium get our reminders.
 */
export type InterestLevel = 'high' | 'medium' | 'low' | 'not_interested';
export interface Interest { level: InterestLevel; reason?: string | null; at?: string | null; by?: string | null }

export const INTEREST: Record<InterestLevel, { label: string; icon: string; chip: string }> = {
  high: { label: 'High interest', icon: 'local_fire_department', chip: 'bg-emerald-500/15 border-emerald-500/40 text-emerald-300' },
  medium: { label: 'Some interest', icon: 'trending_flat', chip: 'bg-amber-500/15 border-amber-500/40 text-amber-300' },
  low: { label: 'Low interest', icon: 'trending_down', chip: 'bg-slate-500/15 border-slate-500/40 text-slate-300' },
  not_interested: { label: 'Not interested', icon: 'do_not_disturb_on', chip: 'bg-rose-500/15 border-rose-500/40 text-rose-300' },
};

export const InterestChip: React.FC<{ interest?: Interest | null; withReason?: boolean }> = ({ interest, withReason }) => {
  if (!interest || !INTEREST[interest.level]) return null;
  const s = INTEREST[interest.level];
  return (
    <span className="inline-flex flex-col items-start gap-0.5 max-w-full">
      <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full border text-[11px] font-semibold whitespace-nowrap ${s.chip}`}
        title={`${interest.by === 'rules' ? 'AutoGMap, from what they did' : 'Claude CLI'}${interest.reason ? `: ${interest.reason}` : ''}. After the 24-hour window, only High and Some interest get our reminders.`}>
        <span className="material-symbols-outlined text-[13px]" aria-hidden="true">{s.icon}</span>{s.label}
      </span>
      {withReason && interest.reason && <span className="text-[11.5px] text-slate-400 leading-snug">{interest.reason}</span>}
    </span>
  );
};
