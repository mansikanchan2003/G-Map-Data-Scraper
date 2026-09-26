import React from 'react';

/**
 * The dashboard's headline figures as small bar charts.
 *
 * They are drawn as two groups rather than one chart because they are not one
 * measure. Locations and categories are the dimensions of the search grid;
 * jobs and businesses are counts of work and of output. Putting all four on a
 * shared axis would invite a comparison that means nothing — and at 55 against
 * 7,831, the smallest bar would be under a percent of the longest and simply
 * disappear.
 *
 * So each group carries its own scale, which is the honest form for two
 * measures of different size: separate plots, never two axes on one.
 *
 * Bar length is the only thing encoding magnitude, so every bar keeps one hue.
 * Varying colour here would suggest an identity the rows do not have.
 */

export interface ScaleBar {
  key: string;
  label: string;
  value: number;
  /** Shown to the right of the value — the unit, or what the number is of. */
  note?: string;
  onClick?: () => void;
}

export interface ScaleBarGroup {
  title: string;
  bars: ScaleBar[];
}

interface Props {
  groups: ScaleBarGroup[];
}

// Below this a bar reads as an empty row rather than a small quantity.
const MIN_WIDTH_PCT = 2;

export const ScaleBars: React.FC<Props> = ({ groups }) => (
  <div className="flex flex-col gap-4">
    {groups.map(group => {
      // Each group is scaled to its own largest bar, so the shorter bar in the
      // pair stays readable instead of being crushed by an unrelated measure.
      const max = Math.max(...group.bars.map(b => b.value), 1);

      return (
        <div key={group.title} className="flex flex-col gap-2">
          <div className="text-[10px] font-mono-code uppercase tracking-wider text-slate-500 font-bold">
            {group.title}
          </div>

          {group.bars.map(b => {
            const pct = Math.max((b.value / max) * 100, b.value > 0 ? MIN_WIDTH_PCT : 0);
            const Row = b.onClick ? 'button' : 'div';
            return (
              <Row
                key={b.key}
                onClick={b.onClick}
                className={`w-full text-left group/bar ${b.onClick ? 'cursor-pointer' : ''}`}
              >
                <div className="flex items-baseline justify-between gap-2 mb-1">
                  <span className="text-xs text-slate-300 font-medium truncate">{b.label}</span>
                  <span className="flex items-baseline gap-1.5 shrink-0">
                    <span className="text-xs font-mono-code text-slate-100 font-semibold tabular-nums">
                      {b.value.toLocaleString()}
                    </span>
                    {b.note && (
                      <span className="text-[10px] font-mono-code text-slate-500">{b.note}</span>
                    )}
                  </span>
                </div>
                {/* The track keeps the row's shape while data loads, and gives
                    the shortest bar something to be short against. */}
                <div className="h-1.5 w-full rounded-sm overflow-hidden"
                     style={{ backgroundColor: 'var(--chart-track)' }}>
                  <div
                    className="h-full rounded-sm transition-all duration-300 group-hover/bar:opacity-80"
                    style={{ width: `${pct}%`, backgroundColor: 'var(--chart-accent)' }}
                  />
                </div>
              </Row>
            );
          })}
        </div>
      );
    })}
  </div>
);
