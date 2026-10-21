import React, { useEffect, useState } from 'react';
import { fetchRealPhotos, realPhotoUrl, setRealPhotoActive, uploadRealPhoto } from '../api/whatsapp';
import type { RealPhoto, StudioState } from '../api/whatsapp';
import { CollapsiblePanel } from './CollapsiblePanel';
import { formatDateTime } from '../utils/datetime';

/**
 * Real photos of SBI Customer Service Points for the posters.
 *
 * The AI photos looked AI-made and showed no CSP, so a poster is set on one
 * of these first; the AI photo is made only when no real photo is left for
 * the state. A photo is retired rather than deleted, so drafts made from it
 * keep their image.
 */
export const RealPhotoLibrary: React.FC<{ states: StudioState[] }> = ({ states }) => {
  const [photos, setPhotos] = useState<RealPhoto[] | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const [state, setState] = useState('');
  const [note, setNote] = useState('');
  const [consent, setConsent] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [inputKey, setInputKey] = useState(0);

  const load = () => fetchRealPhotos().then(setPhotos).catch(() => setPhotos([]));
  useEffect(() => { load(); }, []);

  const upload = async () => {
    if (!file) return;
    setBusy(true);
    setError(null);
    try {
      await uploadRealPhoto(file, state, note, consent);
      setFile(null); setNote(''); setConsent(false); setInputKey(k => k + 1);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Upload failed');
    } finally {
      setBusy(false);
    }
  };

  const toggle = async (p: RealPhoto) => {
    try {
      await setRealPhotoActive(p.photo_id, !p.active);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not change the photo');
    }
  };

  const inUse = (photos || []).filter(p => p.active).length;
  return (
    <CollapsiblePanel icon="add_a_photo" iconClass="text-amber-400" title="Real CSP photos"
      badge={<span className="text-xs text-slate-500">{photos === null ? '' : inUse ? `${inUse} in use` : 'none yet: posters use AI photos'}</span>}>
      <div className="space-y-4 text-xs">
        <p className="text-slate-400">
          Posters are set on a real photo of an SBI Customer Service Point first: one for the draft's state, or one
          marked for any state. Photos take turns, and <span className="text-slate-300">New photo</span> moves to the next.
          An AI photo is made only when there is no real one. Landscape photos showing the counter, the operator and
          the SBI signboard work best.
        </p>

        <div className="grid gap-3 md:grid-cols-[1fr_180px] items-start bg-slate-900/60 border border-slate-800 rounded p-3">
          <div className="space-y-2">
            <input key={inputKey} type="file" accept="image/jpeg,image/png,image/webp"
              onChange={e => setFile(e.target.files?.[0] || null)}
              className="block w-full text-slate-300 file:mr-3 file:h-8 file:px-3 file:rounded file:border-0 file:bg-slate-700 file:text-slate-100 file:text-xs file:font-semibold" />
            <input value={note} onChange={e => setNote(e.target.value)} maxLength={300}
              placeholder="Where it was taken, e.g. Eko CSP, Anand, Gujarat"
              className="w-full h-8 px-2 bg-slate-950 border border-slate-700 rounded text-slate-200" />
            <label className="flex items-start gap-2 text-slate-300">
              <input type="checkbox" checked={consent} onChange={e => setConsent(e.target.checked)} className="mt-0.5" />
              <span>The people in this photo agreed to it being used in Eko's posters.</span>
            </label>
          </div>
          <div className="space-y-2">
            <select value={state} onChange={e => setState(e.target.value)}
              className="w-full h-8 px-2 bg-slate-950 border border-slate-700 rounded text-slate-200">
              <option value="">Any state</option>
              {states.map(s => <option key={s.state} value={s.state}>{s.state}</option>)}
            </select>
            <button onClick={upload} disabled={!file || !consent || busy}
              className="w-full h-8 bg-amber-500 hover:bg-amber-400 text-slate-950 font-semibold rounded disabled:opacity-40">
              {busy ? 'Uploading…' : 'Add photo'}
            </button>
          </div>
          {error && <div className="md:col-span-2 text-rose-300">{error}</div>}
        </div>

        {photos && photos.length > 0 && (
          <div className="grid gap-3 grid-cols-2 md:grid-cols-4">
            {photos.map(p => (
              <div key={p.photo_id} className={`rounded border border-slate-800 overflow-hidden bg-slate-900 ${p.active ? '' : 'opacity-50'}`}>
                <img src={realPhotoUrl(p.media_id)} alt={p.note || 'CSP photo'} className="w-full aspect-[3/2] object-cover" loading="lazy" />
                <div className="p-2 space-y-1">
                  <div className="text-slate-200 font-semibold">{p.state || 'Any state'}</div>
                  {p.note && <div className="text-slate-400 truncate" title={p.note}>{p.note}</div>}
                  <div className="text-slate-500">
                    Used {p.times_used}×{p.last_used_at ? `, last ${formatDateTime(p.last_used_at)}` : ''}
                  </div>
                  <button onClick={() => toggle(p)}
                    className="h-7 px-2 bg-slate-800 hover:bg-slate-700 border border-slate-700 text-slate-200 rounded">
                    {p.active ? 'Retire' : 'Use again'}
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </CollapsiblePanel>
  );
};
