import React from 'react';
import type { Theme } from '../hooks/useTheme';

interface ThemeToggleProps {
  theme: Theme;
  onToggle: () => void;
}

/**
 * Two-state switch for the dashboard theme.
 * Both options stay visible so the current mode is readable at a glance
 * rather than having to infer it from the icon.
 */
export const ThemeToggle: React.FC<ThemeToggleProps> = ({ theme, onToggle }) => {
  const isDark = theme === 'dark';

  return (
    <button
      onClick={onToggle}
      title={isDark ? 'Switch to light theme' : 'Switch to dark theme'}
      aria-label={isDark ? 'Switch to light theme' : 'Switch to dark theme'}
      aria-pressed={!isDark}
      className="h-8 flex items-center gap-0.5 bg-slate-900 border border-slate-700 rounded-full p-0.5 transition-colors hover:border-slate-600"
    >
      <span
        className={`flex items-center gap-1 px-2 py-1 rounded-full text-[11px] font-semibold transition-colors ${
          isDark ? 'bg-slate-700 text-slate-100' : 'text-slate-500'
        }`}
      >
        <span className="material-symbols-outlined text-[14px]">dark_mode</span>
        Dark
      </span>
      <span
        className={`flex items-center gap-1 px-2 py-1 rounded-full text-[11px] font-semibold transition-colors ${
          // Eko's gold, set literally so the active pill reads the same in
          // both themes rather than following the remapped amber ramp.
          !isDark ? 'bg-[#f9ab10] text-[#0c2531]' : 'text-slate-500'
        }`}
      >
        <span className="material-symbols-outlined text-[14px]">light_mode</span>
        Light
      </span>
    </button>
  );
};
