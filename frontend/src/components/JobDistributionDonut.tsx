import React, { useState } from 'react';

/**
 * Job pipeline as a part-to-whole donut.
 *
 * Colours come from the reserved status palette — good / warning / critical —
 * because these slices name states, not arbitrary series. "Blocked" is not one
 * of those four states, so it takes a categorical violet; pairing it with the
 * warning amber instead put two hues 13.6 ΔE apart, below the 15 floor where
 * full-colour readers stop being able to separate them.
 *
 * "Pending" is deliberately the recessive grey: it is the work still to come,
 * the context the finished states are read against, not a condition.
 *
 * Every slice is labelled with its count and share, so identity never rests on
 * colour alone — which is also the relief the amber needs, sitting below 3:1
 * on a white surface.
 */

export interface DistributionSlice {
  key: string;
  label: string;
  value: number;
  /** CSS custom property holding this state's colour in both themes. */
  colorVar: string;
}

interface Props {
  slices: DistributionSlice[];
  total: number;
  /** The share the dashboard leads with, shown inside the ring. */
  heroValue: string;
  heroLabel: string;
  onSliceClick?: (key: string) => void;
}

const RADIUS = 66;
const STROKE = 22;
const CIRCUMFERENCE = 2 * Math.PI * RADIUS;
// A hairline of surface between arcs, so neighbouring fills never touch.
const GAP_DEG = 1.4;

export const JobDistributionDonut: React.FC<Props> = ({
  slices, total, heroValue, heroLabel, onSliceClick,
}) => {
  const [hovered, setHovered] = useState<string | null>(null);

  // A zero-value state cannot be drawn, but it still belongs in the legend:
  // "0 blocked" is a result, not an absence of information.
  const drawn = slices.filter(s => s.value > 0);

  let cursor = 0;
  const arcs = drawn.map(s => {
    const share = total > 0 ? s.value / total : 0;
    const degrees = share * 360;
    const arc = {
      ...s,
      share,
      // Trim the gap off the arc itself rather than the geometry, so the
      // shares stay true to the data.
      dash: Math.max(0, (degrees - GAP_DEG) / 360) * CIRCUMFERENCE,
      offset: -(cursor / 360) * CIRCUMFERENCE,
      rotation: cursor,
    };
    cursor += degrees;
    return arc;
  });

  const active = hovered ? arcs.find(a => a.key === hovered) : null;

  return (
    <div className="flex flex-col lg:flex-row items-center gap-6">
      <div className="relative shrink-0">
        <svg width="180" height="180" viewBox="0 0 180 180" role="img"
             aria-label={`Job distribution: ${slices.map(s => `${s.label} ${s.value}`).join(', ')}`}>
          {/* Track, so the ring keeps its shape while data loads */}
          <circle cx="90" cy="90" r={RADIUS} fill="none"
                  stroke="var(--chart-track)" strokeWidth={STROKE} />

          {arcs.map(a => (
            <circle
              key={a.key}
              cx="90" cy="90" r={RADIUS} fill="none"
              strokeWidth={hovered === a.key ? STROKE + 4 : STROKE}
              strokeDasharray={`${a.dash} ${CIRCUMFERENCE}`}
              strokeDashoffset={a.offset}
              transform="rotate(-90 90 90)"
              stroke={`var(${a.colorVar})`}
              className="transition-all duration-200 cursor-pointer"
              onMouseEnter={() => setHovered(a.key)}
              onMouseLeave={() => setHovered(null)}
              onClick={() => onSliceClick?.(a.key)}
            />
          ))}
        </svg>

        {/* The headline number lives in the hole rather than beside it */}
        <div className="absolute inset-0 flex flex-col items-center justify-center pointer-events-none">
          {active ? (
            <>
              <span className="text-2xl font-bold text-slate-100 leading-none">
                {(active.share * 100).toFixed(1)}%
              </span>
              <span className="text-[10px] uppercase tracking-wider text-slate-400 mt-1">
                {active.label}
              </span>
              <span className="text-[11px] font-mono-code text-slate-500 mt-0.5">
                {active.value.toLocaleString()}
              </span>
            </>
          ) : (
            <>
              <span className="text-2xl font-bold text-slate-100 leading-none">{heroValue}</span>
              <span className="text-[10px] uppercase tracking-wider text-slate-400 mt-1">{heroLabel}</span>
              <span className="text-[11px] font-mono-code text-slate-500 mt-0.5">
                {total.toLocaleString()} jobs
              </span>
            </>
          )}
        </div>
      </div>

      {/* Legend doubles as the table view: every state, its count and its share */}
      <div className="flex-1 w-full grid grid-cols-1 sm:grid-cols-2 gap-x-6 gap-y-1.5">
        {slices.map(s => {
          const share = total > 0 ? (s.value / total) * 100 : 0;
          const dimmed = hovered !== null && hovered !== s.key;
          return (
            <button
              key={s.key}
              onMouseEnter={() => s.value > 0 && setHovered(s.key)}
              onMouseLeave={() => setHovered(null)}
              onClick={() => onSliceClick?.(s.key)}
              className={`flex items-center gap-2.5 py-1 text-left transition-opacity ${
                dimmed ? 'opacity-40' : 'opacity-100'
              } ${onSliceClick ? 'cursor-pointer' : 'cursor-default'}`}
            >
              <span className="w-2.5 h-2.5 rounded-sm shrink-0"
                    style={{ backgroundColor: `var(${s.colorVar})` }} />
              <span className="text-xs text-slate-300 font-medium flex-1 truncate">{s.label}</span>
              <span className="text-xs font-mono-code text-slate-100 font-semibold tabular-nums">
                {s.value.toLocaleString()}
              </span>
              <span className="text-[11px] font-mono-code text-slate-500 tabular-nums w-12 text-right">
                {share.toFixed(1)}%
              </span>
            </button>
          );
        })}
      </div>
    </div>
  );
};
