import React, { useCallback, useEffect, useState } from 'react';
import { BackToParent } from '../components/SubPage';
import type { NavTab } from '../components/Header';
import { fetchAgentQuality, fetchAgentRun, fetchAgentRuns, type AgentQuality, type AgentRun } from '../api/agents';
import { formatDateTime } from '../utils/datetime';

/**
 * How AutoGMap's agents are doing, by the team's blueprint (2026-10-26):
 * implicit acceptance, correction delta (edit distance), task completion,
 * tokens per run and human interventions, per agent and week by week; then
 * every run with its full chain: the context it used (the "why"), what it
 * produced and what a person finally kept, with the difference marked.
 */

const Icon: React.FC<{ name: string; className?: string }> = ({ name, className = '' }) =>
  <span className={`material-symbols-outlined ${className}`}>{name}</span>;
const pct = (v: number | null | undefined) => (v == null ? '—' : `${Math.round(v * 100)}%`);
const num = (v: number | null | undefined) => (v == null ? '—' : v.toLocaleString('en-IN'));

const OUTCOME: Record<AgentRun['outcome'], { label: string; cls: string }> = {
  accepted: { label: 'Accepted as is', cls: 'bg-emerald-950 text-emerald-300' },
  edited: { label: 'Corrected', cls: 'bg-amber-950 text-amber-300' },
  rejected: { label: 'Rejected', cls: 'bg-rose-950 text-rose-300' },
  failed: { label: 'Failed', cls: 'bg-rose-950 text-rose-300' },
  pending: { label: 'Waiting for a person', cls: 'bg-slate-800 text-slate-300' },
};

const Tile: React.FC<{ icon: string; label: string; value: string; target: string; good: boolean | null; note?: string }> =
  ({ icon, label, value, target, good, note }) => (
  <div className="rounded-xl border border-slate-800 bg-slate-900 p-4 shadow-sm">
    <div className="flex flex-wrap items-center justify-between gap-1">
      <span className="flex items-center gap-1.5 text-[12px] text-slate-400 whitespace-nowrap"><Icon name={icon} className="text-[16px]" />{label}</span>
      {good != null && (
        <span className={`text-[10.5px] font-semibold px-1.5 py-0.5 rounded ${good ? 'bg-emerald-950 text-emerald-300' : 'bg-amber-950 text-amber-300'}`}>
          {good ? 'On target' : 'Below target'}
        </span>
      )}
    </div>
    <div className="text-2xl font-semibold tabular-nums text-slate-100 mt-1">{value}</div>
    <div className="text-[11px] text-slate-500 mt-0.5">Target: {target}{note ? ` · ${note}` : ''}</div>
  </div>
);

/** Word by word: what the person removed (struck through) and added (marked). */
const Diff: React.FC<{ before: string; after: string }> = ({ before, after }) => {
  const a = before.split(/(\s+)/), b = after.split(/(\s+)/);
  const n = a.length, m = b.length;
  const dp: number[][] = Array.from({ length: n + 1 }, () => Array(m + 1).fill(0));
  for (let i = n - 1; i >= 0; i--) for (let j = m - 1; j >= 0; j--)
    dp[i][j] = a[i] === b[j] ? dp[i + 1][j + 1] + 1 : Math.max(dp[i + 1][j], dp[i][j + 1]);
  const out: React.ReactNode[] = [];
  let i = 0, j = 0, k = 0;
  while (i < n && j < m) {
    if (a[i] === b[j]) { out.push(<span key={k++}>{a[i]}</span>); i++; j++; }
    else if (dp[i + 1][j] >= dp[i][j + 1]) { out.push(<del key={k++} className="bg-rose-950 text-rose-300">{a[i]}</del>); i++; }
    else { out.push(<ins key={k++} className="bg-emerald-950 text-emerald-300 no-underline">{b[j]}</ins>); j++; }
  }
  while (i < n) out.push(<del key={k++} className="bg-rose-950 text-rose-300">{a[i++]}</del>);
  while (j < m) out.push(<ins key={k++} className="bg-emerald-950 text-emerald-300 no-underline">{b[j++]}</ins>);
  return <div className="whitespace-pre-wrap text-[12.5px] text-slate-200 leading-relaxed">{out}</div>;
};

/** Where the run's tokens went: injected context, the rest of the prompt, and the output. */
const Budget: React.FC<{ r: AgentRun }> = ({ r }) => {
  const ctx = r.context_tokens || 0, prompt = Math.max((r.prompt_tokens || 0) - ctx, 0), out = r.output_tokens || 0;
  const total = ctx + prompt + out;
  if (!total) return null;
  const w = (x: number) => `${(x / total) * 100}%`;
  return (
    <div>
      <div className="flex h-2 rounded-full overflow-hidden bg-slate-800">
        <div className="bg-sky-500" style={{ width: w(ctx) }} title={`Context ${ctx}`} />
        <div className="bg-violet-500" style={{ width: w(prompt) }} title={`Instructions ${prompt}`} />
        <div className="bg-emerald-500" style={{ width: w(out) }} title={`Output ${out}`} />
      </div>
      <div className="flex flex-wrap gap-x-3 text-[11px] text-slate-500 mt-1">
        <span><span className="inline-block w-2 h-2 rounded-full bg-sky-500 mr-1" />Context {num(ctx)}</span>
        <span><span className="inline-block w-2 h-2 rounded-full bg-violet-500 mr-1" />Instructions {num(prompt)}</span>
        <span><span className="inline-block w-2 h-2 rounded-full bg-emerald-500 mr-1" />Output {num(out)}</span>
        <span>≈ tokens (characters ÷ 4)</span>
      </div>
    </div>
  );
};

const RunRow: React.FC<{ r: AgentRun }> = ({ r }) => {
  const [open, setOpen] = useState(false);
  const [prompt, setPrompt] = useState<string | null>(null);
  const o = OUTCOME[r.outcome] || OUTCOME.pending;
  const subject = r.subject_type === 'chat' ? <a href={`#inbox/${r.subject_id.replace(/\D/g, '')}`} className="text-sky-300 hover:underline">{r.subject_id}</a>
    : <span className="font-mono-code text-slate-400">{r.subject_id.slice(0, 10)}</span>;
  return (
    <li className="rounded-xl border border-slate-800 bg-slate-950/60">
      <button onClick={() => setOpen(v => !v)} className="w-full text-left p-3 flex flex-wrap items-center gap-x-3 gap-y-1 cursor-pointer">
        <span className="text-[12.5px] font-semibold text-slate-100">{r.agent_label}</span>
        <span className={`px-2 py-0.5 rounded-full text-[10.5px] font-semibold ${o.cls}`}>{o.label}</span>
        {r.edit_distance != null && r.outcome === 'edited' && <span className="text-[11px] text-amber-300">{r.edit_distance} characters changed</span>}
        <span className="text-[11.5px] text-slate-500">{subject}</span>
        <span className="flex-1" />
        <span className="text-[11px] text-slate-500">{r.created_at ? formatDateTime(r.created_at) : ''}</span>
        <Icon name={open ? 'expand_less' : 'expand_more'} className="text-[18px] text-slate-500" />
      </button>
      {open && (
        <div className="px-3 pb-3 grid gap-3 lg:grid-cols-2">
          <div className="space-y-2">
            <div className="text-[11px] uppercase tracking-wider text-slate-500">What the agent produced{r.final_output != null && r.outcome === 'edited' ? ', and what a person changed' : ''}</div>
            {r.error ? <div className="text-[12.5px] text-rose-300">{r.error}</div>
              : r.outcome === 'edited' && r.final_output != null ? <Diff before={r.output || ''} after={r.final_output} />
              : <div className="whitespace-pre-wrap text-[12.5px] text-slate-200">{r.output}</div>}
            {r.finalized_by && <div className="text-[11px] text-slate-500">Final version by {r.finalized_by === 'implicit' ? 'nobody (left as it was)' : r.finalized_by}{r.finalized_at ? `, ${formatDateTime(r.finalized_at)}` : ''}</div>}
            <Budget r={r} />
          </div>
          <div className="space-y-2">
            <div className="text-[11px] uppercase tracking-wider text-slate-500">Why: the context it used ({r.context.length})</div>
            <ul className="space-y-1.5 max-h-72 overflow-y-auto">
              {r.context.map((c, i) => (
                <li key={i} className="rounded-lg border border-slate-800 bg-slate-900 p-2">
                  <div className="flex items-center gap-2 text-[11px]">
                    <span className="px-1.5 py-0.5 rounded bg-sky-950 text-sky-300 font-semibold">{c.source.replace(/_/g, ' ')}</span>
                    {c.ref && <span className="text-slate-500 truncate">{c.ref}</span>}
                    <span className="flex-1" /><span className="text-slate-500">{c.tokens} tok</span>
                  </div>
                  {c.text && <div className="text-[12px] text-slate-300 mt-1 whitespace-pre-wrap line-clamp-4">{c.text}</div>}
                </li>
              ))}
              {r.context.length === 0 && <li className="text-[12px] text-slate-500">No context recorded.</li>}
            </ul>
            <button onClick={async () => setPrompt((await fetchAgentRun(r.id)).prompt || '(no prompt)')}
              className="text-[11.5px] text-sky-300 hover:underline cursor-pointer">Show the full input</button>
            {prompt != null && <pre className="max-h-64 overflow-auto rounded-lg bg-slate-900 border border-slate-800 p-2 text-[11px] text-slate-300 whitespace-pre-wrap">{prompt}</pre>}
          </div>
        </div>
      )}
    </li>
  );
};

export const AgentQualityView: React.FC<{ can?: (t: NavTab) => boolean }> = ({ can }) => {
  const [days, setDays] = useState(30);
  const [q, setQ] = useState<AgentQuality | null>(null);
  const [runs, setRuns] = useState<AgentRun[]>([]);
  const [agent, setAgent] = useState('');
  const [outcome, setOutcome] = useState('');
  const [error, setError] = useState<string | null>(null);
  const load = useCallback(async () => {
    try {
      setError(null);
      const [quality, list] = await Promise.all([fetchAgentQuality(days), fetchAgentRuns(agent || undefined, outcome || undefined, 60)]);
      setQ(quality); setRuns(list);
    } catch (e: any) { setError(e.message); }
  }, [days, agent, outcome]);
  useEffect(() => { load(); }, [load]);

  const o = q?.overall;
  return (
    <div className="flex-1 overflow-y-auto bg-slate-950 text-slate-100">
      <div className="px-4 sm:px-6 pt-6 pb-2 max-w-[1300px] mx-auto flex flex-wrap items-end justify-between gap-4">
        <div>
          <BackToParent tab="agent-quality" can={can} />
          <h1 className="text-2xl font-semibold tracking-tight text-slate-100">Agent quality</h1>
          <p className="text-sm text-slate-500 mt-1">How often people keep what the agents produce, how much they change, and why each agent did what it did.</p>
        </div>
        <div className="flex items-center gap-1 rounded-lg border border-slate-800 bg-slate-900 p-1">
          {[7, 30, 90].map(n => (
            <button key={n} onClick={() => setDays(n)}
              className={`px-3 py-1.5 rounded-md text-xs font-semibold cursor-pointer ${days === n ? 'bg-slate-800 text-slate-100' : 'text-slate-500 hover:text-slate-300'}`}>
              Last {n} days
            </button>
          ))}
        </div>
      </div>
      <div className="px-4 sm:px-6 py-4 max-w-[1300px] mx-auto space-y-5">
        {error && <div className="p-3 rounded-lg border border-rose-800/60 bg-rose-950 text-rose-300 text-sm">{error}</div>}
        {o && q && (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 2xl:grid-cols-5 gap-3">
            <Tile icon="task_alt" label="Implicit acceptance" value={pct(o.acceptance_rate)} target="> 75%"
              good={o.acceptance_rate == null ? null : o.acceptance_rate >= q.targets.acceptance_rate}
              note={`${o.accepted} kept, ${o.edited} corrected, ${o.rejected} rejected`} />
            <Tile icon="difference" label="Correction delta" value={o.avg_edit_ratio == null ? '—' : `${Math.round(o.avg_edit_ratio * 100)}%`}
              target="approaching 0" good={o.avg_edit_ratio == null ? null : o.avg_edit_ratio <= 0.1}
              note={o.avg_edit_distance == null ? undefined : `avg ${o.avg_edit_distance} characters`} />
            <Tile icon="check_circle" label="Task completion" value={pct(o.completion_rate)} target="> 95%"
              good={o.completion_rate == null ? null : o.completion_rate >= q.targets.completion_rate} note={`${o.failed} failed`} />
            <Tile icon="data_usage" label="Tokens per run" value={num(o.tokens_per_run)} target="falling"
              good={null} note={o.context_tokens_per_run == null ? undefined : `${num(o.context_tokens_per_run)} of it context`} />
            <Tile icon="support_agent" label="People stepping in" value={num(q.hitl_interventions)} target="falling" good={null} note="tickets raised" />
          </div>
        )}

        {q && (
          <section className="rounded-2xl border border-slate-800 bg-slate-900 p-5 shadow-sm">
            <h3 className="text-[15px] font-semibold text-slate-100 mb-3">By agent</h3>
            <div className="overflow-x-auto">
              <table className="w-full text-[12.5px]">
                <thead><tr className="text-left text-slate-500 text-[11px] uppercase tracking-wider">
                  <th className="py-2 pr-3">Agent</th><th className="pr-3">Runs</th><th className="pr-3">Accepted</th>
                  <th className="pr-3">Correction</th><th className="pr-3">Completed</th><th className="pr-3">Tokens / run</th><th>Waiting</th>
                </tr></thead>
                <tbody>
                  {q.agents.map(a => (
                    <tr key={a.key} className="border-t border-slate-800">
                      <td className="py-2 pr-3 text-slate-100">{a.label}</td>
                      <td className="pr-3 tabular-nums">{a.runs}</td>
                      <td className="pr-3 tabular-nums">{pct(a.acceptance_rate)}</td>
                      <td className="pr-3 tabular-nums">{a.avg_edit_ratio == null ? '—' : `${Math.round(a.avg_edit_ratio * 100)}%`}</td>
                      <td className="pr-3 tabular-nums">{pct(a.completion_rate)}</td>
                      <td className="pr-3 tabular-nums">{num(a.tokens_per_run)}</td>
                      <td className="tabular-nums">{a.pending}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {q.weeks.length > 0 && (
              <>
                <h4 className="text-[12px] uppercase tracking-wider text-slate-500 mt-5 mb-2">Week by week</h4>
                <div className="overflow-x-auto">
                  <table className="w-full text-[12.5px]">
                    <thead><tr className="text-left text-slate-500 text-[11px] uppercase tracking-wider">
                      <th className="py-1.5 pr-3">Week of</th><th className="pr-3">Runs</th><th className="pr-3">Accepted</th>
                      <th className="pr-3">Correction</th><th className="pr-3">Completed</th><th className="pr-3">Tokens / run</th><th>People stepped in</th>
                    </tr></thead>
                    <tbody>
                      {q.weeks.map(w => (
                        <tr key={w.week} className="border-t border-slate-800">
                          <td className="py-1.5 pr-3">{w.week}</td><td className="pr-3 tabular-nums">{w.runs}</td>
                          <td className="pr-3 tabular-nums">{pct(w.acceptance_rate)}</td>
                          <td className="pr-3 tabular-nums">{w.avg_edit_ratio == null ? '—' : `${Math.round(w.avg_edit_ratio * 100)}%`}</td>
                          <td className="pr-3 tabular-nums">{pct(w.completion_rate)}</td>
                          <td className="pr-3 tabular-nums">{num(w.tokens_per_run)}</td><td className="tabular-nums">{w.hitl}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </>
            )}
          </section>
        )}

        <section className="rounded-2xl border border-slate-800 bg-slate-900 p-5 shadow-sm">
          <div className="flex flex-wrap items-center justify-between gap-3 mb-3">
            <h3 className="text-[15px] font-semibold text-slate-100">Runs</h3>
            <div className="flex flex-wrap gap-2">
              <select value={agent} onChange={e => setAgent(e.target.value)}
                className="bg-slate-950 border border-slate-800 rounded-lg px-2 py-1.5 text-[12px] text-slate-200">
                <option value="">Every agent</option>
                {q?.agents.map(a => <option key={a.key} value={a.key}>{a.label}</option>)}
              </select>
              <select value={outcome} onChange={e => setOutcome(e.target.value)}
                className="bg-slate-950 border border-slate-800 rounded-lg px-2 py-1.5 text-[12px] text-slate-200">
                <option value="">Every outcome</option>
                {Object.entries(OUTCOME).map(([k, v]) => <option key={k} value={k}>{v.label}</option>)}
              </select>
            </div>
          </div>
          <ul className="space-y-2">
            {runs.map(r => <RunRow key={r.id} r={r} />)}
            {runs.length === 0 && <li className="py-6 text-center text-[12.5px] text-slate-500">No runs yet: they appear as the agents work.</li>}
          </ul>
        </section>
      </div>
    </div>
  );
};
