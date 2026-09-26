import React, { useState } from 'react';
import { resolveLocation, createLocation } from '../api';
import type { LocationItem } from '../types/api';

/**
 * Adds a target PIN to the matrix.
 *
 * The spreadsheets seeded the first 54 locations; this is how the list grows
 * past them as the business expands into new geography.
 *
 * State and district are required. Every business discovered at a location
 * copies them, so a PIN saved without them produces rows that can never be
 * filtered by state or district afterwards — which is exactly what went wrong
 * with locations added before this form existed. "Look up" fills in the
 * coordinates and, for a PIN code, the state; Google Maps never states the
 * district, so that one is always typed.
 */

interface Props {
  onCreated: (location: LocationItem) => void;
  /** Held by the parent so the trigger can sit in the panel header while the
   *  form itself opens as a full-width row beneath it. */
  open: boolean;
  onClose: () => void;
}

const EMPTY = {
  pincode: '',
  anchor_name: '',
  state: '',
  district: '',
  tehsil: '',
  latitude: '',
  longitude: '',
  radius_km: '',
};

const inputClass =
  'w-full bg-slate-950 border border-slate-700 rounded px-2 py-1.5 text-xs font-mono-code ' +
  'text-slate-100 placeholder:text-slate-600 focus:border-sky-600 focus:outline-none';

const labelClass = 'block text-[10px] font-mono-code uppercase text-slate-400 font-bold mb-1';

export const AddLocationForm: React.FC<Props> = ({ onCreated, open, onClose }) => {
  const [form, setForm] = useState({ ...EMPTY });
  const [looking, setLooking] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);

  const set = (key: keyof typeof EMPTY, value: string) =>
    setForm(prev => ({ ...prev, [key]: value }));

  const reset = () => {
    setForm({ ...EMPTY });
    setError(null);
    setNote(null);
  };

  const lookupTarget = form.pincode.trim() || form.anchor_name.trim();

  const handleLookup = async () => {
    if (!lookupTarget) {
      setError('Enter a PIN code or a town name to look up.');
      return;
    }
    setLooking(true);
    setError(null);
    setNote(null);
    try {
      const r = await resolveLocation(lookupTarget);
      setForm(prev => ({
        ...prev,
        latitude: String(r.latitude),
        longitude: String(r.longitude),
        // Only fill blanks — anything already typed is the user's decision.
        pincode: prev.pincode.trim() || r.pincode || '',
        state: prev.state.trim() || r.state || '',
        anchor_name: prev.anchor_name.trim() || r.resolved_name || '',
        radius_km: prev.radius_km.trim() || String(r.radius_km),
      }));
      setNote(
        r.state
          ? `Found ${r.resolved_name || lookupTarget} in ${r.state}. District still needs filling in — Maps does not state it.`
          : `Found ${r.resolved_name || lookupTarget}. Maps named no state or district for this one, so both need filling in.`,
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Lookup failed.');
    } finally {
      setLooking(false);
    }
  };

  const handleSave = async () => {
    if (!form.pincode.trim() || !form.state.trim() || !form.district.trim()) {
      setError('PIN code, state and district are all required.');
      return;
    }
    setSaving(true);
    setError(null);
    try {
      const created = await createLocation({
        pincode: form.pincode.trim(),
        state: form.state.trim(),
        district: form.district.trim(),
        tehsil: form.tehsil.trim() || null,
        anchor_name: form.anchor_name.trim() || null,
        latitude: form.latitude.trim() ? Number(form.latitude) : null,
        longitude: form.longitude.trim() ? Number(form.longitude) : null,
        radius_km: form.radius_km.trim() ? Number(form.radius_km) : null,
      });
      onCreated(created);
      reset();
      onClose();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not save this location.');
    } finally {
      setSaving(false);
    }
  };

  if (!open) return null;

  return (
    <div className="p-3 bg-slate-950 border-b border-slate-800 flex flex-col gap-3">
      <div className="flex items-center justify-between">
        <h3 className="text-xs font-mono-code font-bold uppercase text-slate-200">
          Add a target PIN
        </h3>
        <button
          onClick={() => { reset(); onClose(); }}
          className="text-slate-500 hover:text-slate-200 transition-colors cursor-pointer"
          title="Close"
        >
          <span className="material-symbols-outlined text-[18px]">close</span>
        </button>
      </div>

      <div className="flex flex-col sm:flex-row gap-2 sm:items-end">
        <div className="flex-1">
          <label className={labelClass}>PIN code *</label>
          <input
            className={inputClass}
            value={form.pincode}
            onChange={e => set('pincode', e.target.value)}
            placeholder="124001"
          />
        </div>
        <div className="flex-1">
          <label className={labelClass}>Anchor village / town</label>
          <input
            className={inputClass}
            value={form.anchor_name}
            onChange={e => set('anchor_name', e.target.value)}
            placeholder="Rohtak"
          />
        </div>
        <button
          onClick={handleLookup}
          disabled={looking || !lookupTarget}
          className="h-[30px] px-3 rounded text-[10px] font-mono-code font-bold uppercase
                     border border-slate-700 bg-slate-900 text-slate-200
                     hover:border-sky-700 hover:text-sky-300 transition-colors
                     disabled:opacity-40 disabled:cursor-not-allowed cursor-pointer shrink-0"
        >
          {looking ? 'Looking up…' : 'Look up'}
        </button>
      </div>

      <div className="grid grid-cols-2 lg:grid-cols-3 gap-2">
        <div>
          <label className={labelClass}>State *</label>
          <input
            className={inputClass}
            value={form.state}
            onChange={e => set('state', e.target.value)}
            placeholder="Haryana"
          />
        </div>
        <div>
          <label className={labelClass}>District *</label>
          <input
            className={inputClass}
            value={form.district}
            onChange={e => set('district', e.target.value)}
            placeholder="ROHTAK"
          />
        </div>
        <div>
          <label className={labelClass}>Tehsil</label>
          <input
            className={inputClass}
            value={form.tehsil}
            onChange={e => set('tehsil', e.target.value)}
            placeholder="Rohtak"
          />
        </div>
        <div>
          <label className={labelClass}>Latitude</label>
          <input
            className={inputClass}
            value={form.latitude}
            onChange={e => set('latitude', e.target.value)}
            placeholder="Auto"
          />
        </div>
        <div>
          <label className={labelClass}>Longitude</label>
          <input
            className={inputClass}
            value={form.longitude}
            onChange={e => set('longitude', e.target.value)}
            placeholder="Auto"
          />
        </div>
        <div>
          <label className={labelClass}>Radius (km)</label>
          <input
            className={inputClass}
            value={form.radius_km}
            onChange={e => set('radius_km', e.target.value)}
            placeholder="20"
          />
        </div>
      </div>

      {note && (
        <p className="text-[11px] font-mono-code text-sky-300 flex items-start gap-1.5">
          <span className="material-symbols-outlined text-[14px] mt-px">info</span>
          {note}
        </p>
      )}
      {error && (
        <p className="text-[11px] font-mono-code text-rose-400 flex items-start gap-1.5">
          <span className="material-symbols-outlined text-[14px] mt-px">error</span>
          {error}
        </p>
      )}

      <div className="flex items-center gap-2">
        <button
          onClick={handleSave}
          disabled={saving}
          className="px-3 py-1.5 rounded text-[10px] font-mono-code font-bold uppercase
                     border border-emerald-800 bg-emerald-950 text-emerald-300
                     hover:bg-emerald-900 hover:text-slate-100 transition-colors
                     disabled:opacity-40 disabled:cursor-not-allowed cursor-pointer"
        >
          {saving ? 'Saving…' : 'Save PIN'}
        </button>
        <span className="text-[10px] font-mono-code text-slate-500">
          Leave coordinates blank to resolve them on save.
        </span>
      </div>
    </div>
  );
};
