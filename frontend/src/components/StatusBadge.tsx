import React from 'react';
import type { JobStatus } from '../types/api';

interface StatusBadgeProps {
  status: JobStatus | string;
  showDot?: boolean;
}

export const StatusBadge: React.FC<StatusBadgeProps> = ({ status, showDot = false }) => {
  const normalized = (status || '').toUpperCase();

  const getStyle = () => {
    switch (normalized) {
      case 'COMPLETED':
        return 'bg-emerald-950/70 border-emerald-800 text-emerald-300';
      case 'RUNNING':
        return 'bg-sky-950/70 border-sky-800 text-sky-300';
      case 'PARTIAL':
        return 'bg-amber-950/70 border-amber-800 text-amber-300';
      case 'FAILED':
        return 'bg-rose-950/70 border-rose-800 text-rose-300';
      case 'BLOCKED':
        return 'bg-purple-950/70 border-purple-800 text-purple-300';
      case 'PENDING':
      default:
        return 'bg-slate-900 border-slate-700 text-slate-300';
    }
  };

  const getDotColor = () => {
    switch (normalized) {
      case 'COMPLETED':
        return 'bg-emerald-400';
      case 'RUNNING':
        return 'bg-sky-400 pulse-glow';
      case 'PARTIAL':
        return 'bg-amber-400';
      case 'FAILED':
        return 'bg-rose-400';
      case 'BLOCKED':
        return 'bg-purple-400';
      case 'PENDING':
      default:
        return 'bg-slate-400';
    }
  };

  return (
    <span
      className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded text-[11px] font-mono-code font-semibold border ${getStyle()} select-none`}
    >
      {(showDot || normalized === 'RUNNING') && (
        <span className={`w-1.5 h-1.5 rounded-full ${getDotColor()}`} />
      )}
      <span>{normalized}</span>
    </span>
  );
};
