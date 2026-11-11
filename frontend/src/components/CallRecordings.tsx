import React, { useEffect, useState } from 'react';
import {
  fetchRecordings, fetchRecordingsSummary, recordingAudioUrl, recordingsExportUrl,
  type CallRecording, type RecordingsSummary,
} from '../api/inbox';

/**
 * Recordings of phone calls with one applicant, from the call-recorder app on
 * Kavya Ma'am's phone (11 Nov 2026): each call with its direction, time and
 * length, and a player. The header carries the totals and a zip of every
 * recording for Sumit's AI calling agent. Hidden for anyone who may not listen
 * (members), and when this person has no recordings.
 */

const Icon: React.FC<{ name: string; className?: string }> = ({ name, className = '' }) =>
  <span className={`material-symbols-outlined ${className}`} aria-hidden="true">{name}</span>;

const HERO = 'linear-gradient(120deg, #3b0764 0%, #6d28d9 55%, #8b5cf6 100%)';
const when = (iso: string | null) => iso
  ? new Date(iso).toLocaleString('en-IN', { timeZone: 'Asia/Kolkata', day: 'numeric', month: 'short', hour: 'numeric', minute: '2-digit' })
  : 'Time not sent';
const length = (s: number | null) => (s == null ? '' : s < 60 ? `${s}s` : `${Math.floor(s / 60)}m ${s % 60}s`);
const hours = (s: number) => (s < 3600 ? `${Math.round(s / 60)} min` : `${(s / 3600).toFixed(1)} hr`);

const DIRECTION = {
  in: { label: 'Unhone call kiya', icon: 'call_received', chip: 'bg-emerald-500/15 text-emerald-300 border-emerald-500/30' },
  out: { label: 'Humne call kiya', icon: 'call_made', chip: 'bg-sky-500/15 text-sky-300 border-sky-500/30' },
  none: { label: 'Call', icon: 'call', chip: 'bg-slate-500/15 text-slate-300 border-slate-500/30' },
} as const;

export const CallRecordingsCard: React.FC<{ phone: string; version?: string }> = ({ phone, version }) => {
  const [rows, setRows] = useState<CallRecording[] | null>(null);
  const [total, setTotal] = useState<RecordingsSummary | null>(null);

  useEffect(() => {
    let alive = true;
    fetchRecordings(phone).then(r => alive && setRows(r)).catch(() => alive && setRows([]));
    fetchRecordingsSummary().then(s => alive && setTotal(s)).catch(() => alive && setTotal(null));
    return () => { alive = false; };
  }, [phone, version]);

  // Members may not listen (the summary is refused for them); nothing to show without recordings.
  if (!rows || !rows.length || !total) return null;
  const seconds = rows.reduce((n, r) => n + (r.duration_seconds || 0), 0);

  return (
    <div className="rounded-xl overflow-hidden border border-slate-800 bg-slate-900 shadow-sm">
      <div className="px-4 py-3 text-white" style={{ background: HERO }}>
        <div className="flex items-center gap-2.5">
          <span className="h-8 w-8 rounded-lg bg-white/15 flex items-center justify-center shrink-0">
            <Icon name="graphic_eq" className="text-[19px]" />
          </span>
          <div className="min-w-0 flex-1">
            <div className="text-[13px] font-semibold leading-tight">Call recordings</div>
            <div className="text-[11px] text-white/75">
              {rows.length} {rows.length === 1 ? 'call' : 'calls'}{seconds ? ` · ${length(seconds)}` : ''} · Kavya Ma'am ke phone se
            </div>
          </div>
          <a href={recordingsExportUrl()} download
             className="shrink-0 inline-flex items-center gap-1 rounded-full bg-white/15 hover:bg-white/25 px-2.5 py-1 text-[11px] font-semibold transition-colors"
             title={`All ${total.recordings} recordings (${hours(total.seconds)}, ${total.people} people) as one zip, for Sumit's AI calling agent`}>
            <Icon name="download" className="text-[15px]" /> Sabki zip
          </a>
        </div>
      </div>
      <ul className="divide-y divide-slate-800">
        {rows.map(r => {
          const d = DIRECTION[r.direction || 'none'];
          return (
            <li key={r.recording_id} className="px-4 py-3">
              <div className="flex items-center gap-2 text-[12px]">
                <span className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 font-semibold ${d.chip}`}>
                  <Icon name={d.icon} className="text-[14px]" /> {d.label}
                </span>
                <span className="text-slate-400">{when(r.started_at)}</span>
                {r.duration_seconds != null && <span className="ml-auto text-slate-300 font-semibold tabular-nums">{length(r.duration_seconds)}</span>}
              </div>
              <audio controls preload="none" src={recordingAudioUrl(r.recording_id)} className="mt-2 w-full h-9" />
            </li>
          );
        })}
      </ul>
    </div>
  );
};
