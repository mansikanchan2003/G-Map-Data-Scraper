import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { BackToParent } from '../components/SubPage';
import type { NavTab } from '../components/Header';
import {
  acceptPatch, dismissPatch, fetchAgentQuality, fetchAgentRun, fetchAgentRuns, fetchControls, fetchCopyTrial, fetchGolden,
  fetchLearning, fetchSources, setSwitch, startCopyTrial, tryReply, undoPatch,
  type AgentQuality, type AgentRun, type ContextChunk, type Controls, type CopyTrial, type Draft, type GateReport,
  type BotAction, type GoldenHistory, type Learning, type Patch, type Reading, type SourceRow,
} from '../api/agents';
import { formatDateTime } from '../utils/datetime';

/**
 * The agents' control cockpit (the team's blueprint and its "Context & Harness
 * Engineering" UI spec, 2026-10-26). Leads with the one number that matters,
 * implicit acceptance against its target; then how it moves week by week, each
 * agent's outcomes, where people corrected the most (drift & repair), and a run
 * inspector: its execution trace, the worker's output beside the evaluator's
 * checks, the context it used in three tiers (global, project, session), and
 * the token health of its window.
 *
 * Agent colours follow the reference palette's fixed order (validated for both
 * themes) and always sit beside the agent's name; outcomes use status colours
 * with an icon and a label, never colour alone.
 */

const Icon: React.FC<{ name: string; className?: string; style?: React.CSSProperties }> = ({ name, className = '', style }) =>
  <span className={`material-symbols-outlined ${className}`} style={style}>{name}</span>;
const pct = (v: number | null | undefined) => (v == null ? '—' : `${Math.round(v * 100)}%`);
const num = (v: number | null | undefined) => (v == null ? '—' : v.toLocaleString('en-IN'));
const compact = (v: number) => (v >= 1000 ? `${(v / 1000).toFixed(v >= 10000 ? 0 : 1)}K` : String(Math.round(v)));

// Agent identity: the categorical palette's slots in their fixed order.
const AGENT: Record<string, { icon: string; color: string; short: string }> = {
  template_writer: { icon: 'edit_note', color: 'var(--ag-1)', short: 'Copywriter' },
  business_agent: { icon: 'storefront', color: 'var(--ag-2)', short: 'Business agent' },
  bot_faq: { icon: 'quiz', color: 'var(--ag-3)', short: 'Bot FAQ' },
  bot_reply_disposition: { icon: 'rule', color: 'var(--ag-4)', short: 'Bot dispositions' },
  inbox_ready_reply: { icon: 'quickreply', color: 'var(--ag-5)', short: 'Ready replies' },
};
const agentOf = (k: string) => AGENT[k] || { icon: 'smart_toy', color: 'var(--ag-1)', short: k };

// Outcomes: status colours, always with an icon and a label.
const OUTCOME: Record<AgentRun['outcome'], { label: string; icon: string; color: string; pill: string }> = {
  accepted: { label: 'Kept as it was', icon: 'task_alt', color: 'var(--st-good)', pill: 'bg-emerald-950 text-emerald-300' },
  edited: { label: 'Corrected', icon: 'edit', color: 'var(--st-warn)', pill: 'bg-amber-950 text-amber-300' },
  rejected: { label: 'Rejected', icon: 'block', color: 'var(--st-bad)', pill: 'bg-rose-950 text-rose-300' },
  failed: { label: 'Failed', icon: 'error', color: 'var(--st-crit)', pill: 'bg-rose-950 text-rose-300' },
  pending: { label: 'Waiting for a person', icon: 'hourglass_top', color: 'var(--st-wait)', pill: 'bg-slate-800 text-slate-300' },
};
const OUTCOME_ORDER: AgentRun['outcome'][] = ['accepted', 'edited', 'rejected', 'failed', 'pending'];

const LAYER: Record<ContextChunk['layer'], { label: string; icon: string; note: string; tint: string }> = {
  global: { label: 'Global', icon: 'public', note: "Eko's facts, rules and guardrails", tint: 'bg-sky-950 text-sky-300' },
  project: { label: 'Project memory', icon: 'neurology', note: 'Approved examples, lessons, FAQ, past results', tint: 'bg-violet-950 text-violet-300' },
  session: { label: 'Session', icon: 'chat', note: "This run's own input: the brief, the audience, their words", tint: 'bg-amber-950 text-amber-300' },
};

const STYLE = `
.aq { --ag-1:#3987e5; --ag-2:#d95926; --ag-3:#199e70; --ag-4:#c98500; --ag-5:#d55181;
      --st-good:#34d399; --st-warn:#f9ab10; --st-bad:#fb7185; --st-crit:#f43f5e; --st-wait:#64748b;
      --grid:#1e293b; --ink-2:#94a3b8; --surf:#0f172a; }
:root[data-theme="light"] .aq { --ag-1:#2a78d6; --ag-2:#eb6834; --ag-3:#1baf7a; --ag-4:#eda100; --ag-5:#e87ba4;
      --st-good:#16a34a; --st-warn:#d97706; --st-bad:#e11d48; --st-crit:#be123c; --st-wait:#94a3b8;
      --grid:#e2e8f0; --ink-2:#64748b; --surf:#ffffff; }
`;

const Card: React.FC<{ title: string; icon: string; sub?: React.ReactNode; right?: React.ReactNode; children: React.ReactNode; className?: string }> =
  ({ title, icon, sub, right, children, className = '' }) => (
  <section className={`rounded-2xl border border-slate-800 bg-slate-900 p-5 shadow-sm ${className}`}>
    <div className="flex flex-wrap items-start justify-between gap-3 mb-4">
      <div>
        <h3 className="text-[15px] font-semibold text-slate-100 flex items-center gap-2">
          <span className="h-8 w-8 rounded-lg bg-sky-950 text-sky-300 flex items-center justify-center"><Icon name={icon} className="text-[18px]" /></span>
          {title}
        </h3>
        {sub && <p className="text-[12px] text-slate-500 mt-1 ml-10">{sub}</p>}
      </div>
      {right}
    </div>
    {children}
  </section>
);

/** A ring that fills to the value, with a tick at the target. */
const Ring: React.FC<{ value: number | null; target?: number; size?: number; stroke?: number; color: string; children?: React.ReactNode }> =
  ({ value, target, size = 150, stroke = 12, color, children }) => {
  const r = (size - stroke) / 2, c = 2 * Math.PI * r, v = Math.max(0, Math.min(1, value ?? 0));
  const tickAngle = target != null ? target * 2 * Math.PI - Math.PI / 2 : 0;
  const tx = size / 2 + Math.cos(tickAngle) * r, ty = size / 2 + Math.sin(tickAngle) * r;
  return (
    <div className="relative shrink-0" style={{ width: size, height: size }}>
      <svg width={size} height={size} className="-rotate-90" role="img" aria-label={`${Math.round(v * 100)}%`}>
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="rgba(255,255,255,0.14)" strokeWidth={stroke} />
        {value != null && <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke={color} strokeWidth={stroke}
          strokeLinecap="round" strokeDasharray={`${c * v} ${c}`} style={{ transition: 'stroke-dasharray .6s ease' }} />}
      </svg>
      {target != null && (
        <span className="absolute h-3 w-3 rounded-full border-2 border-white bg-[#0a3543]" title={`Target ${Math.round(target * 100)}%`}
          style={{ left: tx - 6, top: ty - 6, transform: 'rotate(0deg)' }} />
      )}
      <div className="absolute inset-0 flex flex-col items-center justify-center text-center">{children}</div>
    </div>
  );
};

/** Two lines on one 0–100% axis, a labelled target line, and a crosshair with a tooltip. */
const TrendChart: React.FC<{ weeks: AgentQuality['weeks']; target: number }> = ({ weeks, target }) => {
  const [hover, setHover] = useState<number | null>(null);
  const W = 640, H = 220, L = 40, R = 86, T = 14, B = 28;
  const pts = weeks.filter(w => w.runs > 0);
  if (pts.length < 2) {
    return (
      <div className="h-52 flex flex-col items-center justify-center gap-2 text-center rounded-xl border border-dashed border-slate-800">
        <Icon name="show_chart" className="text-[28px] text-slate-600" />
        <span className="text-[12.5px] text-slate-500 max-w-xs">The trend draws itself once the agents have worked across two weeks.</span>
      </div>
    );
  }
  const x = (i: number) => L + (i * (W - L - R)) / (pts.length - 1);
  const y = (v: number) => T + (1 - v) * (H - T - B);
  const series = [
    { key: 'acceptance_rate' as const, label: 'Kept as it was', color: 'var(--ag-1)' },
    { key: 'completion_rate' as const, label: 'Completed', color: 'var(--ag-3)' },
  ];
  const path = (k: 'acceptance_rate' | 'completion_rate') =>
    pts.map((p, i) => p[k] == null ? '' : `${i && pts[i - 1][k] != null ? 'L' : 'M'}${x(i)},${y(p[k] as number)}`).join(' ');
  return (
    <div className="relative">
      <div className="flex flex-wrap gap-4 text-[12px] text-slate-400 mb-2">
        {series.map(s => <span key={s.key} className="flex items-center gap-1.5"><span className="w-4 h-[2px] rounded" style={{ background: s.color }} />{s.label}</span>)}
        <span className="flex items-center gap-1.5"><span className="w-4 border-t border-dotted" style={{ borderColor: 'var(--st-warn)' }} />Target {Math.round(target * 100)}%</span>
      </div>
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full h-auto" onMouseLeave={() => setHover(null)}>
        {[0, 0.25, 0.5, 0.75, 1].map(g => (
          <g key={g}>
            <line x1={L} x2={W - R} y1={y(g)} y2={y(g)} stroke="var(--grid)" strokeWidth={1} />
            <text x={L - 8} y={y(g) + 4} textAnchor="end" fontSize={11} fill="var(--ink-2)">{g * 100}%</text>
          </g>
        ))}
        <line x1={L} x2={W - R} y1={y(target)} y2={y(target)} stroke="var(--st-warn)" strokeWidth={1.5} strokeDasharray="2 4" />
        {pts.map((p, i) => (
          <text key={p.week} x={x(i)} y={H - 8} textAnchor="middle" fontSize={11} fill="var(--ink-2)">
            {new Date(p.week).toLocaleDateString('en-IN', { day: 'numeric', month: 'short' })}
          </text>
        ))}
        {series.map(s => <path key={s.key} d={path(s.key)} fill="none" stroke={s.color} strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" />)}
        {series.map(s => {
          const i = pts.length - 1, v = pts[i][s.key];
          return v == null ? null : (
            <g key={s.key}>
              <circle cx={x(i)} cy={y(v)} r={5} fill={s.color} stroke="var(--surf)" strokeWidth={2} />
              <text x={x(i) + 10} y={y(v) + 4} fontSize={12} fill="currentColor" className="text-slate-200">{Math.round(v * 100)}%</text>
            </g>
          );
        })}
        {hover != null && <line x1={x(hover)} x2={x(hover)} y1={T} y2={H - B} stroke="var(--ink-2)" strokeWidth={1} />}
        {hover != null && series.map(s => pts[hover][s.key] == null ? null :
          <circle key={s.key} cx={x(hover)} cy={y(pts[hover][s.key] as number)} r={5} fill={s.color} stroke="var(--surf)" strokeWidth={2} />)}
        {pts.map((_, i) => (
          <rect key={i} x={x(i) - (W - L - R) / (pts.length - 1) / 2} y={T} width={(W - L - R) / (pts.length - 1)} height={H - T - B}
            fill="transparent" onMouseEnter={() => setHover(i)} />
        ))}
      </svg>
      {hover != null && (
        <div className="absolute pointer-events-none rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-[12px] shadow-lg"
          style={{ left: `${(x(hover) / W) * 100}%`, top: 24, transform: `translateX(${hover > pts.length / 2 ? '-105%' : '8%'})` }}>
          <div className="font-semibold text-slate-100">Week of {new Date(pts[hover].week).toLocaleDateString('en-IN', { day: 'numeric', month: 'short' })}</div>
          <div className="text-slate-300">Kept as it was: <b>{pct(pts[hover].acceptance_rate)}</b></div>
          <div className="text-slate-300">Completed: <b>{pct(pts[hover].completion_rate)}</b></div>
          <div className="text-slate-500">{pts[hover].runs} runs · {num(pts[hover].tokens_per_run)} tokens each · {pts[hover].hitl} tickets</div>
        </div>
      )}
    </div>
  );
};

/** One agent's runs by outcome: a stacked bar with 2px gaps; the legend sits once above the cards. */
const OutcomeBar: React.FC<{ a: AgentQuality['agents'][number] }> = ({ a }) => {
  const counts: Record<AgentRun['outcome'], number> = { accepted: a.accepted, edited: a.edited, rejected: a.rejected, failed: a.failed, pending: a.pending };
  const total = OUTCOME_ORDER.reduce((n, k) => n + counts[k], 0);
  if (!total) return <div className="h-2.5 rounded-full bg-slate-800" />;
  return (
    <div className="flex h-2.5 gap-[2px] rounded-full overflow-hidden">
      {OUTCOME_ORDER.filter(k => counts[k]).map(k => (
        <div key={k} title={`${OUTCOME[k].label}: ${counts[k]}`} style={{ width: `${(counts[k] / total) * 100}%`, background: OUTCOME[k].color }} />
      ))}
    </div>
  );
};

/** Word by word: what a person removed (struck through) and added (marked). */
const Diff: React.FC<{ before: string; after: string; clamp?: boolean }> = ({ before, after, clamp }) => {
  // Words, spaces and punctuation apart, so "Namaste," against "Namaste" marks only the comma.
  const split = (t: string) => t.split(/(\s+|[,.!?;:।])/).filter(x => x !== '');
  const a = split(before), b = split(after);
  const n = a.length, m = b.length;
  const dp: number[][] = Array.from({ length: n + 1 }, () => Array(m + 1).fill(0));
  for (let i = n - 1; i >= 0; i--) for (let j = m - 1; j >= 0; j--)
    dp[i][j] = a[i] === b[j] ? dp[i + 1][j + 1] + 1 : Math.max(dp[i + 1][j], dp[i][j + 1]);
  const out: React.ReactNode[] = [];
  let i = 0, j = 0, k = 0;
  const del = (t: string) => <del key={k++} className="rounded px-0.5 bg-rose-950 text-rose-300">{t}</del>;
  const ins = (t: string) => <ins key={k++} className="rounded px-0.5 bg-emerald-950 text-emerald-300 no-underline">{t}</ins>;
  while (i < n && j < m) {
    if (a[i] === b[j]) { out.push(<span key={k++}>{a[i]}</span>); i++; j++; }
    else if (dp[i + 1][j] >= dp[i][j + 1]) out.push(del(a[i++]));
    else out.push(ins(b[j++]));
  }
  while (i < n) out.push(del(a[i++]));
  while (j < m) out.push(ins(b[j++]));
  return <div className={`whitespace-pre-wrap text-[13px] text-slate-200 leading-relaxed ${clamp ? 'line-clamp-3' : ''}`}>{out}</div>;
};

/** The model's window: green to 60%, yellow to 80%, red past it (the UI spec, 2.2). */
const TokenHealth: React.FC<{ r: AgentRun }> = ({ r }) => {
  const used = (r.prompt_tokens || 0) + (r.output_tokens || 0);
  if (!r.context_window) {
    return (
      <div className="flex items-center gap-2 rounded-xl border border-slate-800 bg-slate-950/60 px-3 py-2.5 text-[12.5px] text-slate-400">
        <Icon name="bolt" className="text-[18px] text-emerald-300" />
        No language model: fixed rules and Eko's FAQ, so no token window to fill.
      </div>
    );
  }
  const share = used / r.context_window;
  const zone = share >= 0.8 ? { label: 'Compress the context', color: 'var(--st-bad)', icon: 'warning' }
    : share >= 0.6 ? { label: 'Getting heavy: slower answers', color: 'var(--st-warn)', icon: 'info' }
    : { label: 'Healthy', color: 'var(--st-good)', icon: 'check_circle' };
  const ctx = r.context_tokens || 0, rest = Math.max((r.prompt_tokens || 0) - ctx, 0), out = r.output_tokens || 0;
  const w = (t: number) => `${(t / r.context_window!) * 100}%`;
  return (
    <div className="rounded-xl border border-slate-800 bg-slate-950/60 p-3">
      <div className="flex items-center justify-between text-[12px]">
        <span className="text-slate-400">Token health · {num(used)} of {compact(r.context_window)} window</span>
        <span className="flex items-center gap-1 font-semibold" style={{ color: zone.color }}><Icon name={zone.icon} className="text-[15px]" />{zone.label}</span>
      </div>
      <div className="relative mt-2 h-3 rounded-full bg-slate-800 overflow-hidden flex gap-[2px]">
        <div style={{ width: w(ctx), background: 'var(--ag-1)' }} title={`Context ${num(ctx)}`} />
        <div style={{ width: w(rest), background: 'var(--ag-5)' }} title={`Instructions ${num(rest)}`} />
        <div style={{ width: w(out), background: 'var(--ag-3)' }} title={`Output ${num(out)}`} />
        <span className="absolute top-0 bottom-0 w-px bg-amber-400/70" style={{ left: '60%' }} />
        <span className="absolute top-0 bottom-0 w-px bg-rose-400/70" style={{ left: '80%' }} />
      </div>
      <div className="flex flex-wrap gap-x-4 gap-y-1 text-[11px] text-slate-500 mt-1.5">
        <span><span className="inline-block w-2 h-2 rounded-full mr-1" style={{ background: 'var(--ag-1)' }} />Context {num(ctx)}</span>
        <span><span className="inline-block w-2 h-2 rounded-full mr-1" style={{ background: 'var(--ag-5)' }} />Instructions {num(rest)}</span>
        <span><span className="inline-block w-2 h-2 rounded-full mr-1" style={{ background: 'var(--ag-3)' }} />Output {num(out)}</span>
        <span>≈ characters ÷ 4</span>
      </div>
    </div>
  );
};

/** The run's steps, from its input to a person's decision (the UI spec's thinking trace, 3.3). */
const Trace: React.FC<{ r: AgentRun }> = ({ r }) => {
  const [open, setOpen] = useState(true);
  const checks = r.evaluation?.checks || [];
  const passed = checks.filter(c => c.passed).length;
  const o = OUTCOME[r.outcome];
  const steps: { icon: string; title: string; detail: string; color: string }[] = [
    { icon: 'input', title: 'Input received', detail: r.prompt_tokens ? `≈ ${num(r.prompt_tokens)} tokens` : 'Their message', color: 'var(--ag-1)' },
    { icon: 'layers', title: 'Context assembled', detail: `${r.context.length} pieces · ≈ ${num(r.context_tokens)} tokens`, color: 'var(--ag-2)' },
    { icon: r.error ? 'error' : 'smart_toy', title: r.error ? 'The agent failed' : 'Agent produced its output',
      detail: r.error || `${r.model || 'Fixed rules'}${r.latency_ms ? ` · ${(r.latency_ms / 1000).toFixed(1)} s` : ''}`, color: r.error ? 'var(--st-bad)' : 'var(--ag-3)' },
    ...(checks.length ? [{ icon: 'fact_check', title: 'Evaluator checked it', detail: `${passed} of ${checks.length} checks passed${r.evaluation?.repaired ? ' · repaired itself' : ''}`,
      color: passed === checks.length ? 'var(--st-good)' : 'var(--st-warn)' }] : []),
    { icon: o.icon, title: r.outcome === 'pending' ? 'Waiting for a person' : `Person: ${o.label.toLowerCase()}`,
      detail: r.outcome === 'edited' ? `${r.edit_distance} characters changed by ${r.finalized_by}` : r.finalized_by ? `by ${r.finalized_by === 'implicit' ? 'nobody stepping in' : r.finalized_by}` : '—',
      color: o.color },
  ];
  return (
    <div className="rounded-xl border border-slate-800 bg-slate-950/60">
      <button onClick={() => setOpen(v => !v)} className="w-full flex items-center justify-between px-3 py-2.5 text-[12.5px] font-semibold text-slate-200 cursor-pointer">
        <span className="flex items-center gap-2"><Icon name="timeline" className="text-[17px] text-sky-300" />Execution trace</span>
        <Icon name={open ? 'expand_less' : 'expand_more'} className="text-[18px] text-slate-500" />
      </button>
      {open && (
        <ol className="px-3 pb-3 flex flex-col sm:flex-row gap-2">
          {steps.map((s, i) => (
            <li key={i} className="flex-1 flex sm:flex-col gap-2 sm:gap-1.5 items-start rounded-lg border border-slate-800 bg-slate-900 p-2.5 relative">
              <span className="h-7 w-7 rounded-full flex items-center justify-center shrink-0" style={{ background: `color-mix(in srgb, ${s.color} 18%, transparent)`, color: s.color }}>
                <Icon name={s.icon} className="text-[16px]" />
              </span>
              <div className="min-w-0">
                <div className="text-[12px] font-semibold text-slate-100">{s.title}</div>
                <div className="text-[11px] text-slate-500 break-words">{s.detail}</div>
              </div>
            </li>
          ))}
        </ol>
      )}
    </div>
  );
};

/** The context in the spec's three tiers, each piece a chip that opens to its text. */
const ContextLayers: React.FC<{ chunks: ContextChunk[] }> = ({ chunks }) => {
  const [openChip, setOpenChip] = useState<number | null>(null);
  const total = chunks.reduce((n, c) => n + (c.tokens || 0), 0) || 1;
  return (
    <div className="space-y-3">
      {(['global', 'project', 'session'] as const).map(layer => {
        const here = chunks.map((c, i) => ({ c, i })).filter(({ c }) => c.layer === layer);
        const tokens = here.reduce((n, { c }) => n + (c.tokens || 0), 0);
        const L = LAYER[layer];
        return (
          <div key={layer} className="rounded-xl border border-slate-800 bg-slate-950/60 p-3">
            <div className="flex items-center gap-2">
              <span className={`h-7 w-7 rounded-lg flex items-center justify-center ${L.tint}`}><Icon name={L.icon} className="text-[16px]" /></span>
              <div className="flex-1 min-w-0">
                <div className="text-[12.5px] font-semibold text-slate-100">{L.label} <span className="font-normal text-slate-500">· {here.length} pieces</span></div>
                <div className="text-[11px] text-slate-500">{L.note}</div>
              </div>
              <span className="text-[11.5px] tabular-nums text-slate-400">{num(tokens)} tok · {Math.round((tokens / total) * 100)}%</span>
            </div>
            {here.length > 0 ? (
              <div className="flex flex-wrap gap-1.5 mt-2.5">
                {here.map(({ c, i }) => (
                  <button key={i} onClick={() => setOpenChip(openChip === i ? null : i)}
                    className={`inline-flex items-center gap-1.5 px-2 py-1 rounded-full border text-[11.5px] cursor-pointer transition-colors ${openChip === i
                      ? 'border-sky-500 bg-sky-950 text-sky-200' : 'border-slate-700 bg-slate-900 text-slate-300 hover:border-slate-600'}`}>
                    <Icon name="sell" className="text-[13px]" />{c.source.replace(/_/g, ' ').replace('learned:', '')}
                    {c.ref && <span className="text-slate-500 max-w-[120px] truncate">{c.ref}</span>}
                    <span className="text-slate-500 tabular-nums">{c.tokens}</span>
                  </button>
                ))}
              </div>
            ) : <div className="text-[11.5px] text-slate-600 mt-2">Nothing from this tier.</div>}
            {here.some(({ i }) => i === openChip) && openChip != null && (
              <div className="mt-2 rounded-lg bg-slate-900 border border-slate-800 p-2.5 text-[12px] text-slate-300 whitespace-pre-wrap max-h-48 overflow-y-auto">
                <span className="text-slate-500 font-mono-code text-[10.5px]">&lt;{chunks[openChip].source}{chunks[openChip].ref ? ` ref="${chunks[openChip].ref}"` : ''}&gt;</span>
                {'\n'}{chunks[openChip].text || '(empty)'}
                {'\n'}<span className="text-slate-500 font-mono-code text-[10.5px]">&lt;/{chunks[openChip].source}&gt;</span>
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
};

/** One run in full: trace, worker beside evaluator, context tiers, token health, the compressed input. */
const Inspector: React.FC<{ r: AgentRun }> = ({ r }) => {
  const [prompt, setPrompt] = useState<string | null>(null);
  const [showPrompt, setShowPrompt] = useState(false);
  useEffect(() => { setPrompt(null); setShowPrompt(false); }, [r.id]);
  const a = agentOf(r.agent), o = OUTCOME[r.outcome];
  const checks = r.evaluation?.checks || [];
  const lines = (prompt || '').split('\n').length;
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <span className="h-10 w-10 rounded-xl flex items-center justify-center" style={{ background: `color-mix(in srgb, ${a.color} 18%, transparent)`, color: a.color }}>
          <Icon name={a.icon} className="text-[22px]" />
        </span>
        <div className="flex-1 min-w-0">
          <div className="text-[15px] font-semibold text-slate-100">{r.agent_label}</div>
          <div className="text-[12px] text-slate-500 flex flex-wrap gap-x-2">
            {r.subject_type === 'chat'
              ? <a href={`#inbox/${r.subject_id.replace(/\D/g, '')}`} className="text-sky-300 hover:underline">Chat {r.subject_id}</a>
              : <span>Draft {r.subject_id.slice(0, 10)}</span>}
            <span>{r.created_at ? formatDateTime(r.created_at) : ''}</span>
          </div>
        </div>
        <span className={`inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-[11.5px] font-semibold ${o.pill}`}><Icon name={o.icon} className="text-[14px]" />{o.label}</span>
      </div>

      <Trace r={r} />

      <div className="grid gap-3 lg:grid-cols-2">
        <div className="rounded-xl border border-slate-800 bg-slate-950/60 p-3">
          <div className="flex items-center justify-between mb-2">
            <span className="flex items-center gap-1.5 text-[11px] uppercase tracking-wider font-semibold text-slate-400"><Icon name="engineering" className="text-[15px]" style={{ color: a.color }} />Worker · what the agent produced</span>
          </div>
          {r.error ? <div className="text-[13px] text-rose-300">{r.error}</div>
            : r.outcome === 'edited' && r.final_output != null ? <Diff before={r.output || ''} after={r.final_output} />
            : <div className="whitespace-pre-wrap text-[13px] text-slate-200 leading-relaxed">{r.output}</div>}
          {r.outcome === 'edited' && (
            <div className="mt-2 flex items-center gap-3 text-[11px] text-slate-500">
              <span><del className="bg-rose-950 text-rose-300 rounded px-1">removed</del> <ins className="bg-emerald-950 text-emerald-300 no-underline rounded px-1">added</ins> by {r.finalized_by}</span>
            </div>
          )}
        </div>
        <div className="rounded-xl border border-slate-800 bg-slate-950/60 p-3">
          <div className="flex items-center gap-1.5 text-[11px] uppercase tracking-wider font-semibold text-slate-400 mb-2"><Icon name="verified" className="text-[15px] text-emerald-300" />Evaluator · checks apart from the agent</div>
          {checks.length ? (
            <ul className="space-y-1.5">
              {checks.map((c, i) => (
                <li key={i} className="flex items-start gap-2 text-[12.5px]">
                  <Icon name={c.passed ? 'check_circle' : 'cancel'} className="text-[17px] mt-[1px]" style={{ color: c.passed ? 'var(--st-good)' : 'var(--st-bad)' }} />
                  <div><div className="text-slate-200">{c.name}</div><div className="text-[11.5px] text-slate-500">{c.detail}</div></div>
                </li>
              ))}
            </ul>
          ) : <div className="text-[12.5px] text-slate-500">No automatic checks for this agent: a person's decision is the evaluation.</div>}
          <div className="mt-3 pt-2.5 border-t border-slate-800 flex items-center gap-2 text-[12.5px]">
            <Icon name={o.icon} className="text-[17px]" style={{ color: o.color }} />
            <span className="text-slate-300">Human verdict: <b className="text-slate-100">{o.label}</b>
              {r.outcome === 'edited' && r.edit_ratio != null && <span className="text-slate-500"> · {Math.round(r.edit_ratio * 100)}% of the text changed</span>}</span>
          </div>
        </div>
      </div>

      <ContextLayers chunks={r.context} />
      <TokenHealth r={r} />

      <div>
        <button onClick={async () => { if (prompt == null) setPrompt((await fetchAgentRun(r.id)).prompt || ''); setShowPrompt(v => !v); }}
          className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full border border-slate-700 bg-slate-950 text-[12px] text-slate-300 hover:border-slate-600 cursor-pointer font-mono-code">
          <Icon name="unfold_more" className="text-[15px]" />
          [Full input{prompt != null ? `: ${lines} lines` : ''} · ≈ {num(r.prompt_tokens)} tokens {showPrompt ? 'shown' : 'compressed'}]
        </button>
        {showPrompt && prompt != null && (
          <pre className="mt-2 max-h-80 overflow-auto rounded-xl bg-slate-950 border border-slate-800 p-3 text-[11.5px] text-slate-300 whitespace-pre-wrap">{prompt || '(no input recorded)'}</pre>
        )}
      </div>
    </div>
  );
};

const SUITE: Record<string, { label: string; icon: string; note: string }> = {
  bot_flow: { label: 'Bot flow', icon: 'route', note: 'Language, PIN, education, investment, documents' },
  faq: { label: 'FAQ answers', icon: 'quiz', note: "Questions in the lead's own words" },
  reply_disposition: { label: 'Dispositions from replies', icon: 'rule', note: 'And replies that must not be read as one' },
  trust: { label: 'Trust concerns', icon: 'verified_user', note: 'Answered, recorded, sent to the team on time' },
  copy_check: { label: 'Copy checker', icon: 'spellcheck', note: 'Drafts it must pass or stop' },
  disposition_sheet: { label: 'Dispositions vs the sheet', icon: 'fact_check', note: 'Each disposition does what the approved sheet says, and Lead Journey shows it' },
};

/** The golden set: real cases with the right answer, run before every deploy (blueprint phase 2). */
const GoldenCard: React.FC<{ g: GoldenHistory }> = ({ g }) => {
  const r = g.last;
  if (!r) {
    return (
      <Card title="Golden test set" icon="workspace_premium" sub="Real cases with the answer AutoGMap must give, run before every deploy">
        <div className="rounded-xl border border-dashed border-slate-800 p-6 text-center text-[13px] text-slate-500">
          Not run on this server yet. The deploy runs it: <code className="font-mono-code text-slate-300">python -m src.evals.golden --save</code>
        </div>
      </Card>
    );
  }
  const share = r.total ? r.passed / r.total : 0;
  const all = r.passed === r.total;
  const runs = [...g.history].reverse().concat([{ ran_at: r.ran_at, total: r.total, passed: r.passed }]).slice(-12);
  return (
    <Card title="Golden test set" icon="workspace_premium"
      sub={<>Real cases with the answer AutoGMap must give · last run {formatDateTime(r.ran_at)} · {r.seconds} s</>}
      right={(
        <span className={`inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-[11.5px] font-semibold ${all ? 'bg-emerald-950 text-emerald-300' : 'bg-rose-950 text-rose-300'}`}>
          <Icon name={all ? 'verified' : 'gpp_bad'} className="text-[15px]" />{all ? 'Safe to deploy' : `${r.total - r.passed} failing: fix before deploying`}
        </span>
      )}>
      <div className="grid gap-5 lg:grid-cols-[200px_1fr_1fr] items-start">
        <div className="flex flex-col items-center gap-3">
          <div className="rounded-full p-1" style={{ background: 'linear-gradient(135deg, #0a3543, #1d5a6e)' }}>
            <Ring value={share} size={150} stroke={12} color={all ? '#34d399' : '#fb7185'}>
              <span className="text-3xl font-semibold tabular-nums text-white">{r.passed}<span className="text-white/60 text-lg">/{r.total}</span></span>
              <span className="text-[11px] text-white/70">cases pass</span>
            </Ring>
          </div>
          {runs.length > 1 && (
            <div className="w-full">
              <div className="flex items-end gap-[3px] h-8">
                {runs.map((h, i) => (
                  <span key={i} className="flex-1 rounded-t-sm" title={`${h.passed}/${h.total} · ${formatDateTime(h.ran_at)}`}
                    style={{ height: `${Math.max(10, (h.passed / Math.max(h.total, 1)) * 100)}%`,
                             background: h.passed === h.total ? 'var(--st-good)' : 'var(--st-bad)', opacity: i === runs.length - 1 ? 1 : 0.55 }} />
                ))}
              </div>
              <div className="text-[10.5px] text-slate-500 text-center mt-1">Last {runs.length} runs</div>
            </div>
          )}
        </div>
        <ul className="space-y-3">
          {Object.entries(r.suites).map(([k, s]) => {
            const meta = SUITE[k] || { label: k, icon: 'checklist', note: '' };
            const ok = s.passed === s.total;
            return (
              <li key={k}>
                <div className="flex items-center gap-2 text-[12.5px]">
                  <Icon name={meta.icon} className="text-[17px] text-sky-300" />
                  <span className="text-slate-100 font-semibold">{meta.label}</span>
                  <span className="flex-1" />
                  <span className="tabular-nums text-slate-300">{s.passed}/{s.total}</span>
                  <Icon name={ok ? 'check_circle' : 'cancel'} className="text-[16px]" style={{ color: ok ? 'var(--st-good)' : 'var(--st-bad)' }} />
                </div>
                <div className="h-1.5 rounded-full bg-slate-800 mt-1.5 overflow-hidden">
                  <div className="h-full rounded-full" style={{ width: `${(s.passed / Math.max(s.total, 1)) * 100}%`, background: ok ? 'var(--st-good)' : 'var(--st-bad)' }} />
                </div>
                <div className="text-[11px] text-slate-500 mt-1">{meta.note}</div>
              </li>
            );
          })}
        </ul>
        <div>
          <div className="text-[11px] uppercase tracking-wider font-semibold text-slate-500 mb-2">{r.failures.length ? 'What failed' : 'Nothing failed'}</div>
          {r.failures.length ? (
            <ul className="space-y-2 max-h-64 overflow-y-auto">
              {r.failures.map(f => (
                <li key={f.id} className="rounded-xl border border-rose-900/60 bg-rose-950/40 p-2.5">
                  <div className="text-[12.5px] text-slate-100"><span className="font-mono-code text-rose-300 text-[11px] mr-1.5">{f.id}</span>{f.title}</div>
                  {f.problems.map((p, i) => <div key={i} className="text-[11.5px] text-rose-200/80 mt-0.5">· {p}</div>)}
                </li>
              ))}
            </ul>
          ) : (
            <div className="rounded-xl border border-emerald-900/50 bg-emerald-950/30 p-4 flex items-center gap-3">
              <Icon name="celebration" className="text-[26px] text-emerald-300" />
              <span className="text-[12.5px] text-slate-300">Every case gives the answer it should. A change that breaks one stops the deploy.</span>
            </div>
          )}
        </div>
      </div>
    </Card>
  );
};


const ago = (iso: string | null) => {
  if (!iso) return '';
  const m = Math.max(0, Math.round((Date.now() - new Date(iso).getTime()) / 60000));
  return m < 60 ? `${m} min ago` : m < 1440 ? `${Math.round(m / 60)} h ago` : `${Math.round(m / 1440)} d ago`;
};

/** Where the agents' knowledge comes from, and how fresh each source is (the blueprint's freshness badges). */
const Freshness: React.FC<{ rows: SourceRow[] }> = ({ rows }) => (
  <div className="flex flex-wrap gap-2">
    {rows.map(r => {
      const tone = r.status === 'fresh' ? { dot: 'var(--st-good)', text: r.synced_at ? `Synced ${ago(r.synced_at)}` : 'Built in' }
        : r.status === 'stale' ? { dot: 'var(--st-warn)', text: `Stale · ${ago(r.synced_at)}` }
        : { dot: 'var(--st-wait)', text: 'Not refreshed yet' };
      return (
        <span key={r.key} title={r.note}
          className="inline-flex items-center gap-2 pl-2 pr-3 py-1.5 rounded-full border border-slate-800 bg-slate-900 text-[12px] shadow-sm">
          <Icon name={r.icon} className="text-[16px] text-sky-300" />
          <span className="text-slate-200 font-medium">{r.label}</span>
          <span className="flex items-center gap-1 text-slate-400">
            <span className={`h-2 w-2 rounded-full ${r.status === 'fresh' ? 'animate-pulse' : ''}`} style={{ background: tone.dot }} />{tone.text}
          </span>
        </span>
      );
    })}
  </div>
);

/** A switch: the admin's one click; others see where it stands. */
const Toggle: React.FC<{ on: boolean; disabled?: boolean; busy?: boolean; onChange: (v: boolean) => void; label: string }> =
  ({ on, disabled, busy, onChange, label }) => (
  <button role="switch" aria-checked={on} aria-label={label} disabled={disabled || busy} onClick={() => onChange(!on)}
    className={`relative inline-flex h-6 w-11 shrink-0 items-center rounded-full transition-colors ${disabled ? 'opacity-50 cursor-not-allowed' : 'cursor-pointer'}`}
    style={{ background: on ? 'var(--st-good)' : 'var(--st-wait)' }}>
    <span className={`inline-block h-5 w-5 rounded-full bg-white shadow transition-transform ${on ? 'translate-x-[22px]' : 'translate-x-[2px]'}`} />
  </button>
);

/** The guardrails: one switch per agent, and each piece of context the template agents get (admin only). */
const ControlsCard: React.FC<{ isAdmin: boolean; tokens: Record<string, number> }> = ({ isAdmin, tokens }) => {
  const [c, setC] = useState<Controls | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => { fetchControls().then(setC).catch(e => setErr(e.message)); }, []);
  const flip = async (group: 'agents' | 'context', key: string, v: boolean) => {
    setBusy(key); setErr(null);
    try { setC(await setSwitch(group, key, v)); } catch (e: any) { setErr(e.message); } finally { setBusy(null); }
  };
  if (!c) return null;
  const offCount = c.agents.filter(a => !a.enabled).length;
  return (
    <Card title="Controls" icon="admin_panel_settings"
      sub={isAdmin ? 'One click takes an agent’s automatic action away; it is back with another' : 'Only the admin can change these'}
      right={(
        <span className={`inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-[11.5px] font-semibold ${offCount ? 'bg-amber-950 text-amber-300' : 'bg-emerald-950 text-emerald-300'}`}>
          <Icon name={offCount ? 'pause_circle' : 'play_circle'} className="text-[15px]" />{offCount ? `${offCount} agent${offCount > 1 ? 's' : ''} turned off` : 'Every agent on'}
        </span>
      )}>
      {err && <div className="mb-3 p-2.5 rounded-lg border border-rose-800/60 bg-rose-950 text-rose-300 text-[12.5px]">{err}</div>}
      <div className="grid gap-5 xl:grid-cols-[1.4fr_1fr]">
        <ul className="space-y-2">
          {c.agents.map(a => {
            const ag = agentOf(a.key);
            return (
              <li key={a.key} className={`rounded-xl border p-3 flex items-start gap-3 transition-colors ${a.enabled ? 'border-slate-800 bg-slate-950/60' : 'border-amber-800/60 bg-amber-950/20'}`}>
                <span className="h-9 w-9 rounded-lg flex items-center justify-center shrink-0" style={{ background: `color-mix(in srgb, ${ag.color} 18%, transparent)`, color: ag.color }}>
                  <Icon name={ag.icon} className="text-[20px]" />
                </span>
                <div className="flex-1 min-w-0">
                  <div className="text-[13px] font-semibold text-slate-100">{a.label}</div>
                  <div className="text-[12px] text-slate-400 mt-0.5">{a.enabled ? a.on : a.off}</div>
                  {a.changed_by && <div className="text-[11px] text-slate-500 mt-1">{a.enabled ? 'Turned on' : 'Turned off'} by {a.changed_by} · {ago(a.changed_at)}</div>}
                </div>
                <Toggle on={a.enabled} disabled={!isAdmin} busy={busy === a.key} label={a.label} onChange={v => flip('agents', a.key, v)} />
              </li>
            );
          })}
        </ul>
        <div>
          <div className="text-[11px] uppercase tracking-wider font-semibold text-slate-500 mb-2 flex items-center gap-1.5">
            <Icon name="tune" className="text-[15px]" />What the template agents are given
          </div>
          <ul className="space-y-2">
            {c.context.map(x => (
              <li key={x.key} className={`rounded-xl border p-3 flex items-center gap-3 ${x.enabled ? 'border-slate-800 bg-slate-950/60' : 'border-slate-800 bg-slate-950/30 opacity-70'}`}>
                <span className="h-8 w-8 rounded-lg bg-violet-950 text-violet-300 flex items-center justify-center shrink-0"><Icon name="neurology" className="text-[17px]" /></span>
                <div className="flex-1 min-w-0">
                  <div className="text-[12.5px] font-semibold text-slate-100">{x.label}
                    {tokens[x.key] ? <span className="ml-1.5 font-normal text-slate-500">≈ {num(tokens[x.key])} tokens a run</span> : null}</div>
                  <div className="text-[11.5px] text-slate-500">{x.about}</div>
                </div>
                <Toggle on={x.enabled} disabled={!isAdmin} busy={busy === x.key} label={x.label} onChange={v => flip('context', x.key, v)} />
              </li>
            ))}
          </ul>
          {c.history.length > 0 && (
            <div className="mt-4">
              <div className="text-[11px] uppercase tracking-wider font-semibold text-slate-500 mb-1.5">Changes</div>
              <ul className="space-y-1 text-[11.5px] text-slate-400 max-h-32 overflow-y-auto">
                {c.history.slice(0, 8).map((h, i) => (
                  <li key={i} className="flex items-center gap-1.5">
                    <Icon name={h.on ? 'toggle_on' : 'toggle_off'} className="text-[16px]" style={{ color: h.on ? 'var(--st-good)' : 'var(--st-wait)' }} />
                    <span className="text-slate-300">{h.what}</span> {h.on ? 'on' : 'off'} · {h.by} · {ago(h.at)}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      </div>
    </Card>
  );
};


/** Git-style: the line as it is, and the line the patch puts in its place. */
const PatchDiff: React.FC<{ before: string; after: string; file: string }> = ({ before, after, file }) => (
  <div className="rounded-lg border border-slate-800 overflow-hidden font-mono-code text-[12px]">
    <div className="px-3 py-1.5 bg-slate-950 border-b border-slate-800 text-slate-500 flex items-center gap-1.5">
      <Icon name="description" className="text-[14px]" />{file}
    </div>
    <div className="px-3 py-1.5 bg-rose-950/50 text-rose-200 whitespace-pre-wrap"><span className="select-none text-rose-400 mr-2">−</span>{before}</div>
    <div className="px-3 py-1.5 bg-emerald-950/50 text-emerald-200 whitespace-pre-wrap"><span className="select-none text-emerald-400 mr-2">+</span>{after}</div>
  </div>
);

const PATCH_KIND: Record<Patch['kind'], { label: string; icon: string; file: string; tint: string }> = {
  copy_lesson: { label: 'Copywriter lesson', icon: 'edit_note', file: 'template agents · lessons the team accepted', tint: 'bg-sky-950 text-sky-300' },
  rule_phrase: { label: 'Bot rule', icon: 'rule', file: 'bot · dispositions read from replies', tint: 'bg-amber-950 text-amber-300' },
  faq_review: { label: 'FAQ to review', icon: 'quiz', file: "bot · Eko's FAQ (never changed automatically)", tint: 'bg-violet-950 text-violet-300' },
};

/** Drift & repair: corrections become proposed patches; the admin accepts them after the golden gate. */
const LearningCard: React.FC<{ isAdmin: boolean; onChanged: () => void }> = ({ isAdmin, onChanged }) => {
  const [l, setL] = useState<Learning | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [gate, setGate] = useState<{ id: string; message: string; report?: GateReport } | null>(null);
  const load = useCallback(() => { fetchLearning().then(setL).catch(() => setL({ proposals: [], accepted: [], log: [] })); }, []);
  useEffect(() => { load(); }, [load]);
  const accept = async (p: Patch) => {
    setBusy(p.id); setGate(null);
    try {
      const r = await acceptPatch(p.id);
      if (!r.ok) setGate({ id: p.id, message: r.message, report: r.gate });
    } catch (e: any) {
      setGate({ id: p.id, message: `The patch was not accepted: ${e?.message || 'the server did not answer'}.` });
    } finally { setBusy(null); load(); onChanged(); }
  };
  const act = async (fn: () => Promise<Learning>, id: string) => { setBusy(id); try { setL(await fn()); } finally { setBusy(null); } };
  if (!l) return null;
  return (
    <Card title="Learning loop" icon="model_training"
      sub="What people corrected, proposed as patches to the agents. A bot rule is tried against the golden set before it goes in."
      right={(
        <div className="flex gap-2 text-[11.5px]">
          <span className="px-2.5 py-1 rounded-full bg-amber-950 text-amber-300 font-semibold">{l.proposals.length} proposed</span>
          <span className="px-2.5 py-1 rounded-full bg-emerald-950 text-emerald-300 font-semibold">{l.accepted.length} in force</span>
        </div>
      )}>
      <div className="grid gap-5 xl:grid-cols-[1.5fr_1fr]">
        <div className="space-y-3">
          {l.proposals.length === 0 && (
            <div className="rounded-xl border border-dashed border-slate-800 p-8 flex flex-col items-center gap-2 text-center">
              <Icon name="auto_fix_high" className="text-[30px] text-slate-600" />
              <span className="text-[13px] text-slate-500 max-w-sm">Nothing to learn yet. When a reviewer rewrites a draft or the team records a different disposition than the bot, a patch appears here.</span>
            </div>
          )}
          {l.proposals.map(p => {
            const k = PATCH_KIND[p.kind];
            const failed = gate?.id === p.id ? gate : null;
            return (
              <div key={p.id} className="rounded-xl border border-slate-800 bg-slate-950/60 p-3.5">
                <div className="flex flex-wrap items-center gap-2">
                  <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-semibold ${k.tint}`}><Icon name={k.icon} className="text-[14px]" />{k.label}</span>
                  <span className="text-[12.5px] font-semibold text-slate-100">{p.title}</span>
                  <span className="flex-1" />
                  <span className="text-[11px] text-slate-500">{p.evidence.by && p.evidence.by !== 'implicit' ? `by ${p.evidence.by}` : ''}{p.evidence.at ? ` · ${ago(p.evidence.at)}` : ''}</span>
                </div>
                <div className="mt-2.5"><PatchDiff before={p.before} after={p.after} file={k.file} /></div>
                <div className="text-[12px] text-slate-400 mt-2 flex items-start gap-1.5"><Icon name="lightbulb" className="text-[15px] text-amber-300 mt-[1px]" />{p.lesson}</div>
                {failed && (
                  <div className="mt-2.5 rounded-lg border border-rose-800/60 bg-rose-950/60 p-2.5 text-[12px]">
                    <div className="text-rose-200 font-semibold flex items-center gap-1.5"><Icon name="gpp_bad" className="text-[16px]" />{failed.message}</div>
                    {failed.report && <div className="text-rose-300/80 mt-1">{failed.report.passed}/{failed.report.total} golden cases pass with it.</div>}
                    {failed.report?.failures.slice(0, 4).map(f => <div key={f.id} className="text-rose-200/80 mt-0.5">· {f.id}: {f.title}</div>)}
                  </div>
                )}
                <div className="flex flex-wrap gap-2 mt-3">
                  {p.kind !== 'faq_review' ? (
                    <button disabled={!isAdmin || busy === p.id} onClick={() => accept(p)}
                      className="inline-flex items-center gap-1.5 h-8 px-3 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white text-[12px] font-semibold disabled:opacity-50 cursor-pointer">
                      <Icon name={busy === p.id ? 'progress_activity' : 'merge'} className={`text-[16px] ${busy === p.id ? 'animate-spin' : ''}`} />
                      {busy === p.id ? (p.kind === 'rule_phrase' ? 'Running the golden set…' : 'Accepting…') : 'Accept prompt patch'}
                    </button>
                  ) : (
                    <button disabled={!isAdmin || busy === p.id} onClick={() => accept(p)}
                      className="inline-flex items-center gap-1.5 h-8 px-3 rounded-lg bg-violet-600 hover:bg-violet-500 text-white text-[12px] font-semibold disabled:opacity-50 cursor-pointer">
                      <Icon name="task_alt" className="text-[16px]" />Mark reviewed
                    </button>
                  )}
                  <button disabled={!isAdmin || busy === p.id} onClick={() => act(() => dismissPatch(p.id), p.id)}
                    className="h-8 px-3 rounded-lg border border-slate-700 text-slate-300 text-[12px] font-semibold hover:bg-slate-800 disabled:opacity-50 cursor-pointer">Dismiss</button>
                  {!isAdmin && <span className="text-[11px] text-slate-500 self-center">Only the admin can accept patches</span>}
                </div>
              </div>
            );
          })}
        </div>
        <div>
          <div className="text-[11px] uppercase tracking-wider font-semibold text-slate-500 mb-2 flex items-center gap-1.5"><Icon name="verified" className="text-[15px] text-emerald-300" />In force</div>
          {l.accepted.length === 0 ? <div className="text-[12.5px] text-slate-500">No patch accepted yet.</div> : (
            <ul className="space-y-2">
              {l.accepted.map(p => (
                <li key={p.id} className="rounded-xl border border-emerald-900/50 bg-emerald-950/20 p-3">
                  <div className="flex items-start gap-2">
                    <Icon name={PATCH_KIND[p.kind].icon} className="text-[17px] text-emerald-300 mt-[1px]" />
                    <div className="flex-1 min-w-0">
                      <div className="text-[12.5px] text-slate-200">{p.lesson}</div>
                      <div className="text-[11px] text-slate-500 mt-0.5">by {p.accepted_by} · {ago(p.accepted_at || null)}
                        {p.gate ? ` · golden ${p.gate.passed}/${p.gate.total}` : ''}</div>
                    </div>
                    {p.kind !== 'faq_review' && (
                      <button disabled={!isAdmin || busy === p.id} onClick={() => act(() => undoPatch(p.id), p.id)}
                        className="text-[11.5px] text-slate-400 hover:text-rose-300 disabled:opacity-50 cursor-pointer flex items-center gap-1">
                        <Icon name="undo" className="text-[15px]" />Undo
                      </button>
                    )}
                  </div>
                </li>
              ))}
            </ul>
          )}
          {l.log.length > 0 && (
            <div className="mt-4">
              <div className="text-[11px] uppercase tracking-wider font-semibold text-slate-500 mb-1.5">What was done</div>
              <ul className="space-y-1 text-[11.5px] text-slate-400 max-h-36 overflow-y-auto">
                {l.log.slice(0, 10).map((x, i) => (
                  <li key={i}>
                    <span className={x.what === 'accepted' ? 'text-emerald-300' : x.what === 'undone' ? 'text-rose-300' : 'text-slate-300'}>{x.what}</span>
                    {x.lesson ? `: ${x.lesson.slice(0, 70)}${x.lesson.length > 70 ? '…' : ''}` : ''} · {x.by} · {ago(x.at)}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      </div>
    </Card>
  );
};

const SOURCES_OFF = [
  { key: 'approved_example', label: 'Approved examples' }, { key: 'performance', label: 'Past performance' },
  { key: 'rejected_draft', label: 'Rejected drafts' }, { key: 'past_mistake', label: 'Past mistakes' },
  { key: 'growth_goal', label: 'Growth goal' },
];

/** Side by side: today's behaviour against a change, before it goes anywhere near a lead. */
const BOT_ACTIONS: Record<BotAction['kind'], { icon: string; color: string }> = {
  faq: { icon: 'quiz', color: 'var(--ag-1)' },
  disposition: { icon: 'label', color: 'var(--ag-3)' },
  auto_reply: { icon: 'smart_toy', color: 'var(--ag-4)' },
  clarify: { icon: 'help', color: 'var(--ag-5)' },
  team: { icon: 'support_agent', color: 'var(--ag-2)' },
  step: { icon: 'replay', color: 'var(--ag-1)' },
};

const PlaygroundCard: React.FC<{ isAdmin: boolean }> = ({ isAdmin }) => {
  const [tab, setTab] = useState<'reply' | 'copy'>('reply');
  const [text, setText] = useState('abhi busy hoon, shaam 5 baje call karna');
  const [reading, setReading] = useState<Awaited<ReturnType<typeof tryReply>> | null>(null);
  const [state, setState] = useState('Gujarat');
  const [instruction, setInstruction] = useState('');
  const [without, setWithout] = useState<string[]>([]);
  const [trial, setTrial] = useState<CopyTrial | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const read = async () => { setErr(null); try { setReading(await tryReply(text)); } catch (e: any) { setErr(e.message); } };
  const write = async () => {
    setErr(null); setTrial({ status: 'running', state, instruction, without });
    try {
      const { id } = await startCopyTrial(state, instruction, without);
      for (let i = 0; i < 90; i++) {
        await new Promise(r => setTimeout(r, 2000));
        const t = await fetchCopyTrial(id);
        setTrial(t);
        if (t.status !== 'running') break;
      }
    } catch (e: any) { setErr(e.message); setTrial(null); }
  };
  const Pane: React.FC<{ title: string; icon: string; accent: string; children: React.ReactNode }> = ({ title, icon, accent, children }) => (
    <div className="rounded-xl border border-slate-800 bg-slate-950/60 p-3.5 min-w-0">
      <div className="flex items-center gap-1.5 text-[11px] uppercase tracking-wider font-semibold mb-2.5" style={{ color: accent }}>
        <Icon name={icon} className="text-[15px]" />{title}
      </div>
      {children}
    </div>
  );
  const ReadingView: React.FC<{ r: Reading }> = ({ r }) => (
    <div>
      <div className="text-[18px] font-semibold text-slate-100">{r.label}</div>
      <div className="text-[12px] text-slate-500 mt-0.5">Read from {r.by}</div>
      {r.confidence != null && (
        <div className="mt-2.5">
          <div className="flex justify-between text-[11px] text-slate-500"><span>Confidence</span><span>{Math.round(r.confidence * 100)}%</span></div>
          <div className="h-1.5 rounded-full bg-slate-800 mt-1 overflow-hidden">
            <div className="h-full rounded-full" style={{ width: `${r.confidence * 100}%`, background: r.confidence >= 0.75 ? 'var(--st-good)' : 'var(--st-warn)' }} />
          </div>
        </div>
      )}
    </div>
  );
  const DraftView: React.FC<{ d?: Draft }> = ({ d }) => !d ? <div className="h-28 rounded-lg bg-slate-900 animate-pulse" /> : (
    <div>
      <div className="whitespace-pre-wrap text-[13px] text-slate-200 leading-relaxed max-h-64 overflow-y-auto">{d.body}</div>
      <div className="mt-2.5 flex flex-wrap gap-2 text-[11px]">
        <span className={`px-2 py-0.5 rounded-full font-semibold ${d.problems.length ? 'bg-rose-950 text-rose-300' : 'bg-emerald-950 text-emerald-300'}`}>
          {d.problems.length ? `${d.problems.length} checker problem${d.problems.length > 1 ? 's' : ''}` : 'Checker: clean'}
        </span>
        <span className="px-2 py-0.5 rounded-full bg-slate-800 text-slate-300">≈ {num(d.prompt_tokens)} prompt tokens</span>
      </div>
      {d.problems.slice(0, 3).map((p, i) => <div key={i} className="text-[11.5px] text-rose-300/80 mt-1">· {p}</div>)}
    </div>
  );
  return (
    <Card title="Playground" icon="science" sub="Try a change side by side with today's behaviour; nothing here reaches a lead or Meta"
      right={(
        <div className="flex items-center gap-1 rounded-lg border border-slate-800 bg-slate-950 p-1">
          {([['reply', 'Bot rules', 'rule'], ['copy', 'Copywriter', 'edit_note']] as const).map(([k, label, icon]) => (
            <button key={k} onClick={() => setTab(k)}
              className={`inline-flex items-center gap-1 px-3 py-1.5 rounded-md text-xs font-semibold cursor-pointer ${tab === k ? 'bg-slate-800 text-slate-100' : 'text-slate-500 hover:text-slate-300'}`}>
              <Icon name={icon} className="text-[15px]" />{label}
            </button>
          ))}
        </div>
      )}>
      {err && <div className="mb-3 p-2.5 rounded-lg border border-rose-800/60 bg-rose-950 text-rose-300 text-[12.5px]">{err}</div>}
      {tab === 'reply' ? (
        <div className="space-y-3">
          <div className="flex gap-2">
            <input value={text} onChange={e => setText(e.target.value)} onKeyDown={e => { if (e.key === 'Enter') read(); }}
              placeholder="Type a reply a lead might send…"
              className="flex-1 bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-[13px] text-slate-100 outline-none focus:border-sky-500" />
            <button onClick={read} className="h-10 px-4 rounded-lg bg-sky-600 hover:bg-sky-500 text-white text-[12.5px] font-semibold cursor-pointer flex items-center gap-1.5">
              <Icon name="play_arrow" className="text-[17px]" />Read it
            </button>
          </div>
          {reading && (() => {
            const act = BOT_ACTIONS[reading.bot.kind];
            return (
              <>
                {/* What the bot actually does: a disposition is only one of the things it tries. */}
                <div className="rounded-xl border p-3.5" style={{ borderColor: `color-mix(in srgb, ${act.color} 45%, transparent)`, background: `color-mix(in srgb, ${act.color} 9%, transparent)` }}>
                  <div className="flex items-start gap-3">
                    <div className="h-9 w-9 shrink-0 rounded-lg grid place-items-center text-white" style={{ background: act.color }}>
                      <Icon name={act.icon} className="text-[19px]" />
                    </div>
                    <div className="min-w-0 flex-1">
                      <div className="text-[11px] uppercase tracking-wider font-semibold text-slate-400">What the bot does</div>
                      <div className="text-[16px] font-semibold text-slate-100 mt-0.5">{reading.bot.title}</div>
                      <div className="text-[12.5px] text-slate-400 mt-0.5">{reading.bot.detail}</div>
                      {reading.bot.answer && (
                        <div className="mt-2.5 rounded-lg bg-slate-950/70 border border-slate-800 p-3 text-[13px] text-slate-200 whitespace-pre-wrap leading-relaxed max-h-56 overflow-y-auto">
                          {reading.bot.answer}
                        </div>
                      )}
                    </div>
                  </div>
                </div>
                <div className="text-[11px] uppercase tracking-wider font-semibold text-slate-500 pt-1">Read as a disposition</div>
                <div className="grid gap-3 md:grid-cols-2">
                  <Pane title="Today, in production" icon="public" accent="var(--ag-1)"><ReadingView r={reading.today} /></Pane>
                  {reading.pending_rules ? (
                    <Pane title={`With the ${reading.pending_rules} pending rule${reading.pending_rules === 1 ? '' : 's'}`} icon="science" accent="var(--ag-4)"><ReadingView r={reading.with_patches} /></Pane>
                  ) : (
                    <Pane title="With pending rules" icon="science" accent="var(--ag-4)">
                      <div className="text-[14px] font-semibold text-slate-300">No rule waiting to be accepted</div>
                      <div className="text-[12px] text-slate-500 mt-0.5">When the team corrects a disposition, the proposed rule is tried here.</div>
                    </Pane>
                  )}
                </div>
              </>
            );
          })()}
        </div>
      ) : (
        <div className="space-y-3">
          <div className="grid gap-2 md:grid-cols-[180px_1fr_auto]">
            <input value={state} onChange={e => setState(e.target.value)} placeholder="State"
              className="bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-[13px] text-slate-100 outline-none focus:border-sky-500" />
            <input value={instruction} onChange={e => setInstruction(e.target.value)} placeholder="The change to try, e.g. Open with the free training"
              className="bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-[13px] text-slate-100 outline-none focus:border-sky-500" />
            <button onClick={write} disabled={!isAdmin || trial?.status === 'running'}
              className="h-10 px-4 rounded-lg bg-sky-600 hover:bg-sky-500 text-white text-[12.5px] font-semibold cursor-pointer flex items-center gap-1.5 disabled:opacity-50">
              <Icon name={trial?.status === 'running' ? 'progress_activity' : 'play_arrow'} className={`text-[17px] ${trial?.status === 'running' ? 'animate-spin' : ''}`} />
              {trial?.status === 'running' ? 'Writing both…' : 'Write both'}
            </button>
          </div>
          <div className="flex flex-wrap gap-1.5 items-center text-[11.5px]">
            <span className="text-slate-500 mr-1">Leave out:</span>
            {SOURCES_OFF.map(s => {
              const on = without.includes(s.key);
              return (
                <button key={s.key} onClick={() => setWithout(on ? without.filter(x => x !== s.key) : [...without, s.key])}
                  className={`px-2.5 py-1 rounded-full border cursor-pointer ${on ? 'border-amber-600 bg-amber-950 text-amber-200 line-through' : 'border-slate-700 text-slate-400 hover:border-slate-600'}`}>
                  {s.label}
                </button>
              );
            })}
            {!isAdmin && <span className="text-slate-500 ml-2">Only the admin can run copy trials (they use the model)</span>}
          </div>
          {trial && (
            trial.status === 'failed' ? <div className="text-[12.5px] text-rose-300">The trial failed: {trial.error}</div> : (
              <div className="grid gap-3 md:grid-cols-2">
                <Pane title="Today's prompt" icon="public" accent="var(--ag-1)"><DraftView d={trial.today} /></Pane>
                <Pane title="With your change" icon="science" accent="var(--ag-4)"><DraftView d={trial.changed} /></Pane>
              </div>
            )
          )}
        </div>
      )}
    </Card>
  );
};

/** Why a template draft reads the way it does: its run, in the inspector (opened from Template Studio). */
export const WhyThisDraft: React.FC<{ templateId: string }> = ({ templateId }) => {
  const [r, setR] = useState<AgentRun | null | undefined>(undefined);
  useEffect(() => { fetchAgentRuns(undefined, undefined, 1, templateId).then(l => setR(l[0] || null)).catch(() => setR(null)); }, [templateId]);
  return (
    <div className="aq">
      <style>{STYLE}</style>
      {r === undefined ? <div className="h-40 rounded-xl bg-slate-900 animate-pulse" />
        : r === null ? <div className="text-[13px] text-slate-500">This draft was written before runs were recorded (26 Oct 2026), so its context is not kept.</div>
        : <Inspector r={r} />}
    </div>
  );
};

export const AgentQualityView: React.FC<{ can?: (t: NavTab) => boolean; isAdmin?: boolean }> = ({ can, isAdmin = false }) => {
  const [days, setDays] = useState(30);
  const [q, setQ] = useState<AgentQuality | null>(null);
  const [runs, setRuns] = useState<AgentRun[]>([]);
  const [agent, setAgent] = useState('');
  const [outcome, setOutcome] = useState('');
  const [picked, setPicked] = useState<AgentRun | null>(null);
  const [golden, setGolden] = useState<GoldenHistory | null>(null);
  const [sources, setSources] = useState<SourceRow[]>([]);
  useEffect(() => { fetchSources().then(setSources).catch(() => setSources([])); }, []);
  useEffect(() => { fetchGolden().then(setGolden).catch(() => setGolden({ last: null, history: [] })); }, []);
  const [error, setError] = useState<string | null>(null);
  const load = useCallback(async () => {
    try {
      setError(null);
      const [quality, list] = await Promise.all([fetchAgentQuality(days), fetchAgentRuns(agent || undefined, outcome || undefined, 60)]);
      setQ(quality); setRuns(list);
      setPicked(p => (p && list.find(x => x.id === p.id)) || list[0] || null);
    } catch (e: any) { setError(e.message); }
  }, [days, agent, outcome]);
  useEffect(() => { load(); }, [load]);

  const o = q?.overall;
  const decided = o ? o.accepted + o.edited + o.rejected : 0;
  const onTarget = o?.acceptance_rate != null && q ? o.acceptance_rate >= q.targets.acceptance_rate : null;
  const hitlSeries = useMemo(() => (q?.weeks || []).map(w => w.hitl), [q]);
  const contextTokens = useMemo(() => {
    const runsWith = runs.filter(r => r.agent === 'template_writer' || r.agent === 'business_agent');
    const sum: Record<string, number> = {};
    runsWith.forEach(r => r.context.forEach(c => { sum[c.source] = (sum[c.source] || 0) + (c.tokens || 0); }));
    return Object.fromEntries(Object.entries(sum).map(([k, v]) => [k, Math.round(v / Math.max(runsWith.length, 1))]));
  }, [runs]);

  return (
    <div className="aq flex-1 overflow-y-auto bg-slate-950 text-slate-100">
      <style>{STYLE}</style>
      <div className="px-4 sm:px-6 pt-6 max-w-[1400px] mx-auto">
        <BackToParent tab="agent-quality" can={can} />
      </div>
      <div className="px-4 sm:px-6 pb-8 max-w-[1400px] mx-auto space-y-5">
        {error && <div className="p-3 rounded-lg border border-rose-800/60 bg-rose-950 text-rose-300 text-sm">{error}</div>}

        {/* The headline: implicit acceptance against its target, in the app's deep-teal banner (dark in both themes). */}
        <section className="rounded-2xl overflow-hidden shadow-md text-white"
          style={{ background: 'linear-gradient(120deg, #0a3543 0%, #16435a 55%, #1d5a6e 100%)' }}>
          <div className="p-6 flex flex-col lg:flex-row gap-6 lg:items-center">
            <div className="flex items-center gap-6 flex-1 min-w-0">
              <Ring value={o?.acceptance_rate ?? null} target={q?.targets.acceptance_rate} color={onTarget ? '#34d399' : '#f9ab10'}>
                <span className="text-4xl font-semibold tabular-nums">{pct(o?.acceptance_rate)}</span>
                <span className="text-[11px] text-white/70">kept as it was</span>
              </Ring>
              <div className="min-w-0">
                <div className="text-[11px] uppercase tracking-[0.14em] font-semibold flex flex-wrap items-center gap-2" style={{ color: '#f9ab10' }}>
                  Agent quality
                  <span className="normal-case tracking-normal font-medium text-[10.5px] px-2 py-0.5 rounded-full bg-white/10 text-white/80">
                    <Icon name="psychology" className="text-[13px] align-[-2px] mr-0.5" />{num(o?.runs)} runs in {days} days
                  </span>
                </div>
                <h1 className="text-2xl sm:text-[28px] font-semibold leading-tight mt-1">
                  {o?.acceptance_rate == null ? 'Waiting for the first decisions'
                    : onTarget ? 'People keep what the agents make' : 'People still correct the agents often'}
                </h1>
                <p className="text-sm text-white/75 mt-1.5 max-w-xl">
                  {decided ? <>Of <b className="text-white">{decided}</b> outputs a person decided on, <b className="text-white">{o?.accepted}</b> were kept untouched,
                    {' '}<b className="text-white">{o?.edited}</b> corrected and <b className="text-white">{o?.rejected}</b> rejected. Target: more than 75% kept.</>
                    : 'Every template draft, FAQ answer, disposition read from a reply and ready reply is recorded here with what a person did with it.'}
                </p>
                <div className="mt-3 flex items-center gap-1 rounded-lg bg-white/10 p-1 w-fit">
                  {[7, 30, 90].map(n => (
                    <button key={n} onClick={() => setDays(n)}
                      className={`px-3 py-1 rounded-md text-xs font-semibold cursor-pointer transition-colors ${days === n ? 'bg-white text-[#0a3543]' : 'text-white/75 hover:text-white'}`}>
                      {n} days
                    </button>
                  ))}
                </div>
              </div>
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-3 lg:grid-cols-1 2xl:grid-cols-3 gap-3 lg:w-[290px] 2xl:w-[620px] shrink-0">
              <div className="rounded-xl bg-white/10 p-3.5 flex items-center gap-3">
                <Ring value={o?.completion_rate ?? null} target={q?.targets.completion_rate} size={58} stroke={7}
                  color={(o?.completion_rate ?? 0) >= (q?.targets.completion_rate ?? 1) ? '#34d399' : '#fb7185'}>
                  <span className="text-[11px] font-semibold tabular-nums">{pct(o?.completion_rate)}</span>
                </Ring>
                <div><div className="text-[11.5px] text-white/70">Task completion</div><div className="text-[11px] text-white/55">target &gt; 95% · {o?.failed ?? 0} failed</div></div>
              </div>
              <div className="rounded-xl bg-white/10 p-3.5">
                <div className="text-[11.5px] text-white/70 flex items-center gap-1"><Icon name="difference" className="text-[15px]" style={{ color: '#f9ab10' }} />Correction delta</div>
                <div className="text-2xl font-semibold tabular-nums mt-0.5">{o?.avg_edit_ratio == null ? '—' : `${Math.round(o.avg_edit_ratio * 100)}%`}</div>
                <div className="h-1.5 rounded-full bg-white/10 mt-1.5 overflow-hidden">
                  <div className="h-full rounded-full bg-[#f9ab10]" style={{ width: `${Math.min(100, (o?.avg_edit_ratio ?? 0) * 100)}%` }} />
                </div>
                <div className="text-[11px] text-white/55 mt-1">of the text changed · target 0</div>
              </div>
              <div className="rounded-xl bg-white/10 p-3.5">
                <div className="text-[11.5px] text-white/70 flex items-center gap-1"><Icon name="support_agent" className="text-[15px]" style={{ color: '#c4b5fd' }} />People stepping in</div>
                <div className="text-2xl font-semibold tabular-nums mt-0.5">{num(q?.hitl_interventions)}</div>
                <div className="flex items-end gap-[2px] h-5 mt-1">
                  {hitlSeries.map((v, i) => (
                    <span key={i} className="flex-1 rounded-t-sm" title={`${v} tickets`}
                      style={{ height: `${Math.max(8, (v / Math.max(...hitlSeries, 1)) * 100)}%`, background: i === hitlSeries.length - 1 ? '#c4b5fd' : 'rgba(255,255,255,0.28)' }} />
                  ))}
                </div>
                <div className="text-[11px] text-white/55 mt-1">tickets · target falling</div>
              </div>
            </div>
          </div>
        </section>

        {sources.length > 0 && <Freshness rows={sources} />}

        {q && (
          <div className="grid gap-5 xl:grid-cols-[1.5fr_1fr]">
            <Card title="Week by week" icon="show_chart" sub="Share kept as it was and share completed · hover a week">
              <TrendChart weeks={q.weeks} target={q.targets.acceptance_rate} />
            </Card>
            <Card title="Tokens per run" icon="data_usage" sub="Context window efficiency · lower is better">
              <div className="flex items-baseline gap-2">
                <span className="text-4xl font-semibold tabular-nums text-slate-100">{num(o?.tokens_per_run)}</span>
                <span className="text-[12.5px] text-slate-500">tokens a run, {num(o?.context_tokens_per_run)} of them context</span>
              </div>
              <div className="flex items-end gap-2 h-32 mt-5">
                {q.weeks.filter(w => w.runs).map((w, i, arr) => {
                  const max = Math.max(...arr.map(x => x.tokens_per_run || 0), 1);
                  return (
                    <div key={w.week} className="flex-1 flex flex-col items-center gap-1 h-full justify-end group">
                      <span className="text-[10.5px] tabular-nums text-slate-500 opacity-0 group-hover:opacity-100">{compact(w.tokens_per_run || 0)}</span>
                      <div className="w-full max-w-[24px] rounded-t" style={{ height: `${((w.tokens_per_run || 0) / max) * 100}%`, minHeight: 4,
                        background: i === arr.length - 1 ? 'var(--ag-1)' : 'color-mix(in srgb, var(--ag-1) 40%, transparent)' }} />
                      <span className="text-[10px] text-slate-500">{new Date(w.week).toLocaleDateString('en-IN', { day: 'numeric', month: 'short' })}</span>
                    </div>
                  );
                })}
                {!q.weeks.some(w => w.runs) && <div className="w-full self-center text-center text-[12.5px] text-slate-500">No runs yet.</div>}
              </div>
            </Card>
          </div>
        )}

        {q && (
          <Card title="Each agent" icon="hub" sub="Its runs by outcome, and the share people kept"
            right={(
              <div className="flex flex-wrap gap-3 text-[11.5px] text-slate-400">
                {OUTCOME_ORDER.map(k => <span key={k} className="flex items-center gap-1.5"><Icon name={OUTCOME[k].icon} className="text-[14px]" style={{ color: OUTCOME[k].color }} />{OUTCOME[k].label}</span>)}
              </div>
            )}>
            <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
              {q.agents.map(a => {
                const ag = agentOf(a.key);
                const on = agent === a.key;
                return (
                  <button key={a.key} onClick={() => setAgent(on ? '' : a.key)}
                    className={`text-left rounded-xl border p-4 transition-all cursor-pointer ${on ? 'border-sky-500 ring-1 ring-sky-500 bg-slate-950' : 'border-slate-800 bg-slate-950/60 hover:border-slate-700'}`}>
                    <div className="flex items-center gap-2.5">
                      <span className="h-9 w-9 rounded-lg flex items-center justify-center" style={{ background: `color-mix(in srgb, ${ag.color} 18%, transparent)`, color: ag.color }}>
                        <Icon name={ag.icon} className="text-[20px]" />
                      </span>
                      <div className="min-w-0"><div className="text-[13px] font-semibold text-slate-100 leading-tight">{a.label}</div>
                        <div className="text-[11px] text-slate-500">{a.runs} runs</div></div>
                    </div>
                    <div className="flex items-baseline justify-between mt-3">
                      <span className="text-2xl font-semibold tabular-nums text-slate-100">{pct(a.acceptance_rate)}</span>
                      <span className="text-[11px] text-slate-500">kept</span>
                    </div>
                    <div className="mt-2"><OutcomeBar a={a} /></div>
                    <div className="grid grid-cols-2 gap-2 mt-3 text-[11px]">
                      <div><div className="text-slate-500">Correction</div><div className="text-slate-200 tabular-nums font-semibold">{a.avg_edit_ratio == null ? '—' : `${Math.round(a.avg_edit_ratio * 100)}%`}</div></div>
                      <div><div className="text-slate-500">Tokens / run</div><div className="text-slate-200 tabular-nums font-semibold">{a.tokens_per_run == null ? '—' : compact(a.tokens_per_run)}</div></div>
                    </div>
                  </button>
                );
              })}
            </div>
          </Card>
        )}

        <ControlsCard isAdmin={isAdmin} tokens={contextTokens} />

        {golden && <GoldenCard g={golden} />}

        <LearningCard isAdmin={isAdmin} onChanged={load} />

        <PlaygroundCard isAdmin={isAdmin} />

        {q && q.biggest_corrections.length > 0 && (
          <Card title="Biggest corrections" icon="build_circle" sub="Where people changed the most; the learning loop below turns them into patches">
            <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
              {q.biggest_corrections.map(r => {
                const ag = agentOf(r.agent);
                return (
                  <button key={r.id} onClick={() => setPicked(r)} className="text-left rounded-xl border border-slate-800 bg-slate-950/60 p-3 hover:border-amber-700/60 cursor-pointer">
                    <div className="flex items-center gap-2 text-[11.5px]">
                      <Icon name={ag.icon} className="text-[16px]" style={{ color: ag.color }} /><span className="text-slate-300 font-semibold">{ag.short}</span>
                      <span className="flex-1" />
                      <span className="px-2 py-0.5 rounded-full bg-amber-950 text-amber-300 font-semibold tabular-nums">{Math.round((r.edit_ratio || 0) * 100)}% changed</span>
                    </div>
                    <div className="mt-2"><Diff before={r.output || ''} after={r.final_output || ''} clamp /></div>
                  </button>
                );
              })}
            </div>
          </Card>
        )}

        <Card title="Run inspector" icon="manage_search" sub="Pick a run: its trace, the worker beside the evaluator, the context it used and its token health"
          right={(
            <div className="flex flex-wrap gap-1.5">
              {(['', ...OUTCOME_ORDER] as const).map(k => (
                <button key={k || 'all'} onClick={() => setOutcome(k)}
                  className={`inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-[11.5px] border cursor-pointer ${outcome === k ? 'border-sky-500 bg-sky-950 text-sky-200' : 'border-slate-700 text-slate-400 hover:border-slate-600'}`}>
                  {k && <Icon name={OUTCOME[k].icon} className="text-[13px]" style={{ color: OUTCOME[k].color }} />}{k ? OUTCOME[k].label : 'Every outcome'}
                </button>
              ))}
            </div>
          )}>
          {runs.length === 0 ? (
            <div className="py-12 flex flex-col items-center gap-2 text-center rounded-xl border border-dashed border-slate-800">
              <Icon name="psychology" className="text-[32px] text-slate-600" />
              <span className="text-[13px] text-slate-500 max-w-sm">No runs yet. They appear as the bot answers, reads replies, and the template agents write drafts.</span>
            </div>
          ) : (
            <div className="grid gap-4 xl:grid-cols-[360px_1fr]">
              <ul className="space-y-2 xl:max-h-[880px] xl:overflow-y-auto xl:pr-1">
                {runs.map(r => {
                  const ag = agentOf(r.agent), oc = OUTCOME[r.outcome], on = picked?.id === r.id;
                  return (
                    <li key={r.id}>
                      <button onClick={() => setPicked(r)}
                        className={`w-full text-left rounded-xl border p-3 flex gap-3 cursor-pointer transition-colors ${on ? 'border-sky-500 bg-slate-950' : 'border-slate-800 bg-slate-950/60 hover:border-slate-700'}`}>
                        <span className="w-1 rounded-full shrink-0" style={{ background: ag.color }} />
                        <div className="min-w-0 flex-1">
                          <div className="flex items-center gap-1.5 text-[11.5px]">
                            <Icon name={ag.icon} className="text-[15px]" style={{ color: ag.color }} />
                            <span className="font-semibold text-slate-200">{ag.short}</span>
                            <span className="flex-1" />
                            <Icon name={oc.icon} className="text-[15px]" style={{ color: oc.color }} />
                            <span className="text-slate-400">{oc.label}</span>
                          </div>
                          <div className="text-[12.5px] text-slate-300 mt-1 line-clamp-2">{r.output === 'clarify'
                            ? <>Could mean {(r.evaluation?.ambiguous || []).join(' or ')}: left for a person</> : (r.error || r.output || '—')}</div>
                          {(r.output === 'clarify' || (r.evaluation?.confidence != null && r.evaluation.confidence < 0.75)) && (
                            <span className="inline-flex items-center gap-1 mt-1.5 px-2 py-0.5 rounded-full text-[10.5px] font-semibold bg-amber-950 text-amber-300">
                              <Icon name={r.output === 'clarify' ? 'help' : 'speed'} className="text-[13px]" />
                              {r.output === 'clarify' ? 'Clarify: read two ways' : `Low confidence · ${Math.round((r.evaluation?.confidence || 0) * 100)}%`}
                            </span>
                          )}
                          <div className="text-[10.5px] text-slate-500 mt-1">{r.created_at ? formatDateTime(r.created_at) : ''}{r.outcome === 'edited' && r.edit_distance != null ? ` · ${r.edit_distance} chars changed` : ''}</div>
                        </div>
                      </button>
                    </li>
                  );
                })}
              </ul>
              <div className="rounded-2xl border border-slate-800 bg-slate-900/40 p-4 min-w-0">
                {picked ? <Inspector r={picked} /> : <div className="text-[13px] text-slate-500">Pick a run on the left.</div>}
              </div>
            </div>
          )}
        </Card>
      </div>
    </div>
  );
};
