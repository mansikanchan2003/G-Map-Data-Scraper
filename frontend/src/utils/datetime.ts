/**
 * Timestamp formatting for the dashboard.
 *
 * The API returns timezone-aware UTC (e.g. "2026-09-24T07:21:17.764586+00:00").
 * Slicing that string drops the "+00:00" and shows UTC digits as though they
 * were local, which is how a run at 12:51 PM IST came to display as 07:21.
 * Parsing it as a Date and letting the browser format it keeps the offset.
 */

/** Date and time in the viewer's own timezone. */
export const formatDateTime = (iso?: string | null): string => {
  if (!iso) return '—';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '—';
  return d.toLocaleString(undefined, {
    year: 'numeric',
    month: 'short',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  });
};

/** Time only, for dense tables where the date is already obvious. */
export const formatTime = (iso?: string | null): string => {
  if (!iso) return '—';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '—';
  return d.toLocaleTimeString(undefined, {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  });
};

/** The viewer's timezone, so a displayed time is never ambiguous. */
export const localTimeZone = (): string => {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || 'local time';
  } catch {
    return 'local time';
  }
};
