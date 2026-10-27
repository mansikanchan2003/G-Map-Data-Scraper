import React, { useCallback, useEffect, useState } from 'react';
import {
  fetchReferencePosters, realPhotoUrl, rereadReferencePoster, setReferencePosterActive, uploadReferencePoster,
} from '../api/whatsapp';
import type { ReferencePoster, StudioState } from '../api/whatsapp';
import { RealPhotoLibrary } from './RealPhotoLibrary';
import { formatDateTime } from '../utils/datetime';

/**
 * The Template Studio's reference gallery (the user, 2026-10-27): real CSP
 * photos the posters are set on, and posters the team likes, which the agents
 * follow in style. Opened from the top of the Studio, so it is never buried
 * under the drafts.
 */

const LAYOUT_NAMES: Record<string, string> = {
  classic: 'Photo on top, text below', list: 'Benefits as a list', banner: 'Full photo, text over it',
  mirror: 'Photo one side, text the other', spotlight: 'Big photo, small badge',
};

const PosterCard: React.FC<{ p: ReferencePoster; onChanged: () => void }> = ({ p, onChanged }) => {
  const [busy, setBusy] = useState(false);
  const act = async (fn: () => Promise<unknown>) => { setBusy(true); try { await fn(); onChanged(); } finally { setBusy(false); } };
  const reading = !p.read_at && !p.read_error;
  return (
    <div className={`rounded-xl border border-slate-800 bg-slate-900 overflow-hidden flex flex-col ${p.active ? '' : 'opacity-55'}`}>
      <div className="relative bg-slate-950">
        <img src={realPhotoUrl(p.media_id)} alt={p.note || 'Reference poster'} loading="lazy"
          className="w-full h-60 object-contain p-2" />
        {p.style?.layout && (
          <span className="absolute left-2 top-2 inline-flex items-center gap-1 rounded-full bg-slate-950/85 text-sky-300 px-2 py-0.5 text-[10.5px] font-semibold border border-sky-800/60">
            <span className="material-symbols-outlined text-[13px]">dashboard</span>{LAYOUT_NAMES[p.style.layout] || p.style.layout}
          </span>
        )}
        {!p.active && <span className="absolute right-2 top-2 rounded-full bg-slate-800 text-slate-300 px-2 py-0.5 text-[10.5px] font-semibold">Retired</span>}
      </div>
      <div className="p-3 space-y-2 text-[12px] flex-1 flex flex-col">
        {p.note && <div className="text-slate-100 font-semibold truncate" title={p.note}>{p.note}</div>}
        {p.palette && p.palette.length > 0 && (
          <div className="flex items-center gap-1" title={p.style?.colours || 'Main colours'}>
            {p.palette.map(c => <span key={c} className="h-4 w-4 rounded-full ring-1 ring-slate-700" style={{ background: c }} />)}
            {p.style?.colours && <span className="ml-1.5 text-slate-500 truncate">{p.style.colours}</span>}
          </div>
        )}
        {reading && (
          <div className="flex items-center gap-1.5 text-sky-300">
            <span className="material-symbols-outlined text-[15px] animate-spin">progress_activity</span>Reading its style…
          </div>
        )}
        {p.read_error && (
          <div className="rounded-lg border border-rose-800/60 bg-rose-950 text-rose-300 p-2">
            {p.read_error}
            <button onClick={() => act(() => rereadReferencePoster(p.poster_id))} disabled={busy}
              className="block mt-1.5 font-semibold underline cursor-pointer">Read again</button>
          </div>
        )}
        {p.style && (
          <>
            {p.style.headline_style && <div className="text-slate-300"><span className="text-slate-500">Headline · </span>{p.style.headline_style}</div>}
            {p.style.what_to_copy.length > 0 && (
              <ul className="space-y-1">
                {p.style.what_to_copy.map((w, i) => (
                  <li key={i} className="flex gap-1.5 text-slate-300">
                    <span className="material-symbols-outlined text-[14px] text-emerald-400 mt-px">check_circle</span>{w}
                  </li>
                ))}
              </ul>
            )}
          </>
        )}
        <div className="mt-auto pt-2 flex items-center justify-between gap-2 text-slate-500">
          <span className="truncate">{formatDateTime(p.created_at)}</span>
          <button onClick={() => act(() => setReferencePosterActive(p.poster_id, !p.active))} disabled={busy}
            className="h-7 px-2.5 rounded-md bg-slate-800 hover:bg-slate-700 border border-slate-700 text-slate-200 font-semibold cursor-pointer disabled:opacity-50">
            {p.active ? 'Retire' : 'Use again'}
          </button>
        </div>
      </div>
    </div>
  );
};

const ReferencePosters: React.FC<{ onCount: (n: number) => void }> = ({ onCount }) => {
  const [posters, setPosters] = useState<ReferencePoster[] | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const [note, setNote] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [inputKey, setInputKey] = useState(0);
  const load = useCallback(() => fetchReferencePosters().then(setPosters).catch(() => setPosters([])), []);
  useEffect(() => { load(); }, [load]);
  // While the vision model reads a new poster, look again every few seconds.
  const pending = (posters || []).some(p => !p.read_at && !p.read_error);
  useEffect(() => {
    if (!pending) return;
    const t = setInterval(load, 4000);
    return () => clearInterval(t);
  }, [pending, load]);
  const inUse = (posters || []).filter(p => p.active && p.style).length;
  useEffect(() => { if (posters) onCount(inUse); }, [posters, inUse, onCount]);

  const upload = async () => {
    if (!file) return;
    setBusy(true); setError(null);
    try {
      await uploadReferencePoster(file, note);
      setFile(null); setNote(''); setInputKey(k => k + 1);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Upload failed');
    } finally { setBusy(false); }
  };

  return (
    <div className="space-y-4 text-xs">
      <p className="text-slate-400">
        Upload posters you like, ours or anyone's. Each is read once for its layout, headline style, amount of text
        and what makes it work; the agents write new posters in that style (never copying its words), and the first
        draft of each round takes the layout most of these are closest to. Eko's colours and logo stay as they are.
      </p>
      <div className="grid gap-2 md:grid-cols-[1fr_1fr_auto] items-center bg-slate-900/60 border border-slate-800 rounded-lg p-3">
        <input key={inputKey} type="file" accept="image/jpeg,image/png,image/webp" onChange={e => setFile(e.target.files?.[0] || null)}
          className="block w-full text-slate-300 file:mr-3 file:h-8 file:px-3 file:rounded file:border-0 file:bg-slate-700 file:text-slate-100 file:text-xs file:font-semibold" />
        <input value={note} onChange={e => setNote(e.target.value)} maxLength={300} placeholder="What you like about it (optional)"
          className="h-8 px-2 bg-slate-950 border border-slate-700 rounded text-slate-200" />
        <button onClick={upload} disabled={!file || busy}
          className="h-8 px-4 bg-amber-500 hover:bg-amber-400 text-slate-950 font-semibold rounded disabled:opacity-40 cursor-pointer">
          {busy ? 'Uploading…' : 'Add poster'}
        </button>
        {error && <div className="md:col-span-3 text-rose-300">{error}</div>}
      </div>
      {posters && posters.length === 0 && (
        <div className="rounded-xl border border-dashed border-slate-700 p-8 text-center text-slate-500">
          <span className="material-symbols-outlined text-[32px] block mb-1">imagesmode</span>
          No reference posters yet. The agents use their own layouts in turn until you add some.
        </div>
      )}
      {posters && posters.length > 0 && (
        <div className="grid gap-3 grid-cols-1 sm:grid-cols-2 lg:grid-cols-3">
          {posters.map(p => <PosterCard key={p.poster_id} p={p} onChanged={load} />)}
        </div>
      )}
    </div>
  );
};

export const ReferenceGallery: React.FC<{ states: StudioState[]; onClose: () => void }> = ({ states, onClose }) => {
  const [tab, setTab] = useState<'photos' | 'posters'>('photos');
  const [counts, setCounts] = useState<{ photos: number | null; posters: number | null }>({ photos: null, posters: null });
  const setPhotos = useCallback((n: number) => setCounts(c => ({ ...c, photos: n })), []);
  const setPosters = useCallback((n: number) => setCounts(c => ({ ...c, posters: n })), []);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);
  const tabs: ['photos' | 'posters', string, string, number | null][] = [
    ['photos', 'Real CSP photos', 'add_a_photo', counts.photos],
    ['posters', 'Reference posters', 'imagesmode', counts.posters],
  ];
  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-black/60" onClick={onClose}>
      <div onClick={e => e.stopPropagation()}
        className="h-full w-full max-w-5xl bg-slate-950 border-l border-slate-800 shadow-2xl flex flex-col">
        <div className="relative px-6 py-5 text-white" style={{ background: 'linear-gradient(120deg, #0a3543 0%, #16435a 55%, #1d5a6e 100%)' }}>
          <button onClick={onClose} aria-label="Close"
            className="absolute right-4 top-4 h-8 w-8 grid place-items-center rounded-full bg-white/10 hover:bg-white/20 cursor-pointer">
            <span className="material-symbols-outlined text-[18px]">close</span>
          </button>
          <div className="flex items-center gap-3">
            <div className="h-11 w-11 rounded-xl bg-white/15 grid place-items-center">
              <span className="material-symbols-outlined text-[24px]">photo_library</span>
            </div>
            <div>
              <div className="text-[19px] font-semibold">Reference gallery</div>
              <div className="text-[12.5px] text-white/75">What the posters are built from: real outlet photos, and posters the team wants them to look like.</div>
            </div>
          </div>
          <div className="mt-4 flex gap-2">
            {tabs.map(([k, label, icon, n]) => (
              <button key={k} onClick={() => setTab(k)}
                className={`inline-flex items-center gap-1.5 px-3.5 py-2 rounded-lg text-[12.5px] font-semibold cursor-pointer transition ${tab === k
                  ? 'bg-white text-[#0a3543]' : 'bg-white/10 text-white/85 hover:bg-white/20'}`}>
                <span className="material-symbols-outlined text-[17px]">{icon}</span>{label}
                {n !== null && <span className={`ml-0.5 rounded-full px-1.5 text-[11px] ${tab === k ? 'bg-[#0a3543]/10' : 'bg-white/15'}`}>{n} in use</span>}
              </button>
            ))}
          </div>
        </div>
        <div className="flex-1 overflow-y-auto p-6">
          {/* Both stay mounted, so each tab's count shows before it is opened. */}
          <div className={tab === 'photos' ? '' : 'hidden'}><RealPhotoLibrary states={states} bare onCount={setPhotos} /></div>
          <div className={tab === 'posters' ? '' : 'hidden'}><ReferencePosters onCount={setPosters} /></div>
        </div>
      </div>
    </div>
  );
};
