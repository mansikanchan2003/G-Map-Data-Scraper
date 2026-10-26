import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { BackToParent } from '../components/SubPage';
import type { NavTab } from '../components/Header';
import {
  fetchAgentQuality, fetchAgentRun, fetchAgentRuns, type AgentQuality, type AgentRun, type ContextChunk,
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

export const AgentQualityView: React.FC<{ can?: (t: NavTab) => boolean }> = ({ can }) => {
  const [days, setDays] = useState(30);
  const [q, setQ] = useState<AgentQuality | null>(null);
  const [runs, setRuns] = useState<AgentRun[]>([]);
  const [agent, setAgent] = useState('');
  const [outcome, setOutcome] = useState('');
  const [picked, setPicked] = useState<AgentRun | null>(null);
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

        {q && q.biggest_corrections.length > 0 && (
          <Card title="Drift & repair" icon="build_circle" sub="Where people changed the most: what the agents should learn first">
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
                          <div className="text-[12.5px] text-slate-300 mt-1 line-clamp-2">{r.error || r.output || '—'}</div>
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
