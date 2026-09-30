import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  exploreInsights, fetchCampaignInsights, fetchCampaignReport, fetchDimensions,
  fetchInsightHistory, fetchPlaybook, takeSnapshot,
} from '../api/insights';
import type {
  CampaignReport, CampaignRow, Confidence, DimensionInfo, Playbook, SegmentStats, Snapshot, Suggestion,
} from '../api/insights';
import { getApiBaseUrl } from '../api';

// What worked, per campaign and across all of them. Every rate carries a
// confidence label, because most segments are small and a small sample can
// look like a finding when it is not one.

// "Time of day (IST)" -> "time of day (IST)": lower-casing the whole label broke the acronym.
const lowerFirst = (s: string) => s.charAt(0).toLowerCase() + s.slice(1);
const pct = (v: number | null | undefined, digits = 1) =>
  v == null ? '—' : `${(v * 100).toFixed(digits)}%`;
const num = (v: number | null | undefined) => (v == null ? '—' : v.toLocaleString('en-IN'));
const lift = (v: number | null | undefined) =>
  v == null ? '—' : `${v >= 0 ? '+' : ''}${(v * 100).toFixed(0)}%`;

const CONFIDENCE: Record<Confidence, { label: string; icon: string; cls: string; title: string }> = {
  strong: { label: 'Confirmed', icon: 'verified', cls: 'text-emerald-300 bg-emerald-900/30 border-emerald-700/50',
    title: 'The 95% ranges do not overlap: this difference is real.' },
  likely: { label: 'Likely', icon: 'trending_up', cls: 'text-sky-300 bg-sky-900/30 border-sky-700/50',
    title: 'A large difference on enough sends, but not yet certain.' },
  no_difference: { label: 'No difference', icon: 'drag_handle', cls: 'text-slate-300 bg-slate-800 border-slate-700',
    title: 'Enough data, and it performs like everything else.' },
  too_early: { label: 'Too early', icon: 'hourglass_top', cls: 'text-amber-300 bg-amber-900/20 border-amber-700/40',
    title: 'Not enough sends or responses yet to say anything.' },
};

const Badge: React.FC<{ c: Confidence }> = ({ c }) => {
  const s = CONFIDENCE[c] || CONFIDENCE.too_early;
  return (
    <span title={s.title} className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded border text-[10px] font-semibold whitespace-nowrap ${s.cls}`}>
      <span className="material-symbols-outlined text-[12px]">{s.icon}</span>{s.label}
    </span>
  );
};

/** Response rate as a bar with its 95% range, scaled to the table's largest range. */
const RateBar: React.FC<{ row: SegmentStats; max: number }> = ({ row, max }) => {
  const scale = (v: number) => `${Math.min(100, (v / (max || 1)) * 100)}%`;
  return (
    <div className="flex items-center gap-2 min-w-[160px]"
      title={`${pct(row.response_rate, 2)} — 95% range ${pct(row.ci_low, 2)} to ${pct(row.ci_high, 2)}`}>
      <div className="relative h-3 flex-1 rounded-sm bg-slate-800">
        <div className="absolute inset-y-0 left-0 rounded-sm bg-sky-500" style={{ width: scale(row.response_rate) }} />
        <div className="absolute top-1/2 h-px bg-slate-300" style={{ left: scale(row.ci_low), width: `calc(${scale(row.ci_high)} - ${scale(row.ci_low)})` }} />
      </div>
      <span className="text-slate-200 tabular-nums w-14 text-right">{pct(row.response_rate, 2)}</span>
    </div>
  );
};

const Card: React.FC<{ title: string; subtitle?: React.ReactNode; children: React.ReactNode; right?: React.ReactNode }> = ({ title, subtitle, children, right }) => (
  <section className="rounded-lg border border-slate-800 bg-slate-900 mb-6">
    <div className="p-4 border-b border-slate-800 flex items-start justify-between gap-4">
      <div>
        <h2 className="text-sm font-semibold text-slate-100">{title}</h2>
        {subtitle && <div className="text-xs text-slate-500 mt-0.5">{subtitle}</div>}
      </div>
      {right}
    </div>
    <div className="p-4">{children}</div>
  </section>
);

const Tile: React.FC<{ label: string; value: string; note?: string }> = ({ label, value, note }) => (
  <div className="rounded-lg border border-slate-800 bg-slate-900 p-4">
    <div className="text-xs text-slate-400">{label}</div>
    <div className="text-2xl font-semibold text-slate-100 mt-1 tabular-nums">{value}</div>
    {note && <div className="text-[11px] text-slate-500 mt-1">{note}</div>}
  </div>
);

const SegmentTable: React.FC<{ rows: SegmentStats[]; dims: string[]; labels: Record<string, string>; limit?: number }> = ({ rows, dims, labels, limit }) => {
  const shown = limit ? rows.slice(0, limit) : rows;
  const max = Math.max(0.0001, ...shown.map(r => r.ci_high));
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-xs">
        <thead className="text-slate-500 text-left">
          <tr>
            {dims.map(d => <th key={d} className="px-2 py-1.5 font-semibold">{labels[d] || d}</th>)}
            {['Sent', 'Delivered', 'Read', 'Responded', 'Response rate (95% range)', 'vs rest', 'Verdict'].map(h =>
              <th key={h} className="px-2 py-1.5 font-semibold whitespace-nowrap">{h}</th>)}
          </tr>
        </thead>
        <tbody>
          {shown.length === 0 && <tr><td colSpan={dims.length + 7} className="px-2 py-6 text-center text-slate-500">No data yet.</td></tr>}
          {shown.map((r, i) => (
            <tr key={i} className="border-t border-slate-800 text-slate-300">
              {dims.map(d => <td key={d} className="px-2 py-1.5 text-slate-200">{r.values[d]}</td>)}
              <td className="px-2 py-1.5 tabular-nums">{num(r.sent)}</td>
              <td className="px-2 py-1.5 tabular-nums">{r.tracked ? num(r.delivered) : <span className="text-slate-600">not tracked</span>}</td>
              <td className="px-2 py-1.5 tabular-nums">{r.tracked ? num(r.read) : '—'}</td>
              <td className="px-2 py-1.5 tabular-nums">{num(r.responded)}</td>
              <td className="px-2 py-1.5"><RateBar row={r} max={max} /></td>
              <td className="px-2 py-1.5 tabular-nums">{r.confidence === 'too_early' ? '—' : lift(r.lift)}</td>
              <td className="px-2 py-1.5"><Badge c={r.confidence} /></td>
            </tr>
          ))}
        </tbody>
      </table>
      {limit && rows.length > limit && <div className="text-[11px] text-slate-500 mt-2">Showing {limit} of {rows.length}.</div>}
    </div>
  );
};

const mediaUrl = (headerContent: string | null) => {
  try {
    const d = JSON.parse(headerContent || '');
    return d.media_id ? `${getApiBaseUrl()}/api/v1/whatsapp/media/${d.media_id}` : null;
  } catch { return null; }
};

// ---------------------------------------------------------------------------

export const CampaignInsightsView: React.FC = () => {
  const [book, setBook] = useState<Playbook | null>(null);
  const [dims, setDims] = useState<DimensionInfo[]>([]);
  const [campaigns, setCampaigns] = useState<CampaignRow[]>([]);
  const [history, setHistory] = useState<Snapshot[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [openCampaign, setOpenCampaign] = useState<string | null>(null);

  const labels = useMemo(() => Object.fromEntries(dims.map(d => [d.key, d.label])), [dims]);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [b, d, c, h] = await Promise.all([fetchPlaybook(), fetchDimensions(), fetchCampaignInsights(), fetchInsightHistory()]);
      setBook(b); setDims(d.dimensions); setCampaigns(c); setHistory(h);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const snapshot = async () => {
    try { await takeSnapshot(); setHistory(await fetchInsightHistory()); } catch (e: any) { setError(e.message); }
  };

  return (
    <div className="flex-1 flex flex-col min-w-0 h-full bg-slate-950 text-slate-100 p-6 overflow-y-auto">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-semibold text-slate-100 tracking-tight">Campaign Insights</h1>
          <p className="text-xs text-slate-400 mt-0.5">
            How each campaign did, what made the difference, and what has worked across all of them.
          </p>
        </div>
        <button onClick={load} disabled={loading}
          className="h-8 px-3 bg-slate-800 hover:bg-slate-700 border border-slate-700 text-slate-200 text-xs font-mono-code font-semibold rounded flex items-center gap-1.5 disabled:opacity-50">
          <span className={`material-symbols-outlined text-[16px] ${loading ? 'animate-spin' : ''}`}>sync</span>
          {loading ? 'Analysing...' : 'Refresh'}
        </button>
      </div>

      {error && <div className="mb-4 p-3 rounded border border-rose-600/50 bg-rose-900/20 text-rose-200 text-sm">{error}</div>}
      {book && <Readiness book={book} />}
      {book && <Kpis book={book} />}
      {book && <WhatWorks book={book} />}
      {book && <WinningTemplates book={book} />}
      {book && (
        <Card title="Best combinations"
          subtitle={`Pairs of factors — template × state, category × time of day, and every other pair — that responded better than the rest, on at least ${book.thresholds.min_sent} sends each.`}>
          {book.combinations.length === 0 ? (
            <div className="text-sm text-slate-500">
              No combination stands out yet. They appear here once a pair of factors beats the rest on enough responses.
            </div>
          ) : (
            <SegmentTable rows={book.combinations} dims={Object.keys(book.combinations[0].values)}
              labels={labels} />
          )}
        </Card>
      )}
      {dims.length > 0 && <Explore dims={dims} labels={labels} />}
      <CampaignList rows={campaigns} open={openCampaign} onOpen={setOpenCampaign} labels={labels} />
      <History rows={history} labels={labels} onSnapshot={snapshot} />
    </div>
  );
};

// ---------------------------------------------------------------------------

const Readiness: React.FC<{ book: Playbook }> = ({ book }) => {
  const c = book.coverage;
  const lowResponses = c.responses < book.thresholds.min_responses;
  const lowTracking = c.with_delivery_report < 0.5;
  if (!lowResponses && !lowTracking) return null;
  return (
    <div className="mb-6 p-4 rounded-lg border border-amber-700/40 bg-amber-900/15 text-sm text-amber-100">
      <div className="font-semibold mb-1 flex items-center gap-1.5">
        <span className="material-symbols-outlined text-[18px]">hourglass_top</span>
        Still learning — most conclusions below are marked “Too early”
      </div>
      <ul className="list-disc pl-5 space-y-0.5 text-amber-200/90 text-xs">
        {lowResponses && <li>{c.responses} customer response(s) so far. A factor needs about {book.thresholds.min_responses} responses in its comparison before anything can be said about it.</li>}
        {lowTracking && <li>Meta reported delivery for {pct(c.with_delivery_report)} of messages — campaigns sent before the webhook went live have none. Delivered and read counts cover only the rest.</li>}
        {book.test_campaigns_excluded > 0 && <li>{book.test_campaigns_excluded} test campaign(s) (under {book.thresholds.test_campaign_max} recipients) are left out, so the team's own taps do not count as customer behaviour.</li>}
        <li>Every campaign from here adds to the record, and the verdicts update automatically.</li>
      </ul>
    </div>
  );
};

const Kpis: React.FC<{ book: Playbook }> = ({ book }) => {
  const o = book.overall;
  return (
    <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-6 gap-3 mb-6">
      <Tile label="Campaigns analysed" value={num(book.campaigns)} note={book.test_campaigns_excluded ? `${book.test_campaigns_excluded} tests excluded` : undefined} />
      <Tile label="Messages sent" value={num(o.sent)} />
      <Tile label="Delivered" value={o.tracked ? num(o.delivered) : '—'} note={`reported for ${pct(book.coverage.with_delivery_report)} of sends`} />
      <Tile label="Read" value={o.tracked ? num(o.read) : '—'} note={o.read_rate != null ? `${pct(o.read_rate)} of delivered` : undefined} />
      <Tile label="Responded" value={num(o.responded)} note={`${num(o.visited)} link visits · ${num(o.tapped)} taps`} />
      <Tile label="Response rate" value={pct(o.response_rate, 2)} note="responses per message sent" />
    </div>
  );
};

const WhatWorks: React.FC<{ book: Playbook }> = ({ book }) => {
  const groups = ['Template', 'Location', 'Category', 'Timing'];
  const recipe = book.recipe;
  return (
    <Card title="What works best"
      subtitle="The top value of each factor, across every campaign. “Leads so far” means it is ahead but the data cannot confirm it yet.">
      {Object.keys(recipe).length > 0 && (
        <div className="mb-4 p-3 rounded border border-slate-700 bg-slate-950 text-xs text-slate-300">
          <span className="font-semibold text-slate-100">Recommended recipe: </span>
          {Object.entries(recipe).map(([k, v], i) => (
            <span key={k}>{i > 0 && ' · '}<span className="text-slate-500">{book.by_dimension[k]?.label}:</span> {v.value}{v.confidence !== 'strong' && <span className="text-amber-300/80"> (so far)</span>}</span>
          ))}
        </div>
      )}
      <div className="grid md:grid-cols-2 xl:grid-cols-4 gap-4">
        {groups.map(g => (
          <div key={g} className="rounded border border-slate-800 bg-slate-950 p-3">
            <div className="text-xs font-semibold text-slate-200 mb-2">{g}</div>
            <div className="space-y-3">
              {Object.entries(book.by_dimension).filter(([, d]) => d.group === g).map(([key, d]) => {
                const pick = d.best || d.leader;
                return (
                  <div key={key} className="text-xs">
                    <div className="text-slate-500">{d.label}</div>
                    {pick ? (
                      <>
                        <div className="text-slate-100 mt-0.5 break-words">{pick.values[key]}</div>
                        <div className="flex items-center gap-1.5 mt-1">
                          <span className="tabular-nums text-slate-300">{pct(pick.response_rate, 2)}</span>
                          <span className="text-slate-600">of {num(pick.sent)}</span>
                          <Badge c={d.best ? d.best.confidence : 'too_early'} />
                        </div>
                      </>
                    ) : <div className="text-slate-600 mt-0.5">No data</div>}
                    {d.worst && (
                      <div className="text-[11px] text-rose-300/80 mt-0.5">Weakest: {d.worst.values[key]} ({pct(d.worst.response_rate, 2)})</div>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        ))}
      </div>
    </Card>
  );
};

const WinningTemplates: React.FC<{ book: Playbook }> = ({ book }) => (
  <Card title="Templates people responded to most"
    subtitle="Ranked by the low end of their response range, so a lucky small send does not outrank a steady large one. Use these as the reference for new templates and images.">
    {book.winning_templates.length === 0 ? <div className="text-sm text-slate-500">No campaigns yet.</div> : (
      <div className="grid sm:grid-cols-2 xl:grid-cols-3 gap-4">
        {book.winning_templates.map((t, i) => {
          const img = mediaUrl(t.header_content);
          return (
            <div key={t.template_id || i} className="rounded border border-slate-800 bg-slate-950 overflow-hidden">
              {img ? <img src={img} alt="" className="w-full aspect-[3/2] object-cover" /> :
                <div className="aspect-[3/2] flex items-center justify-center text-xs text-slate-600">No image</div>}
              <div className="p-3 text-xs space-y-1.5">
                <div className="flex items-center justify-between gap-2">
                  <span className="text-slate-100 font-semibold truncate">{i + 1}. {t.values.template}</span>
                  <Badge c={t.confidence} />
                </div>
                <div className="text-slate-400">{pct(t.response_rate, 2)} response · {num(t.responded)} of {num(t.sent)} sent</div>
                {t.body && <details><summary className="cursor-pointer text-slate-500 hover:text-slate-300">Message</summary>
                  <div className="mt-1 whitespace-pre-wrap text-slate-400 max-h-48 overflow-y-auto">{t.body}</div></details>}
              </div>
            </div>
          );
        })}
      </div>
    )}
  </Card>
);

const Explore: React.FC<{ dims: DimensionInfo[]; labels: Record<string, string> }> = ({ dims, labels }) => {
  const [picked, setPicked] = useState<string[]>(['template', 'state']);
  const [minSent, setMinSent] = useState(1);
  const [rows, setRows] = useState<SegmentStats[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!picked.length) { setRows([]); return; }
    exploreInsights(picked, minSent).then(r => { setRows(r.rows); setError(null); }).catch(e => setError(e.message));
  }, [picked, minSent]);

  const toggle = (k: string) => setPicked(p => p.includes(k) ? p.filter(x => x !== k) : p.length >= 3 ? p : [...p, k]);
  const groups = Array.from(new Set(dims.map(d => d.group)));

  return (
    <Card title="Explore any combination"
      subtitle="Pick up to three factors to see every combination of them, ranked by response."
      right={
        <label className="text-xs text-slate-400 flex items-center gap-2 whitespace-nowrap">
          Min. sent
          <input type="number" min={1} value={minSent} onChange={e => setMinSent(Math.max(1, Number(e.target.value) || 1))}
            className="w-16 h-7 px-2 bg-slate-950 border border-slate-700 rounded text-slate-100" />
        </label>
      }>
      <div className="flex flex-wrap gap-4 mb-4">
        {groups.map(g => (
          <div key={g}>
            <div className="text-[10px] uppercase tracking-wide text-slate-500 mb-1">{g}</div>
            <div className="flex flex-wrap gap-1.5">
              {dims.filter(d => d.group === g).map(d => {
                const on = picked.includes(d.key);
                return (
                  <button key={d.key} onClick={() => toggle(d.key)} aria-pressed={on}
                    className={`h-7 px-2.5 rounded border text-xs ${on ? 'bg-sky-900/40 border-sky-600 text-sky-200'
                      : 'bg-slate-950 border-slate-700 text-slate-400 hover:text-slate-200'} ${!on && picked.length >= 3 ? 'opacity-40' : ''}`}>
                    {on && <span className="mr-1">{picked.indexOf(d.key) + 1}.</span>}{d.label}
                  </button>
                );
              })}
            </div>
          </div>
        ))}
      </div>
      {error ? <div className="text-sm text-rose-300">{error}</div> :
        picked.length === 0 ? <div className="text-sm text-slate-500">Pick at least one factor.</div> :
          <SegmentTable rows={rows} dims={picked} labels={labels} limit={100} />}
    </Card>
  );
};

// ---------------------------------------------------------------------------

const KIND: Record<Suggestion['kind'], { icon: string; label: string; cls: string }> = {
  strength: { icon: 'thumb_up', label: 'Worked', cls: 'text-emerald-300' },
  opportunity: { icon: 'lightbulb', label: 'Try', cls: 'text-sky-300' },
  weakness: { icon: 'thumb_down', label: 'Held it back', cls: 'text-rose-300' },
  warning: { icon: 'warning', label: 'Check', cls: 'text-amber-300' },
  info: { icon: 'info', label: 'Note', cls: 'text-slate-400' },
};

const CampaignList: React.FC<{ rows: CampaignRow[]; open: string | null; onOpen: (id: string | null) => void; labels: Record<string, string> }> = ({ rows: all, open, onOpen, labels }) => {
  const [showTests, setShowTests] = useState(false);
  const tests = all.filter(r => r.is_test).length;
  const rows = showTests ? all : all.filter(r => !r.is_test);
  return (
  <Card title="Every campaign" subtitle="Click a campaign for its full report: how it did, and what might have made the difference."
    right={tests > 0 ? (
      <label className="text-xs text-slate-400 flex items-center gap-1.5 whitespace-nowrap cursor-pointer">
        <input type="checkbox" checked={showTests} onChange={e => setShowTests(e.target.checked)} />
        Show {tests} test campaign(s)
      </label>
    ) : undefined}>
    <div className="overflow-x-auto">
      <table className="w-full text-xs">
        <thead className="text-slate-500 text-left">
          <tr>{['Campaign', 'Date', 'Sent', 'Delivered', 'Responded', 'Response rate', 'vs all campaigns', 'Main finding'].map(h =>
            <th key={h} className="px-2 py-1.5 font-semibold whitespace-nowrap">{h}</th>)}</tr>
        </thead>
        <tbody>
          {rows.length === 0 && <tr><td colSpan={8} className="px-2 py-6 text-center text-slate-500">No finished campaigns yet.</td></tr>}
          {rows.map(r => (
            <React.Fragment key={r.campaign_id}>
              <tr onClick={() => onOpen(open === r.campaign_id ? null : r.campaign_id)}
                className={`border-t border-slate-800 text-slate-300 cursor-pointer hover:bg-slate-800/40 ${open === r.campaign_id ? 'bg-slate-800/40' : ''}`}>
                <td className="px-2 py-2 text-slate-100 whitespace-nowrap">
                  <span className="material-symbols-outlined text-[14px] align-middle mr-1 text-slate-500">{open === r.campaign_id ? 'expand_more' : 'chevron_right'}</span>
                  {r.name}
                  {r.is_test && <span className="ml-1.5 px-1 py-px rounded bg-slate-800 text-slate-400 text-[10px]">test</span>}
                </td>
                <td className="px-2 py-2 whitespace-nowrap">{new Date(r.created_at).toLocaleDateString('en-IN', { day: '2-digit', month: 'short' })}</td>
                <td className="px-2 py-2 tabular-nums">{num(r.sent)}</td>
                <td className="px-2 py-2 tabular-nums">{r.tracked ? num(r.delivered) : <span className="text-slate-600">not tracked</span>}</td>
                <td className="px-2 py-2 tabular-nums">{num(r.responded)}</td>
                <td className="px-2 py-2 tabular-nums">{pct(r.response_rate, 2)}</td>
                <td className="px-2 py-2 tabular-nums">{lift(r.vs_all_campaigns)}</td>
                <td className="px-2 py-2 text-slate-400 max-w-[420px] truncate" title={r.headline || ''}>{r.headline || '—'}</td>
              </tr>
              {open === r.campaign_id && (
                <tr><td colSpan={8} className="bg-slate-950 border-t border-slate-800"><CampaignDetail id={r.campaign_id} labels={labels} /></td></tr>
              )}
            </React.Fragment>
          ))}
        </tbody>
      </table>
    </div>
  </Card>
  );
};

const CampaignDetail: React.FC<{ id: string; labels: Record<string, string> }> = ({ id, labels }) => {
  const [report, setReport] = useState<CampaignReport | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => { fetchCampaignReport(id).then(setReport).catch(e => setError(e.message)); }, [id]);

  if (error) return <div className="p-4 text-sm text-rose-300">{error}</div>;
  if (!report) return <div className="p-4 text-sm text-slate-500">Analysing…</div>;
  const m = report.metrics;
  const factors = ['Data', 'Delivery', 'Template', 'Location', 'Category', 'Timing'];

  return (
    <div className="p-4 space-y-5">
      <div className="grid grid-cols-2 md:grid-cols-3 2xl:grid-cols-6 gap-3">
        <Tile label="Contacts" value={num(m.total_contacts)} note={`${num(m.skipped)} skipped · ${num(m.failed_to_send)} failed`} />
        <Tile label="Sent" value={num(m.sent)} />
        <Tile label="Delivered" value={m.tracked ? num(m.delivered) : '—'} note={m.tracked ? undefined : 'not tracked'} />
        <Tile label="Read" value={m.tracked ? num(m.read) : '—'} />
        <Tile label="Responded" value={num(m.responded)} note={`${num(m.visited)} visits · ${num(m.tapped)} taps`} />
        <Tile label="Response rate" value={pct(m.response_rate, 2)} note={report.vs_all_campaigns != null ? `${lift(report.vs_all_campaigns)} vs all campaigns` : undefined} />
      </div>

      <div>
        <div className="text-xs font-semibold text-slate-200 mb-2">What might have made the difference{report.template && <span className="text-slate-500 font-normal"> · template “{report.template}”</span>}</div>
        <div className="space-y-1.5">
          {factors.flatMap(f => report.suggestions.filter(s => s.factor === f)).map((s, i) => {
            const k = KIND[s.kind] || KIND.info;
            // Unconfirmed, a "worked" or "held it back" is only a lead.
            const label = s.confidence === 'too_early' && s.kind === 'strength' ? 'Leading so far'
              : s.confidence === 'too_early' && s.kind === 'weakness' ? 'Trailing so far' : k.label;
            return (
              <div key={i} className="flex items-start gap-2 text-xs rounded border border-slate-800 bg-slate-900 p-2.5">
                <span className={`material-symbols-outlined text-[16px] ${k.cls}`}>{k.icon}</span>
                <div className="flex-1">
                  <span className={`font-semibold ${k.cls}`}>{s.factor} · {label}: </span>
                  <span className="text-slate-300">{s.message}</span>
                </div>
                <Badge c={s.confidence} />
              </div>
            );
          })}
        </div>
      </div>

      {!report.is_test && (
        <div className="grid xl:grid-cols-2 gap-5">
          {Object.entries(report.breakdowns).map(([dim, rows]) => (
            <div key={dim}>
              <div className="text-xs font-semibold text-slate-200 mb-1">By {lowerFirst(labels[dim] || dim)}</div>
              <SegmentTable rows={rows} dims={[dim]} labels={labels} limit={8} />
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

const History: React.FC<{ rows: Snapshot[]; labels: Record<string, string>; onSnapshot: () => void }> = ({ rows, labels, onSnapshot }) => {
  const cols = ['template', 'state', 'category', 'time_of_day', 'weekday'];
  return (
    <Card title="What has been learned, over time"
      subtitle="A snapshot is saved after every campaign, so you can see which conclusions held as data grew. A tick means confirmed at that point."
      right={
        <button onClick={onSnapshot} className="h-7 px-2.5 bg-slate-800 hover:bg-slate-700 border border-slate-700 text-slate-200 text-xs rounded whitespace-nowrap">
          Save snapshot now
        </button>
      }>
      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead className="text-slate-500 text-left">
            <tr>
              {['When', 'After', 'Campaigns', 'Sent', 'Responses'].map(h => <th key={h} className="px-2 py-1.5 font-semibold whitespace-nowrap">{h}</th>)}
              {cols.map(c => <th key={c} className="px-2 py-1.5 font-semibold whitespace-nowrap">Best {lowerFirst(labels[c] || c)}</th>)}
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 && <tr><td colSpan={5 + cols.length} className="px-2 py-6 text-center text-slate-500">
              No snapshots yet. One is saved after each campaign; “Save snapshot now” records today's view of past campaigns.</td></tr>}
            {rows.map(s => (
              <tr key={s.snapshot_id} className="border-t border-slate-800 text-slate-300">
                <td className="px-2 py-1.5 whitespace-nowrap">{new Date(s.created_at).toLocaleString('en-IN', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' })}</td>
                <td className="px-2 py-1.5 whitespace-nowrap">{s.campaign || (s.trigger === 'manual' ? 'Manual' : '—')}</td>
                <td className="px-2 py-1.5 tabular-nums">{num(s.campaigns)}</td>
                <td className="px-2 py-1.5 tabular-nums">{num(s.recipients)}</td>
                <td className="px-2 py-1.5 tabular-nums">{num(s.responses)}</td>
                {cols.map(c => (
                  <td key={c} className="px-2 py-1.5 whitespace-nowrap">
                    {s.playbook?.best?.[c] || '—'}
                    {s.playbook?.confident?.[c] && <span className="material-symbols-outlined text-[13px] text-emerald-300 align-middle ml-1" title="Confirmed">verified</span>}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  );
};
