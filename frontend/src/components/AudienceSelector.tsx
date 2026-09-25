import React, { useState, useEffect, useCallback } from 'react';
import {
  fetchAudienceOptions,
  fetchAudienceSummary,
  fetchAudiencePreview,
  stashAudience,
  type AudienceOptions,
  type AudienceSummary,
} from '../api/whatsapp';

interface Props {
  isOpen: boolean;
  onClose: () => void;
  /** Called once the audience is built and stored, to move to the builder. */
  onReady: () => void;
}

const ALL = 'All';

/**
 * Chooses who a campaign goes to, before the builder opens.
 *
 * Geography narrows the pool, the contacted-history rule decides whether
 * people already reached are eligible, and the limit caps how many are taken.
 * Counts refresh as the selection changes so the decision is made against real
 * numbers rather than after the fact.
 */
export const AudienceSelector: React.FC<Props> = ({ isOpen, onClose, onReady }) => {
  const [options, setOptions] = useState<AudienceOptions | null>(null);
  const [state, setState] = useState(ALL);
  const [district, setDistrict] = useState(ALL);
  const [tehsil, setTehsil] = useState(ALL);
  const [includeContacted, setIncludeContacted] = useState(false);
  const [limitEnabled, setLimitEnabled] = useState(false);
  const [limit, setLimit] = useState<number>(100);

  const [summary, setSummary] = useState<AudienceSummary | null>(null);
  const [loading, setLoading] = useState(false);
  const [building, setBuilding] = useState(false);

  const filters = {
    state,
    district,
    tehsil,
    limit: limitEnabled ? limit : null,
    include_already_contacted: includeContacted,
  };

  // Districts and tehsils depend on the level above, so options reload when
  // the parent selection changes.
  useEffect(() => {
    if (!isOpen) return;
    fetchAudienceOptions(state, district).then(setOptions).catch(() => setOptions(null));
  }, [isOpen, state, district]);

  const refreshSummary = useCallback(async () => {
    setLoading(true);
    try {
      setSummary(await fetchAudienceSummary(filters));
    } catch {
      setSummary(null);
    } finally {
      setLoading(false);
    }
  }, [state, district, tehsil, includeContacted, limitEnabled, limit]);

  useEffect(() => {
    if (!isOpen) return;
    const t = setTimeout(refreshSummary, 250);
    return () => clearTimeout(t);
  }, [isOpen, refreshSummary]);

  if (!isOpen) return null;

  const scopeLabel = [
    tehsil !== ALL ? tehsil : null,
    district !== ALL ? district : null,
    state !== ALL ? state : 'All states',
  ].filter(Boolean).join(' · ');

  const handleContinue = async () => {
    setBuilding(true);
    try {
      const preview = await fetchAudiencePreview(filters);
      if (preview.contacts.length === 0) {
        alert('No sendable contacts match this selection.');
        return;
      }
      stashAudience({ contacts: preview.contacts, label: scopeLabel });
      onReady();
    } catch (err: any) {
      alert(err.message);
    } finally {
      setBuilding(false);
    }
  };

  const Dropdown = ({ label, value, onChange, opts, disabled }: any) => (
    <div className="flex flex-col gap-1">
      <label className="text-[10px] uppercase tracking-wider text-slate-500 font-semibold">{label}</label>
      <select
        value={value}
        onChange={e => onChange(e.target.value)}
        disabled={disabled}
        className="bg-slate-950 border border-slate-700 rounded px-3 py-2 text-sm text-slate-200 outline-none disabled:opacity-50"
      >
        <option value={ALL}>All {label.toLowerCase()}s</option>
        {(opts || []).map((o: any) => (
          <option key={o.value} value={o.value}>
            {o.value} ({o.businesses.toLocaleString()})
          </option>
        ))}
      </select>
    </div>
  );

  return (
    <div className="fixed inset-0 z-50 bg-slate-950/80 flex items-center justify-center p-4">
      <div className="bg-slate-900 border border-slate-800 rounded-xl w-full max-w-2xl max-h-[92vh] overflow-y-auto shadow-2xl">
        <div className="px-6 py-4 border-b border-slate-800 flex items-center justify-between">
          <div>
            <h2 className="text-lg font-semibold text-slate-100">Choose campaign audience</h2>
            <p className="text-xs text-slate-400 mt-0.5">Pick the area, then how many to reach</p>
          </div>
          <button onClick={onClose} className="text-slate-500 hover:text-slate-300">
            <span className="material-symbols-outlined">close</span>
          </button>
        </div>

        <div className="p-6 space-y-5">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            <Dropdown
              label="State" value={state} opts={options?.states}
              onChange={(v: string) => { setState(v); setDistrict(ALL); setTehsil(ALL); }}
            />
            <Dropdown
              label="District" value={district} opts={options?.districts}
              onChange={(v: string) => { setDistrict(v); setTehsil(ALL); }}
            />
            <Dropdown label="Tehsil" value={tehsil} opts={options?.tehsils} onChange={setTehsil} />
          </div>

          {/* What this selection adds up to */}
          <div className="bg-slate-950 border border-slate-800 rounded-lg p-4">
            <div className="flex items-center justify-between mb-3">
              <span className="text-xs font-semibold text-slate-300">{scopeLabel}</span>
              {loading && <span className="text-[10px] text-slate-500">updating…</span>}
            </div>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-center">
              <div>
                <div className="text-xl font-bold text-slate-200">{summary?.total_businesses?.toLocaleString() ?? '—'}</div>
                <div className="text-[10px] uppercase text-slate-500 tracking-wider">Businesses</div>
              </div>
              <div>
                <div className="text-xl font-bold text-sky-400">{summary?.with_phone?.toLocaleString() ?? '—'}</div>
                <div className="text-[10px] uppercase text-slate-500 tracking-wider">Valid phone</div>
              </div>
              <div>
                <div className="text-xl font-bold text-amber-400">{summary?.already_contacted?.toLocaleString() ?? '—'}</div>
                <div className="text-[10px] uppercase text-slate-500 tracking-wider">Already messaged</div>
              </div>
              <div>
                <div className="text-xl font-bold text-emerald-400">{summary?.never_contacted?.toLocaleString() ?? '—'}</div>
                <div className="text-[10px] uppercase text-slate-500 tracking-wider">Never messaged</div>
              </div>
            </div>
          </div>

          {/* Previously contacted */}
          <div className="space-y-2">
            <label className="text-[10px] uppercase tracking-wider text-slate-500 font-semibold">
              People already messaged in this area
            </label>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
              <button
                onClick={() => setIncludeContacted(false)}
                className={`px-3 py-2.5 rounded border text-sm text-left transition-colors ${
                  !includeContacted
                    ? 'bg-emerald-950/40 border-emerald-700 text-emerald-400'
                    : 'bg-slate-950 border-slate-800 text-slate-400 hover:border-slate-600'
                }`}
              >
                <div className="font-semibold">Exclude them</div>
                <div className="text-[11px] opacity-80">Only reach people who have never received a campaign</div>
              </button>
              <button
                onClick={() => setIncludeContacted(true)}
                className={`px-3 py-2.5 rounded border text-sm text-left transition-colors ${
                  includeContacted
                    ? 'bg-amber-950/40 border-amber-700 text-amber-400'
                    : 'bg-slate-950 border-slate-800 text-slate-400 hover:border-slate-600'
                }`}
              >
                <div className="font-semibold">Include them</div>
                <div className="text-[11px] opacity-80">Message everyone, including previous recipients</div>
              </button>
            </div>
          </div>

          {/* How many */}
          <div className="space-y-2">
            <label className="text-[10px] uppercase tracking-wider text-slate-500 font-semibold">How many to send</label>
            <div className="flex items-center gap-3">
              <button
                onClick={() => setLimitEnabled(false)}
                className={`px-3 py-2 rounded border text-sm ${
                  !limitEnabled ? 'bg-sky-950/40 border-sky-700 text-sky-400' : 'bg-slate-950 border-slate-800 text-slate-400'
                }`}
              >
                Everyone
              </button>
              <button
                onClick={() => setLimitEnabled(true)}
                className={`px-3 py-2 rounded border text-sm ${
                  limitEnabled ? 'bg-sky-950/40 border-sky-700 text-sky-400' : 'bg-slate-950 border-slate-800 text-slate-400'
                }`}
              >
                Limit to
              </button>
              <input
                type="number"
                min={1}
                value={limit}
                disabled={!limitEnabled}
                onChange={e => setLimit(Math.max(1, Number(e.target.value) || 1))}
                className="w-28 bg-slate-950 border border-slate-700 rounded px-3 py-2 text-sm text-slate-200 outline-none disabled:opacity-40"
              />
              <span className="text-xs text-slate-500">contacts</span>
            </div>
          </div>

          {/* Outcome */}
          <div className="bg-emerald-950/30 border border-emerald-800 rounded-lg px-4 py-3 flex items-center justify-between">
            <span className="text-sm text-emerald-300">This campaign will message</span>
            <span className="text-2xl font-bold text-emerald-400">
              {summary?.sendable?.toLocaleString() ?? '—'}
            </span>
          </div>
        </div>

        <div className="px-6 py-4 border-t border-slate-800 flex justify-between items-center">
          <button onClick={onClose} className="px-4 py-2 text-sm text-slate-400 hover:text-slate-200 font-semibold">
            Cancel
          </button>
          <button
            onClick={handleContinue}
            disabled={building || !summary || summary.sendable === 0}
            className="px-6 py-2.5 bg-emerald-600 hover:bg-emerald-500 disabled:opacity-40 disabled:cursor-not-allowed text-white text-sm font-semibold rounded shadow transition-colors flex items-center gap-2"
          >
            <span className="material-symbols-outlined text-[18px]">campaign</span>
            {building ? 'Preparing…' : 'Continue to campaign'}
          </button>
        </div>
      </div>
    </div>
  );
};
