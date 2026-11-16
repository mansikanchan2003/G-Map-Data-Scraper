import { useCallback, useEffect, useState } from 'react';

export type Theme = 'dark' | 'light';

// Light is the default for everyone (the user, 16 Nov 2026); only a theme the
// person picks with the Dark / Light switch is remembered. The old key saved
// the theme on every visit, so it held "dark" for people who never chose it:
// it is not read any more.
const STORAGE_KEY = 'gmap-theme-choice';
const DEFAULT_THEME: Theme = 'light';

const readStoredTheme = (): Theme => {
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored === 'light' || stored === 'dark') return stored;
  } catch {
    // Storage can throw in private mode or when site data is blocked.
  }
  return DEFAULT_THEME;
};

const remember = (theme: Theme) => {
  try {
    localStorage.setItem(STORAGE_KEY, theme);
  } catch {
    // Remembering is a convenience; the theme still applies for this session.
  }
};

const applyTheme = (theme: Theme) => {
  document.documentElement.setAttribute('data-theme', theme);
};

export const useTheme = () => {
  const [theme, setThemeState] = useState<Theme>(readStoredTheme);

  useEffect(() => {
    applyTheme(theme);
  }, [theme]);

  const setTheme = useCallback((next: Theme) => {
    remember(next);
    setThemeState(next);
  }, []);
  const toggleTheme = useCallback(
    () => setThemeState(prev => {
      const next = prev === 'dark' ? 'light' : 'dark';
      remember(next);
      return next;
    }),
    []
  );

  return { theme, setTheme, toggleTheme };
};
