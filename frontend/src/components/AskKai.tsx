import React, { useEffect, useRef, useState } from 'react';
import { askKai, fetchAskStatus, fetchAsked, type AskState, type AskStatus } from '../api/insights';
import { formatDateTime } from '../utils/datetime';

/**
 * The search bar at the top of the Plan tab: anyone signed in asks Kiosk KAI
 * about AutoGMap, the application form or TARA's CSPs and revenue, in plain
 * words, and reads the answer here with the tools it came from.
 *
 * An answer takes up to a few minutes, so the question is started and then
 * asked after every few seconds. The last few answers stay in this browser.
 */

const Icon: React.FC<{ name: string; className?: string; style?: React.CSSProperties }> = ({ name, className = '', style }) =>
  <span className={`material-symbols-outlined ${className}`} style={style}>{name}</span>;

const SUGGESTIONS: { icon: string; text: string }[] = [
  { icon: 'currency_rupee', text: "How is this month's revenue in TARA against the ₹1 Cr goal?" },
  { icon: 'troubleshoot', text: 'Where is our agent losing people on the way to a lead?' },
  { icon: 'description', text: "What happened to AutoGMap's applications in the Kiosk form?" },
  { icon: 'map', text: 'Which districts need a campaign, and do we have businesses left there?' },
];

// While it works: what Kiosk KAI can look at, not a claim of what it is doing.
const HINTS = [
  'Reading AutoGMap’s campaigns and funnel…',
  'Looking at the Kiosk Application Form…',
  'Checking TARA’s CSPs and revenue…',
  'Putting the answer together…',
];

const SYSTEMS: Record<string, { label: string; cls: string }> = {
  autogmap: { label: 'AutoGMap', cls: 'bg-emerald-950 text-emerald-300 border-emerald-800' },
  ekokiosk: { label: 'Kiosk form', cls: 'bg-amber-950 text-amber-300 border-amber-800' },
  tara: { label: 'TARA', cls: 'bg-purple-950 text-purple-300 border-purple-800' },
  core: { label: 'Kiosk KAI', cls: 'bg-slate-800 text-slate-300 border-slate-700' },
};

const KEEP = 6;
const STORE = 'kai-asks';

const loadPast = (): AskState[] => {
  try { return JSON.parse(localStorage.getItem(STORE) || '[]'); } catch { return []; }
};
const savePast = (rows: AskState[]) => {
  try { localStorage.setItem(STORE, JSON.stringify(rows.slice(0, KEEP))); } catch { /* private window */ }
};

// --- A small, safe reader for the answer's Markdown: no HTML is injected. ----

const inline = (text: string, key: string): React.ReactNode[] =>
  text.split(/(\*\*[^*]+\*\*|`[^`]+`)/g).filter(Boolean).map((part, i) => {
    if (part.startsWith('**') && part.endsWith('**'))
      return <strong key={`${key}-${i}`} className="font-semibold text-slate-100">{part.slice(2, -2)}</strong>;
    if (part.startsWith('`') && part.endsWith('`'))
      return <code key={`${key}-${i}`} className="px-1 py-0.5 rounded bg-slate-800 text-[12px]">{part.slice(1, -1)}</code>;
    return <React.Fragment key={`${key}-${i}`}>{part}</React.Fragment>;
  });

const cells = (line: string) => line.trim().replace(/^\||\|$/g, '').split('|').map(c => c.trim());

const Answer: React.FC<{ text: string }> = ({ text }) => {
  const lines = text.split('\n');
  const out: React.ReactNode[] = [];
  let i = 0;
  while (i < lines.length) {
    const line = lines[i];
    const t = line.trim();
    if (!t) { i++; continue; }
    if (t.startsWith('|')) {
      const rows: string[] = [];
      while (i < lines.length && lines[i].trim().startsWith('|')) rows.push(lines[i++]);
      const body = rows.filter(r => !/^\s*\|?[\s:-]+(\|[\s:-]+)*\|?\s*$/.test(r));
      const [head, ...rest] = body;
      out.push(
        <div key={`t${i}`} className="overflow-x-auto my-2 rounded-lg border border-slate-800">
          <table className="w-full text-[13px]">
            <thead className="bg-slate-800/60 text-slate-300">
              <tr>{cells(head).map((c, j) => <th key={j} className="text-left font-semibold px-3 py-1.5">{inline(c, `h${i}${j}`)}</th>)}</tr>
            </thead>
            <tbody>
              {rest.map((r, k) => (
                <tr key={k} className="border-t border-slate-800">
                  {cells(r).map((c, j) => <td key={j} className="px-3 py-1.5 text-slate-300 tabular-nums">{inline(c, `c${i}${k}${j}`)}</td>)}
                </tr>
              ))}
            </tbody>
          </table>
        </div>,
      );
      continue;
    }
    const heading = t.match(/^#{1,4}\s+(.*)$/);
    if (heading) {
      out.push(<h4 key={i} className="text-[14px] font-semibold text-slate-100 mt-3 mb-1">{inline(heading[1], `g${i}`)}</h4>);
      i++; continue;
    }
    if (/^([-*•]|\d+[.)])\s+/.test(t)) {
      const ordered = /^\d/.test(t);
      const items: string[] = [];
      while (i < lines.length && /^([-*•]|\d+[.)])\s+/.test(lines[i].trim()))
        items.push(lines[i++].trim().replace(/^([-*•]|\d+[.)])\s+/, ''));
      const List = ordered ? 'ol' : 'ul';
      out.push(
        <List key={`l${i}`} className={`${ordered ? 'list-decimal' : 'list-disc'} pl-5 my-1.5 space-y-1 marker:text-emerald-400`}>
          {items.map((it, j) => <li key={j}>{inline(it, `l${i}${j}`)}</li>)}
        </List>,
      );
      continue;
    }
    out.push(<p key={i} className="my-1.5">{inline(t, `p${i}`)}</p>);
    i++;
  }
  return <div className="text-[14px] leading-relaxed text-slate-300">{out}</div>;
};

const ToolChip: React.FC<{ tool: string }> = ({ tool }) => {
  const sys = SYSTEMS[tool.split('.')[0]] || SYSTEMS.core;
  return (
    <span className={`inline-flex items-center gap-1 text-[11px] px-2 py-0.5 rounded-full border ${sys.cls}`} title={tool}>
      <span className="font-semibold">{sys.label}</span>
      <span className="opacity-75">{tool.split('.').slice(1).join('.').replace(/_/g, ' ') || tool}</span>
    </span>
  );
};

const Result: React.FC<{ a: AskState }> = ({ a }) => (
  <section className="rounded-xl border border-slate-800 bg-slate-900 shadow-sm overflow-hidden">
    <header className="flex items-start gap-3 px-5 pt-4 pb-3 border-b border-slate-800">
      <span className="h-9 w-9 shrink-0 rounded-lg flex items-center justify-center bg-sky-950 text-sky-300">
        <Icon name="forum" className="text-[20px]" />
      </span>
      <div className="min-w-0 flex-1">
        <div className="text-[11px] uppercase tracking-[0.12em] font-semibold text-slate-500">You asked</div>
        <h3 className="text-[15px] font-semibold text-slate-100 leading-snug">{a.question}</h3>
      </div>
      {a.status === 'done' && (
        <span className="shrink-0 text-[11px] text-slate-500 flex items-center gap-1 mt-1">
          <Icon name="timer" className="text-[14px]" />{a.seconds}s
        </span>
      )}
    </header>
    <div className="px-5 py-4">
      {a.status === 'done' && a.answer && <Answer text={a.answer} />}
      {a.status === 'failed' && (
        <div className="flex items-start gap-2 text-sm text-rose-300 bg-rose-950/40 border border-rose-900 rounded-lg px-3 py-2">
          <Icon name="error" className="text-[18px]" />{a.error}
        </div>
      )}
      {a.status === 'done' && (!!a.tools?.length || a.as_of || !!a.caveats?.length) && (
        <div className="mt-4 pt-3 border-t border-slate-800 space-y-2">
          {!!a.tools?.length && (
            <div className="flex flex-wrap items-center gap-1.5">
              <span className="text-[11px] text-slate-500 mr-1">Read from</span>
              {a.tools.map(t => <ToolChip key={t} tool={t} />)}
            </div>
          )}
          {a.as_of && <div className="text-[11px] text-slate-500">Figures as of {formatDateTime(a.as_of)}</div>}
          {a.caveats?.map((c, i) => (
            <div key={i} className="text-[12px] text-amber-300/90 flex items-start gap-1.5">
              <Icon name="info" className="text-[15px] mt-px" />{c}
            </div>
          ))}
        </div>
      )}
    </div>
  </section>
);

export const AskKai: React.FC = () => {
  const [status, setStatus] = useState<AskStatus | null>(null);
  const [q, setQ] = useState('');
  const [current, setCurrent] = useState<AskState | null>(null);
  const [past, setPast] = useState<AskState[]>(loadPast);
  const [error, setError] = useState<string | null>(null);
  const [tick, setTick] = useState(0);
  const timer = useRef<number | null>(null);

  useEffect(() => { fetchAskStatus().then(setStatus).catch(() => setStatus(null)); }, []);
  useEffect(() => () => { if (timer.current) window.clearTimeout(timer.current); }, []);

  const running = current?.status === 'running';
  useEffect(() => {
    if (!running) return;
    const t = window.setInterval(() => setTick(n => n + 1), 1000);
    return () => window.clearInterval(t);
  }, [running]);

  const follow = (id: string) => {
    timer.current = window.setTimeout(async () => {
      try {
        const a = await fetchAsked(id);
        setCurrent(a);
        if (a.status === 'running') return follow(id);
        if (a.status === 'done') {
          setPast(p => { const next = [a, ...p.filter(x => x.question !== a.question)].slice(0, KEEP); savePast(next); return next; });
        }
      } catch (e) {
        setCurrent(c => c && { ...c, status: 'failed', error: (e as Error).message });
      }
    }, 3000);
  };

  const submit = async (question: string) => {
    const text = question.trim();
    if (text.length < 3 || running || !status?.enabled) return;
    setError(null);
    setQ(text);
    setTick(0);
    try {
      const a = await askKai(text);
      setStatus(s => s && { ...s, left_today: Math.max(0, s.left_today - 1) });
      setCurrent(a);
      follow(a.id);
    } catch (e) {
      setError((e as Error).message);
    }
  };

  const enabled = !!status?.enabled && status.left_today > 0;
  const hint = HINTS[Math.floor(tick / 6) % HINTS.length];

  return (
    <div className="space-y-4 mb-6">
      <section className="relative rounded-2xl overflow-hidden shadow-md text-white"
        style={{ background: 'linear-gradient(115deg, #0a3543 0%, #154a5f 45%, #23506f 75%, #2f4a7d 100%)' }}>
        {/* Soft light behind the title, for depth; clipped in its own layer,
            or the banner could be scrolled sideways to it. */}
        <div className="pointer-events-none absolute inset-0 overflow-hidden">
          <div className="absolute -top-24 -right-16 h-64 w-64 rounded-full opacity-30 blur-3xl"
            style={{ background: 'radial-gradient(circle, #f9ab10 0%, transparent 70%)' }} />
          <div className="absolute -bottom-28 left-1/3 h-64 w-64 rounded-full opacity-25 blur-3xl"
            style={{ background: 'radial-gradient(circle, #2dd4bf 0%, transparent 70%)' }} />
        </div>
        <div className="relative p-6">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <div className="text-[11px] uppercase tracking-[0.14em] font-semibold flex items-center gap-1.5" style={{ color: '#f9ab10' }}>
                <Icon name="auto_awesome" className="text-[15px]" />Ask Kiosk KAI
              </div>
              <h2 className="text-xl font-semibold mt-1">Ask anything about AutoGMap, the form or TARA</h2>
              <p className="text-sm text-white/70 mt-0.5 max-w-2xl">
                Revenue and CSPs from TARA, applications from the Kiosk form, and how our campaigns and agent are doing.
                Every figure comes with its source and date.
              </p>
            </div>
            {status?.chat_url && (
              <a href={status.chat_url} target="_blank" rel="noreferrer"
                className="shrink-0 text-xs font-medium text-white/85 hover:text-white px-3 py-1.5 rounded-full bg-white/10 hover:bg-white/15 flex items-center gap-1 transition-colors">
                Full chat<Icon name="open_in_new" className="text-[14px]" />
              </a>
            )}
          </div>

          <form className="mt-4" onSubmit={e => { e.preventDefault(); submit(q); }}>
            <div className={`flex items-center gap-2 rounded-xl bg-white pl-4 pr-1.5 py-1.5 shadow-lg ring-2 transition ${running ? 'ring-[#f9ab10]/70' : 'ring-transparent focus-within:ring-[#5eead4]/70'}`}>
              <Icon name="search" className="text-[22px] text-[#16435a]" />
              <input
                value={q}
                onChange={e => setQ(e.target.value)}
                disabled={!enabled || running}
                maxLength={600}
                placeholder={enabled ? 'e.g. Which circles grew revenue this month, and did any of our leads go live?'
                  : status?.enabled ? "Today's questions are used up; ask again tomorrow" : 'Asking turns on once the app has its Kiosk KAI key'}
                className="flex-1 min-w-0 bg-transparent text-[15px] text-[#0a3543] placeholder:text-slate-400 outline-none py-2 disabled:cursor-not-allowed"
              />
              <button type="submit" disabled={!enabled || running || q.trim().length < 3}
                className="shrink-0 rounded-lg px-4 py-2 text-sm font-semibold text-[#0a3543] disabled:opacity-50 flex items-center gap-1.5 transition hover:brightness-105"
                style={{ background: '#f9ab10' }}>
                {running ? <Icon name="progress_activity" className="text-[18px] animate-spin" /> : <Icon name="send" className="text-[18px]" />}
                {running ? 'Asking' : 'Ask'}
              </button>
            </div>
          </form>

          {running && (
            <div className="mt-3 flex items-center gap-2 text-[13px] text-white/80">
              <span className="relative flex h-2.5 w-2.5">
                <span className="absolute inline-flex h-full w-full rounded-full opacity-75 animate-ping" style={{ background: '#fcd34d' }} />
                <span className="relative inline-flex rounded-full h-2.5 w-2.5" style={{ background: '#fcd34d' }} />
              </span>
              {hint}<span className="text-white/50 tabular-nums">{tick}s · answers can take a few minutes</span>
            </div>
          )}
          {error && (
            <div className="mt-3 text-[13px] flex items-center gap-1.5" style={{ color: '#fecdd3' }}>
              <Icon name="error" className="text-[16px]" />{error}
            </div>
          )}
          {status?.enabled && (
            <div className="mt-2 text-[11.5px] text-white/55 flex items-center gap-1">
              <Icon name="toll" className="text-[14px]" />
              {status.left_today} of {status.daily_max} questions left today · Kiosk KAI's budget is shared by the team
            </div>
          )}
          {status && !status.enabled && (
            <div className="mt-3 text-[12px] text-white/70 flex items-start gap-1.5">
              <Icon name="key" className="text-[15px] mt-px" />
              Turns on when the app's own Kiosk KAI key (KIOSK_KAI_APP_KEY) is set on the server. Until then, use the full chat with your own sign-in.
            </div>
          )}

          <div className="mt-4 flex flex-wrap gap-2">
            {SUGGESTIONS.map(s => (
              <button key={s.text} type="button" onClick={() => submit(s.text)} disabled={!enabled || running}
                className="text-[12.5px] text-white/90 px-3 py-1.5 rounded-full bg-white/10 hover:bg-white/20 border border-white/10 flex items-center gap-1.5 transition disabled:opacity-50 disabled:cursor-not-allowed">
                <Icon name={s.icon} className="text-[15px]" style={{ color: '#f9ab10' }} />{s.text}
              </button>
            ))}
          </div>
        </div>
      </section>

      {current && current.status !== 'running' && <Result a={current} />}

      {past.filter(p => p.id !== current?.id).length > 0 && (
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-[11px] uppercase tracking-[0.12em] font-semibold text-slate-500 flex items-center gap-1">
            <Icon name="history" className="text-[14px]" />Asked earlier
          </span>
          {past.filter(p => p.id !== current?.id).map(p => (
            <button key={p.id} type="button" onClick={() => setCurrent(p)} disabled={running}
              className="text-[12px] text-slate-300 px-2.5 py-1 rounded-full bg-slate-900 border border-slate-800 hover:border-sky-700 max-w-[320px] truncate disabled:opacity-50">
              {p.question}
            </button>
          ))}
        </div>
      )}
    </div>
  );
};
