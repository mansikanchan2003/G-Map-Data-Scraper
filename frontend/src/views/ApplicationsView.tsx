import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { SubPageButton } from '../components/SubPage';
import type { NavTab } from '../components/Header';
import {
  fetchApplications, addApplicationComment, deleteApplicationComment, removeApplication,
  restoreApplication, documentUrl, fetchLeadBrief, type Application, type ApplicationStats, type LeadBrief,
} from '../api/applications';
import { formatDateTime } from '../utils/datetime';
import { recorderNumbersExcelUrl } from '../api/inbox';
import { QualifiedLeadsView } from './QualifiedLeadsView';
import { LeadJourneyView } from './LeadJourneyView';

/**
 * Everyone who started onboarding through the WhatsApp bot: how far they got,
 * whether they qualify, their documents, and the team's comments.
 *
 * Colours come from the theme ramps (slate, sky, emerald, rose, amber,
 * purple), which the light theme redefines, so the page reads in both.
 */

type Filter = 'all' | 'pin' | 'strong' | 'not' | 'submitted' | 'esaf';

const FILTERS: { key: Filter; label: string; hint: string; icon: string; tint: string; ring: string; pick: (a: Application) => boolean }[] = [
  { key: 'all', label: 'All applications', hint: 'Started onboarding on WhatsApp', icon: 'groups',
    tint: 'bg-sky-950 text-sky-300', ring: 'ring-sky-500', pick: () => true },
  { key: 'pin', label: 'PIN qualified', hint: 'PIN within our area', icon: 'location_on',
    tint: 'bg-sky-950 text-sky-300', ring: 'ring-sky-500', pick: a => a.pin_qualified },
  { key: 'strong', label: 'Strongly qualified', hint: 'Area + 12th or above + can invest ₹5 lakh, or said yes to ESAF', icon: 'verified',
    tint: 'bg-emerald-950 text-emerald-300', ring: 'ring-emerald-500', pick: a => a.strongly_qualified },
  { key: 'not', label: 'Not qualified', hint: 'Outside area, below 12th or cannot invest', icon: 'block',
    tint: 'bg-rose-950 text-rose-300', ring: 'ring-rose-500', pick: a => a.not_qualified },
  { key: 'submitted', label: 'Submitted', hint: 'Uploaded their documents', icon: 'task_alt',
    tint: 'bg-amber-950 text-amber-300', ring: 'ring-amber-400', pick: a => a.submitted },
  // 19 Nov 2026: everyone who chose ESAF's banking agent (on the bot, on a call or by the team).
  { key: 'esaf', label: 'Interested in ESAF', hint: "Chose ESAF's banking agent (₹1,999 registration)", icon: 'account_balance',
    tint: 'bg-violet-950 text-violet-300', ring: 'ring-violet-500', pick: a => a.programme === 'esaf' },
];

// The simple view (16 Nov 2026, Kavya's account: auth_service.ui_prefs): every part of the page
// stays, in plainer words, with the next step on each row and buttons that say what they do.
const PLAIN: Record<Filter, { label: string; hint: string }> = {
  all: { label: 'Everyone', hint: 'Everyone who started applying on WhatsApp' },
  pin: { label: 'In our SBI area', hint: 'Their PIN code is near one of our SBI branches' },
  strong: { label: 'Fully qualified', hint: 'In our area, 12th or above, and can invest (or chose ESAF)' },
  not: { label: 'Not eligible for SBI', hint: 'Outside our area, below 12th, or cannot invest' },
  submitted: { label: 'Documents received', hint: 'Sent all their documents' },
  esaf: { label: 'Interested in ESAF', hint: 'Want ESAF (₹1,999), not SBI' },
};
const PLAIN_FUNNEL: Record<string, string> = {
  Applied: 'Started applying', 'PIN qualified': 'In our SBI area', 'Strongly qualified': 'Fully qualified', Submitted: 'Sent documents',
};

/** What to do next with this person, in plain words, and how urgent (a colour). */
export function nextStep(a: Application): { text: string; tone: 'emerald' | 'violet' | 'amber' | 'sky' | 'slate' } {
  const reasons = a.not_qualified_reasons || [];
  const outside = reasons.length > 0 && reasons.every(r => r.startsWith('Not qualified for SBI'));
  if (reasons.includes('Below 12th')) return { text: 'Below 12th: not eligible. Nothing to do.', tone: 'slate' };
  if (a.bot_step === 'ESAF_DECLINED') return { text: 'Said no to SBI and ESAF. Nothing to do.', tone: 'slate' };
  if (a.submitted && a.esaf) return { text: 'Documents in. Call for the ESAF registration (₹1,999) and shop visit.', tone: 'emerald' };
  if (a.submitted && outside) return { text: 'Documents in, but outside our SBI area. Call and offer ESAF.', tone: 'emerald' };
  if (a.submitted) return { text: 'Documents in. Check them and hand over for the branch visit.', tone: 'emerald' };
  if (a.esaf) return { text: 'Wants ESAF. Call about the ₹1,999 registration and documents.', tone: 'violet' };
  if (a.bot_step === 'AWAIT_UPLOAD' || a.bot_step === 'AWAIT_DOCS') return { text: 'Call and help them upload their documents.', tone: 'amber' };
  if (a.can_invest === false || ['NOT_INVESTING', 'ESAF_OFFERED', 'ESAF_DETAILS'].includes(a.bot_step || ''))
    return { text: 'Cannot invest ₹3–5 lakh. Call and offer ESAF.', tone: 'sky' };
  if (outside) return { text: 'Outside our SBI area. Call and offer ESAF.', tone: 'sky' };
  if ((a.bot_step || '').startsWith('WEBINAR') || a.bot_step === 'GUIDANCE_QA') return { text: 'Wants guidance. Call and answer their questions.', tone: 'sky' };
  return { text: 'The bot is talking to them. No action yet.', tone: 'slate' };
}
const PLAIN_VERDICT: Record<string, string> = {
  'Strongly qualified': 'Fully qualified', 'Strongly qualified · ESAF': 'Fully qualified · ESAF',
  'PIN qualified': 'In our SBI area', 'PIN qualified · ESAF': 'In our SBI area · ESAF',
  'Not qualified for SBI branch code': 'Outside our SBI area', 'Not qualified': 'Not eligible', 'In progress': 'Still answering',
};
const NEXT_TONE = {
  emerald: 'bg-emerald-500/10 border-emerald-500/30 text-emerald-300', violet: 'bg-violet-500/10 border-violet-500/30 text-violet-300',
  amber: 'bg-amber-500/10 border-amber-500/30 text-amber-300', sky: 'bg-sky-500/10 border-sky-500/30 text-sky-300',
  slate: 'bg-slate-500/10 border-slate-700 text-slate-400',
};

const VERDICT_STYLE: Record<string, string> = {
  'Strongly qualified': 'bg-emerald-950 border-emerald-800/60 text-emerald-300',
  // For ESAF's banking agent: qualified, in ESAF's violet so the team sees the track at a glance.
  'Strongly qualified · ESAF': 'bg-violet-950 border-violet-700/60 text-violet-300',
  'PIN qualified · ESAF': 'bg-violet-950 border-violet-800/60 text-violet-300',
  'PIN qualified': 'bg-sky-950 border-sky-800/60 text-sky-300',
  'Not qualified': 'bg-rose-950 border-rose-800/60 text-rose-300',
  'In progress': 'bg-slate-950 border-slate-800 text-slate-400',
};

// The onboarding steps, in order, for the progress dots on each row.
const STEPS = ['Language', 'PIN', 'Education', 'Investment', 'Documents', 'Upload', 'Submitted'];
const STEP_OF: Record<string, number> = {
  CHOOSE_LANG: 0, AWAIT_PIN: 1, NOT_SERVED: 1, AWAIT_EDUCATION: 2, NOT_ELIGIBLE: 2,
  AWAIT_FRANCHISE: 3, AWAIT_INVEST: 3, NOT_INVESTING: 3, AWAIT_DOCS: 4, AWAIT_UPLOAD: 5, SUBMITTED: 6, HANDOVER: 1,
  // ESAF, offered to those who cannot invest for SBI (11 Nov 2026): it starts at the investment step.
  ESAF_OFFERED: 3, ESAF_DETAILS: 3, ESAF_INTERESTED: 3, ESAF_DECLINED: 3,
};
const STOPPED = new Set(['NOT_SERVED', 'NOT_ELIGIBLE', 'NOT_INVESTING', 'ESAF_DECLINED']);

const FILTER_INPUT = 'w-full h-8 px-2 rounded-md border border-slate-800 bg-slate-900 text-[12px] text-slate-200 outline-none focus:border-sky-500';
const yesNo = (v: boolean | null | undefined) => (v === true ? 'Yes' : v === false ? 'No' : '—');
const csvCell = (v: unknown) => `"${String(v ?? '').replace(/"/g, '""')}"`;
const Icon: React.FC<{ name: string; className?: string }> = ({ name, className = '' }) =>
  <span className={`material-symbols-outlined ${className}`}>{name}</span>;
const initials = (name: string | null, phone: string) =>
  (name || '').trim().split(/\s+/).slice(0, 2).map(w => w[0]).join('').toUpperCase() || phone.slice(-2);
const place = (a: Application) => [a.tehsil, a.district, a.state].filter(Boolean).join(', ');
// "SBI Chotila (60104) · AO Ahmedabad · 12 km"
/** "CSPs near DCs": an SBI-allocated CSP centre in a District Coordinator's district (17 Nov 2026). */
const NearDc: React.FC<{ a: Application }> = ({ a }) => (
  <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-teal-500/15 border border-teal-500/40 text-teal-300 text-[11px] font-semibold whitespace-nowrap"
    title={a.csp_centre ? `SBI CSP centre ${a.csp_centre.name}${a.csp_centre.code ? ` (${a.csp_centre.code})` : ''}, ${a.csp_centre.distance_km} km away` : 'Reached as one of the CSPs near DCs'}>
    <Icon name="share_location" className="text-[13px]" />CSPs near DCs
  </span>
);

/** Who the lead is for (19 Nov 2026): For SBI, unless they chose ESAF. */
const ProgrammeChip: React.FC<{ a: Application }> = ({ a }) => a.programme === 'esaf'
  ? <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-violet-500/15 border border-violet-500/40 text-violet-300 text-[11px] font-semibold whitespace-nowrap"
      title="Chose ESAF's banking agent: ₹1,999 registration, no big investment"><Icon name="account_balance_wallet" className="text-[13px]" />Interested in ESAF</span>
  : <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-sky-500/15 border border-sky-500/40 text-sky-300 text-[11px] font-semibold whitespace-nowrap"
      title="For SBI's Customer Service Point (₹3–5 lakh, depending on location)"><Icon name="account_balance" className="text-[13px]" />For SBI</span>;

const branch = (a: Application) => a.sbi_branch && [
  `SBI ${a.sbi_branch.branch_name} (${a.sbi_branch.branch_code})`, a.sbi_branch.ao,
  a.sbi_branch.distance_km ? `${a.sbi_branch.distance_km} km` : 'same PIN',
].filter(Boolean).join(' · ');

const Avatar: React.FC<{ a: Application; tone?: string }> = ({ a, tone = 'bg-sky-950 text-sky-300' }) => (
  <span className={`h-9 w-9 shrink-0 rounded-full text-xs font-bold flex items-center justify-center ${tone}`}>{initials(a.name, a.phone)}</span>
);

const IconButton: React.FC<{ icon: string; title: string; onClick?: () => void; href?: string; tone?: string; external?: boolean }> =
  ({ icon, title, onClick, href, tone = 'text-slate-400 hover:text-sky-300', external }) => {
  const cls = `h-8 w-8 rounded-full border border-slate-800 bg-slate-900 hover:bg-slate-950 flex items-center justify-center ${tone}`;
  return href
    ? <a href={href} title={title} className={cls} {...(external ? { target: '_blank', rel: 'noreferrer' } : {})}><Icon name={icon} className="text-[17px]" /></a>
    : <button onClick={onClick} title={title} className={cls}><Icon name={icon} className="text-[17px]" /></button>;
};

/** Seven dots, one per onboarding step: filled up to where they are, red where they were ruled out. */
const Progress: React.FC<{ a: Application }> = ({ a }) => {
  const at = a.submitted ? 6 : STEP_OF[a.bot_step || ''] ?? -1;
  const stopped = !a.submitted && STOPPED.has(a.bot_step || '');
  return (
    <div className="flex items-center gap-1" title={STEPS.map((s, i) => `${i <= at ? '●' : '○'} ${s}`).join('\n')}>
      {STEPS.map((s, i) => (
        <span key={s} className={`h-1.5 w-3 rounded-full ${i < at ? (a.submitted ? 'bg-amber-400' : 'bg-sky-500')
          : i === at ? (stopped ? 'bg-rose-500' : a.submitted ? 'bg-amber-400' : 'bg-sky-500') : 'bg-slate-800'}`} />
      ))}
    </div>
  );
};

export const ApplicationsView: React.FC<{ readOnly?: boolean; can?: (t: NavTab) => boolean; simple?: boolean }> = ({ readOnly, can, simple }) => {
  const [items, setItems] = useState<Application[]>([]);
  const [stats, setStats] = useState<ApplicationStats | null>(null);
  const [showRemoved, setShowRemoved] = useState(false);
  const [filter, setFilter] = useState<Filter>('all');
  const [search, setSearch] = useState('');
  const [stage, setStage] = useState('');
  // A filter under every column heading (19 Nov 2026, Kavya's view and everyone's).
  const [col, setCol] = useState({ who: '', next: '', place: '', programme: '', verdict: '', comment: '' });
  const setColumn = (k: keyof typeof col, v: string) => setCol(c => ({ ...c, [k]: v }));
  const [briefFor, setBriefFor] = useState<string | null>(null);
  const [open, setOpen] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  // The Qualified leads page, at #applications/qualified so a refresh or a link lands there.
  const [qualifiedOpen, setQualifiedOpen] = useState(() => window.location.hash.startsWith('#applications/qualified'));
  // The Lead Journey page, at #applications/journey.
  const [journeyOpen, setJourneyOpen] = useState(() => window.location.hash.startsWith('#applications/journey'));
  useEffect(() => {
    const onHash = () => {
      setQualifiedOpen(window.location.hash.startsWith('#applications/qualified'));
      setJourneyOpen(window.location.hash.startsWith('#applications/journey'));
    };
    window.addEventListener('hashchange', onHash);
    return () => window.removeEventListener('hashchange', onHash);
  }, []);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetchApplications(showRemoved);
      setItems(res.items);
      setStats(res.stats);
      setError(null);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [showRemoved]);

  useEffect(() => { load(); }, [load]);

  const leads = useMemo(() => items.filter(a => a.submitted)
    .sort((a, b) => (b.submitted_at || '').localeCompare(a.submitted_at || '')), [items]);
  // Opens the application at its comment history, with the box ready to type in.
  const [commentFocus, setCommentFocus] = useState<string | null>(null);
  const openComments = (phone: string) => { setOpen(phone); setCommentFocus(phone); };
  const openRow = (phone: string) => {
    setFilter('all'); setStage(''); setSearch(''); setOpen(phone);
    setTimeout(() => document.getElementById(`app-${phone}`)?.scrollIntoView({ behavior: 'smooth', block: 'center' }), 50);
  };

  const stages = useMemo(() => Array.from(new Set(items.map(a => a.stage))).sort(), [items]);
  const shown = useMemo(() => {
    const q = search.trim().toLowerCase();
    const pick = FILTERS.find(f => f.key === filter)!.pick;
    const has = (vals: (string | null | undefined)[], text: string) =>
      !text.trim() || vals.some(v => (v || '').toLowerCase().includes(text.trim().toLowerCase()));
    return items.filter(a => pick(a)
      && (!stage || a.stage === stage)
      && has([a.name, a.phone], col.who)
      && (!col.next || nextStep(a).text === col.next)
      && has([a.pincode, a.state, a.district, a.tehsil, a.category, a.source?.business_name, a.sbi_branch?.branch_name], col.place)
      && (!col.programme || (a.programme || 'sbi') === col.programme)
      && (!col.verdict || a.verdict === col.verdict)
      && (!col.comment || (col.comment === 'with' ? a.comments.length > 0 : a.comments.length === 0))
      && (!q || [a.name, a.phone, a.pincode, a.state, a.district, a.tehsil, a.category, a.source?.campaign,
        a.sbi_branch?.branch_name, a.sbi_branch?.branch_code, a.sbi_branch?.ao].some(v => (v || '').toLowerCase().includes(q))));
  }, [items, filter, search, stage, col]);
  const nextSteps = useMemo(() => Array.from(new Set(items.map(a => nextStep(a).text))).sort(), [items]);
  const verdicts = useMemo(() => Array.from(new Set(items.map(a => a.verdict))).sort(), [items]);
  const filtering = Object.values(col).some(Boolean) || !!stage;
  const clearFilters = () => { setCol({ who: '', next: '', place: '', programme: '', verdict: '', comment: '' }); setStage(''); };

  const exportCsv = () => {
    const head = ['Name', 'Phone', 'Lead at', 'Category (persona)', 'Qualification', 'Verdict', 'Not qualified because', 'Franchise background',
      'Can invest ₹5 lakh', 'Stage', 'Documents', 'Required documents', 'Submitted at', 'Campaign', 'Comments', 'PIN code', 'State', 'District', 'Tehsil',
      'Nearest SBI branch', 'SBI branch code', 'AO', 'Distance to branch (km)'];
    const rows = shown.map(a => [a.name, a.phone, a.lead_at ? formatDateTime(a.lead_at) : '', a.category, a.qualification, a.verdict, a.not_qualified_reasons.join('; '),
      yesNo(a.franchise_background), yesNo(a.can_invest), a.stage, `${a.documents_count}/${a.documents_total}`,
      a.required_documents_done ? 'Done' : 'Missing', a.submitted_at ? formatDateTime(a.submitted_at) : '',
      a.source?.campaign, a.comments.map(c => `${formatDateTime(c.created_at)} ${c.author}: ${c.body}`).join(' | '),
      a.pincode, a.state, a.district, a.tehsil,
      a.sbi_branch?.branch_name, a.sbi_branch?.branch_code, a.sbi_branch?.ao, a.sbi_branch?.distance_km]);
    const csv = [head, ...rows].map(r => r.map(csvCell).join(',')).join('\n');
    const url = URL.createObjectURL(new Blob(['﻿' + csv], { type: 'text/csv;charset=utf-8' }));
    const link = document.createElement('a');
    link.href = url;
    link.download = `applications-${new Date().toISOString().slice(0, 10)}.csv`;
    link.click();
    URL.revokeObjectURL(url);
  };

  const remove = async (a: Application) => {
    if (!confirm(`Remove ${a.name || a.phone} from Applications?\n\nThe WhatsApp chat and uploaded documents are kept, and it can be restored from "Removed".`)) return;
    try { await removeApplication(a.phone); await load(); } catch (e: any) { alert(e.message); }
  };
  const restore = async (a: Application) => {
    try { await restoreApplication(a.phone); await load(); } catch (e: any) { alert(e.message); }
  };

  const total = stats?.total || 0;
  const count = (key: Filter) => key === 'all' ? stats?.total : key === 'pin' ? stats?.pin_qualified
    : key === 'strong' ? stats?.strongly_qualified : key === 'not' ? stats?.not_qualified
    : key === 'esaf' ? stats?.esaf : stats?.submitted;
  const funnel = [
    { label: 'Applied', value: total, icon: 'how_to_reg' },
    { label: 'PIN qualified', value: stats?.pin_qualified || 0, icon: 'location_on' },
    { label: 'Strongly qualified', value: stats?.strongly_qualified || 0, icon: 'verified' },
    { label: 'Submitted', value: stats?.submitted || 0, icon: 'task_alt' },
  ];

  if (journeyOpen) {
    return <LeadJourneyView onBack={() => { window.location.hash = 'applications'; }} />;
  }
  if (qualifiedOpen) {
    return <QualifiedLeadsView readOnly={readOnly} onBack={() => { window.location.hash = 'applications'; }} />;
  }

  return (
    <div className="flex-1 overflow-y-auto bg-slate-950 text-slate-100">
      <div className="px-6 pt-6 pb-2 max-w-[1500px] mx-auto flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight text-slate-100">{showRemoved ? 'Removed applications' : 'Applications'}</h1>
          <p className="text-sm text-slate-500 mt-1">{simple
            ? 'Everyone who started applying on WhatsApp, and what to do next with each person.'
            : 'People who started SBI Customer Service Point onboarding through the WhatsApp bot.'}</p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <button onClick={() => { window.location.hash = 'applications/qualified'; }}
            className="h-9 px-3.5 rounded-lg bg-emerald-500 hover:opacity-90 text-white text-sm font-semibold flex items-center gap-1.5 shadow-sm">
            <Icon name="workspace_premium" className="text-[18px]" />Qualified leads
          </button>
          <button onClick={() => { window.location.hash = 'applications/journey'; }}
            className="h-9 px-3.5 rounded-lg bg-violet-500 hover:opacity-90 text-white text-sm font-semibold flex items-center gap-1.5 shadow-sm">
            <Icon name="route" className="text-[18px]" />Lead Journey
          </button>
          {(!can || can('dispositions')) && (
            <SubPageButton tab="dispositions" label="Dispositions" icon="fact_check" className="bg-sky-600 text-white" />
          )}
          <button onClick={() => { setShowRemoved(v => !v); setOpen(null); }}
            className={`h-9 px-3.5 rounded-lg border text-sm font-medium flex items-center gap-1.5 shadow-sm ${showRemoved
              ? 'bg-amber-950 border-amber-800/60 text-amber-300' : 'bg-slate-900 border-slate-800 text-slate-300 hover:bg-slate-800'}`}>
            <Icon name={showRemoved ? 'arrow_back' : 'delete'} className="text-[18px]" />
            {showRemoved ? 'Back to applications' : `Removed (${stats?.removed ?? 0})`}
          </button>
          <button onClick={load} className="h-9 px-3.5 rounded-lg border border-slate-800 bg-slate-900 hover:bg-slate-800 text-sm font-medium text-slate-300 flex items-center gap-1.5 shadow-sm">
            <Icon name="sync" className={`text-[18px] ${loading ? 'animate-spin' : ''}`} /> Refresh
          </button>
        </div>
      </div>

      <div className="px-6 py-4 max-w-[1500px] mx-auto space-y-5">
        {error && <div className="p-3 rounded-lg border border-rose-800/60 bg-rose-950 text-rose-300 text-sm">{error}</div>}
        {simple && !showRemoved && (
          <div className="rounded-xl border border-sky-800/50 bg-sky-950 p-4 grid gap-3 sm:grid-cols-3 text-[13px] text-slate-200">
            {[
              ['touch_app', 'Tap a box below', 'to see only those people (for example, Documents received).'],
              ['assignment', 'Read "Next step"', 'on each row: it tells you what to do with that person.'],
              ['summarize', 'Press "Summary & script"', 'to see what was said, their PIN and education, and what to say on the call. Use the boxes under each heading to filter.'],
            ].map(([icon, b, rest]) => (
              <div key={b} className="flex items-start gap-2.5">
                <span className="h-8 w-8 shrink-0 rounded-lg bg-sky-500/20 text-sky-300 flex items-center justify-center"><Icon name={icon} className="text-[18px]" /></span>
                <span><b className="text-slate-100">{b}</b> {rest}</span>
              </div>
            ))}
          </div>
        )}

        {!showRemoved && <LeadsBlock leads={leads} onOpen={openRow} />}

        {!showRemoved && (
          <>
            {/* The five totals; each one filters the list. */}
            <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-6 gap-3">
              {FILTERS.map(f => (
                <button key={f.key} onClick={() => setFilter(f.key)}
                  className={`text-left p-4 rounded-xl border bg-slate-900 shadow-sm transition-all ${filter === f.key
                    ? `border-transparent ring-2 ${f.ring}` : 'border-slate-800 hover:border-slate-700 hover:-translate-y-0.5'}`}>
                  <div className="flex items-center justify-between">
                    <span className={`h-9 w-9 rounded-lg flex items-center justify-center ${f.tint}`}><Icon name={f.icon} className="text-[20px]" /></span>
                    <span className="text-2xl font-bold text-slate-100 tabular-nums">{count(f.key) ?? '—'}</span>
                  </div>
                  <div className="text-sm font-semibold text-slate-100 mt-3">{simple ? PLAIN[f.key].label : f.label}</div>
                  <div className="text-[11.5px] text-slate-500 mt-0.5 leading-snug">{simple ? PLAIN[f.key].hint : f.hint}</div>
                </button>
              ))}
            </div>

            {/* How far people get. */}
            <section className="rounded-xl border border-slate-800 bg-slate-900 shadow-sm p-5">
              <div className="flex items-center gap-2 mb-4">
                <Icon name="filter_alt" className="text-[20px] text-sky-300" />
                <h2 className="text-[15px] font-semibold text-slate-100">{simple ? 'How many reach each step' : 'How far applicants get'}</h2>
              </div>
              <ol className="grid grid-cols-2 lg:grid-cols-4 gap-3">
                {funnel.map((step, i) => {
                  const share = total ? Math.round((step.value / total) * 100) : 0;
                  const last = i === funnel.length - 1;
                  return (
                    <li key={step.label} className="relative">
                      <div className={`rounded-lg border p-4 h-full ${last ? 'border-amber-800/60 bg-amber-950' : 'border-slate-800 bg-slate-950/60'}`}>
                        <div className={`flex items-center gap-1.5 text-xs font-semibold ${last ? 'text-amber-300' : 'text-slate-400'}`}>
                          <Icon name={step.icon} className="text-[16px]" />{simple ? PLAIN_FUNNEL[step.label] || step.label : step.label}
                        </div>
                        <div className="flex items-baseline gap-2 mt-1.5">
                          <span className="text-2xl font-bold text-slate-100 tabular-nums">{step.value}</span>
                          <span className="text-xs text-slate-500">{simple ? `${share} in every 100` : `${share}% of applied`}</span>
                        </div>
                        <div className="h-1.5 rounded-full bg-slate-800 mt-2.5 overflow-hidden">
                          <div className={`h-full rounded-full ${last ? 'bg-amber-400' : 'bg-sky-500'}`} style={{ width: `${share}%` }} />
                        </div>
                      </div>
                      {!last && (
                        <span className="hidden lg:flex absolute -right-3 top-1/2 -translate-y-1/2 z-10 h-6 w-6 rounded-full bg-slate-900 border border-slate-800 items-center justify-center text-slate-500">
                          <Icon name="chevron_right" className="text-[16px]" />
                        </span>
                      )}
                    </li>
                  );
                })}
              </ol>
            </section>
          </>
        )}

        {/* The list, with search, stage and export. */}
        <section className="rounded-xl border border-slate-800 bg-slate-900 shadow-sm overflow-hidden">
          <div className="p-4 flex flex-wrap items-center gap-2 border-b border-slate-800">
            <div className="relative flex-1 min-w-[220px]">
              <Icon name="search" className="absolute left-3 top-1/2 -translate-y-1/2 text-[18px] text-slate-500" />
              <input value={search} onChange={e => setSearch(e.target.value)} placeholder={simple ? 'Search by name, phone or PIN code' : 'Search name, phone, PIN, area, category or campaign'}
                className="w-full h-10 pl-10 pr-3 rounded-lg border border-slate-800 bg-slate-950 text-sm text-slate-200 outline-none focus:border-sky-500" />
            </div>
            <select value={stage} onChange={e => setStage(e.target.value)}
              className="h-10 px-3 rounded-lg border border-slate-800 bg-slate-950 text-sm text-slate-200">
              <option value="">{simple ? 'Any step' : 'All stages'}</option>
              {stages.map(s => <option key={s} value={s}>{s}</option>)}
            </select>
            <button onClick={exportCsv} disabled={!shown.length}
              className="h-10 px-4 rounded-lg bg-emerald-500 hover:opacity-90 text-white text-sm font-semibold disabled:opacity-40 flex items-center gap-1.5">
              <Icon name="download" className="text-[18px]" /> Export CSV
            </button>
            {!readOnly && (
              <a href={recorderNumbersExcelUrl()} download data-edit
                title="Everyone on this tab as Phone | Name | Description | Active, for the call-recorder app's admin panel. Upload it there; do not email it."
                className="h-10 px-4 rounded-lg bg-purple-600 hover:opacity-90 text-white text-sm font-semibold flex items-center gap-1.5">
                <Icon name="perm_phone_msg" className="text-[18px]" /> Call-recorder Excel
              </a>
            )}
            <span className="text-xs text-slate-500 ml-1">{shown.length} shown</span>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-sm select-text">
              <thead className="bg-slate-950 text-[11px] uppercase tracking-wider text-slate-500">
                <tr>
                  {(simple ? ['Applicant', 'Next step', 'Place & business', 'Eligible?', 'Progress', 'Comment']
                    : ['Applicant', 'Business & place', 'Qualification', 'Progress', 'Comments', '']).map(h => (
                    <th key={h} className="px-3 py-2.5 text-left font-semibold whitespace-nowrap">{h}</th>
                  ))}
                </tr>
                <tr className="normal-case tracking-normal border-t border-slate-800 align-top">
                  <th className="px-2 py-2 font-normal">
                    <input value={col.who} onChange={e => setColumn('who', e.target.value)} placeholder="Name or phone" className={FILTER_INPUT} />
                  </th>
                  {simple && <th className="px-2 py-2 font-normal">
                    <select value={col.next} onChange={e => setColumn('next', e.target.value)} className={FILTER_INPUT}>
                      <option value="">Every next step</option>
                      {nextSteps.map(t => <option key={t} value={t}>{t}</option>)}
                    </select>
                  </th>}
                  <th className="px-2 py-2 font-normal">
                    <input value={col.place} onChange={e => setColumn('place', e.target.value)} placeholder="PIN, district, state or shop" className={FILTER_INPUT} />
                  </th>
                  <th className="px-2 py-2 font-normal space-y-1">
                    <select value={col.programme} onChange={e => setColumn('programme', e.target.value)} className={FILTER_INPUT}>
                      <option value="">SBI and ESAF</option>
                      <option value="sbi">For SBI</option>
                      <option value="esaf">Interested in ESAF</option>
                    </select>
                    <select value={col.verdict} onChange={e => setColumn('verdict', e.target.value)} className={FILTER_INPUT}>
                      <option value="">{simple ? 'Eligible or not' : 'Every verdict'}</option>
                      {verdicts.map(v => <option key={v} value={v}>{simple ? PLAIN_VERDICT[v] || v : v}</option>)}
                    </select>
                  </th>
                  <th className="px-2 py-2 font-normal">
                    <select value={stage} onChange={e => setStage(e.target.value)} className={FILTER_INPUT}>
                      <option value="">{simple ? 'Any step' : 'All stages'}</option>
                      {stages.map(t => <option key={t} value={t}>{t}</option>)}
                    </select>
                  </th>
                  <th className="px-2 py-2 font-normal">
                    <select value={col.comment} onChange={e => setColumn('comment', e.target.value)} className={FILTER_INPUT}>
                      <option value="">{simple ? 'Any' : 'All'}</option>
                      <option value="with">Has a comment</option>
                      <option value="none">No comment yet</option>
                    </select>
                    {simple && filtering && <button onClick={clearFilters} className="mt-1 text-[11.5px] font-semibold text-sky-300 hover:underline">Clear filters</button>}
                  </th>
                  {!simple && <th className="px-2 py-2 font-normal text-right">
                    {filtering && <button onClick={clearFilters} className="text-[11.5px] font-semibold text-sky-300 hover:underline whitespace-nowrap">Clear filters</button>}
                  </th>}
                </tr>
              </thead>
              <tbody className="[&>tr]:border-b-2 [&>tr]:border-slate-700">
                {loading && !items.length ? (
                  <tr><td colSpan={6} className="px-4 py-12 text-center text-slate-500">Loading applications…</td></tr>
                ) : !shown.length ? (
                  <tr><td colSpan={6} className="px-4 py-12 text-center text-slate-500">
                    <Icon name="inbox" className="text-[32px] block mx-auto mb-1 text-slate-600" />
                    {showRemoved ? 'No removed applications.' : 'No applications match.'}
                  </td></tr>
                ) : shown.map(a => (
                  <React.Fragment key={a.phone}>
                    <tr id={`app-${a.phone}`} className={`align-top transition-colors hover:bg-slate-950/60 ${open === a.phone ? 'bg-slate-950/60' : ''}`}>
                      <td className="px-3 py-3">
                        <div className="flex items-start gap-3">
                          <Avatar a={a} tone={a.submitted ? 'bg-amber-950 text-amber-300' : undefined} />
                          <div className="min-w-0">
                            <div className="font-semibold text-slate-100 truncate max-w-[150px]">{a.name || '—'}</div>
                            <div className="font-mono text-xs text-slate-400 whitespace-nowrap">{a.phone}</div>
                            {a.lead_at && <div className="text-[11px] text-slate-500 whitespace-nowrap mt-0.5" title="When the lead came in">
                              <Icon name="schedule" className="text-[13px] align-[-2px] mr-0.5" />{formatDateTime(a.lead_at)}</div>}
                          </div>
                        </div>
                      </td>
                      {simple && (() => {
                        const n = nextStep(a);
                        return (
                          <td className="px-3 py-3 min-w-[176px] max-w-[210px]">
                            <div className={`rounded-lg border px-2.5 py-2 text-[12.5px] leading-snug font-medium ${NEXT_TONE[n.tone]}`}>{n.text}</div>
                            <button onClick={() => setBriefFor(a.phone)}
                              className="mt-2 w-full h-8 rounded-lg bg-violet-600 hover:bg-violet-500 text-white text-[12.5px] font-semibold flex items-center justify-center gap-1">
                              <Icon name="summarize" className="text-[16px]" />Summary & script</button>
                            <div className="grid grid-cols-2 gap-1.5 mt-1.5">
                              <a href={`#inbox/${a.phone.replace(/\D/g, '')}`} className="h-8 rounded-lg bg-sky-600 hover:bg-sky-500 text-white text-[12.5px] font-semibold flex items-center justify-center gap-1"><Icon name="chat" className="text-[16px]" />Chat</a>
                              <button onClick={() => setOpen(open === a.phone ? null : a.phone)} className="h-8 rounded-lg border border-slate-700 bg-slate-900 hover:bg-slate-800 text-slate-200 text-[12.5px] font-semibold flex items-center justify-center gap-1"><Icon name={open === a.phone ? 'expand_less' : 'expand_more'} className="text-[16px]" />{open === a.phone ? 'Hide' : 'Details'}</button>
                              {!readOnly && (showRemoved
                                ? <button onClick={() => restore(a)} className="h-8 rounded-lg border border-emerald-800 text-emerald-300 text-[12.5px] font-semibold flex items-center justify-center gap-1"><Icon name="restore_from_trash" className="text-[16px]" />Restore</button>
                                : <button onClick={() => remove(a)} className="h-8 rounded-lg border border-slate-700 text-slate-400 hover:text-rose-300 text-[12.5px] font-semibold flex items-center justify-center gap-1"><Icon name="delete" className="text-[16px]" />Remove</button>)}
                            </div>
                          </td>
                        );
                      })()}
                      <td className="px-3 py-3">
                        {a.category
                          ? <span className="inline-block px-2 py-0.5 rounded-full bg-purple-950 border border-purple-800/60 text-purple-300 text-[11px] font-semibold whitespace-nowrap">{a.category}</span>
                          : <span className="text-[11px] text-slate-500" title="Not reached through a campaign from Business Data">No category</span>}
                        <div className="text-xs text-slate-300 mt-1 whitespace-nowrap">
                          {a.pincode ? <span className="font-mono">{a.pincode}</span> : <span className="text-slate-500">No PIN</span>}
                          {a.pincode_unchecked && <span className="ml-1 text-[10px] font-semibold text-amber-300" title="Typed in the chat, but the bot could not find it on the map and asked again">unchecked</span>}
                        </div>
                        {place(a) && <div className="text-[11px] text-slate-500 truncate max-w-[180px]" title={place(a)}>{place(a)}</div>}
                        {branch(a) && (
                          <div className="mt-0.5 flex items-center gap-1 text-[11px] text-sky-300 max-w-[170px]" title={`Nearest SBI branch: ${branch(a)}`}>
                            <Icon name="account_balance" className="text-[13px] shrink-0" />
                            <span className="truncate">{branch(a)}</span>
                          </div>
                        )}
                        {a.near_dc && (
                          <div className="mt-1"><NearDc a={a} /></div>
                        )}
                      </td>
                      <td className="px-3 py-3">
                        <div className="mb-1.5"><ProgrammeChip a={a} /></div>
                        <span className={`inline-block px-2 py-0.5 rounded-full border text-[11px] font-semibold whitespace-nowrap ${VERDICT_STYLE[a.verdict]}`}
                          title={a.not_qualified_reasons.join(', ') || undefined}>{simple ? PLAIN_VERDICT[a.verdict] || a.verdict : a.verdict}</span>
                        <div className="text-xs text-slate-400 mt-1 whitespace-nowrap">{a.qualification || 'Education not given'}</div>
                        {a.not_qualified && !(simple && a.not_qualified_reasons.every(r => r.startsWith('Not qualified for SBI'))) && <div className="text-[11px] text-rose-300 mt-0.5">{a.not_qualified_reasons.join(', ')}</div>}
                        {a.esaf && !a.not_qualified && (
                          <div className="text-[11px] text-violet-300 mt-0.5 inline-flex items-center gap-1">
                            <Icon name="account_balance" className="text-[13px]" />For ESAF · can't invest ₹3–5 lakh for SBI
                          </div>
                        )}
                      </td>
                      <td className="px-3 py-3">
                        <div className="text-xs text-slate-200 font-medium">{a.stage}</div>
                        <div className="mt-1.5"><Progress a={a} /></div>
                        <div className="flex items-center gap-2 mt-2" title={a.required_documents_done ? 'Required documents done' : 'Documents uploaded'}>
                          <Icon name="description" className="text-[15px] text-slate-500" />
                          <div className="h-1.5 w-14 rounded-full bg-slate-800 overflow-hidden">
                            <div className={`h-full rounded-full ${a.required_documents_done ? 'bg-emerald-500' : 'bg-sky-500'}`}
                              style={{ width: `${(a.documents_count / Math.max(a.documents_total, 1)) * 100}%` }} />
                          </div>
                          <span className="text-[11px] text-slate-400 tabular-nums">{a.documents_count}/{a.documents_total}</span>
                          {a.required_documents_done && <span className="text-[11px] text-emerald-300">✓</span>}
                        </div>
                        {a.submitted && <div className={`text-[11px] text-amber-300 mt-1 ${simple ? 'max-w-[150px]' : 'whitespace-nowrap'}`}>Submitted {formatDateTime(a.submitted_at)}</div>}
                      </td>
                      <td className="px-3 py-3 text-xs min-w-[130px] max-w-[200px]">
                        {a.comments.length ? (() => {
                          const last = a.comments[a.comments.length - 1];
                          return (
                            <button onClick={() => openComments(a.phone)} className="block w-full text-left rounded-lg bg-slate-950/60 border border-slate-800 px-2.5 py-1.5 hover:border-slate-700" title={last.body}>
                              <span className="block truncate text-slate-200">{last.body}</span>
                              <span className="block text-[10.5px] text-slate-500 mt-0.5">
                                {formatDateTime(last.created_at)} · {last.author}
                                {a.comments.length > 1 && <span className="text-sky-300"> · {a.comments.length} comments</span>}
                              </span>
                            </button>
                          );
                        })() : <span className="text-slate-500">{simple ? 'No comment yet' : 'No comments'}</span>}
                        {!readOnly && !showRemoved && (
                          <button onClick={() => openComments(a.phone)}
                            className="mt-1.5 text-[11.5px] font-semibold text-emerald-300 hover:underline flex items-center gap-0.5">
                            <Icon name="add_comment" className="text-[15px]" /> Add comment
                          </button>
                        )}
                      </td>
                      {!simple && <td className="px-3 py-3">
                        {!simple && (
                        <div className="flex items-center justify-end gap-1.5">
                          <IconButton icon={open === a.phone ? 'expand_less' : 'expand_more'} title={open === a.phone ? 'Hide details' : 'Details'}
                            onClick={() => setOpen(open === a.phone ? null : a.phone)} />
                          <IconButton icon="summarize" title="Summary and call script" onClick={() => setBriefFor(a.phone)} tone="text-violet-300 hover:text-violet-200" />
                          <IconButton icon="chat" title="Open the chat" href={`#inbox/${a.phone.replace(/\D/g, '')}`} />
                          {!readOnly && (showRemoved ? (
                            <IconButton icon="restore_from_trash" title="Restore" onClick={() => restore(a)} tone="text-emerald-300 hover:text-emerald-300" />
                          ) : (
                            <IconButton icon="delete" title="Remove from Applications (the chat and documents are kept)" onClick={() => remove(a)} tone="text-slate-400 hover:text-rose-300" />
                          ))}
                        </div>
                        )}
                      </td>}
                    </tr>
                    {open === a.phone && (
                      <tr><td colSpan={6} className="px-4 pb-5 pt-1 bg-slate-950/60">
                        <ApplicationDetails app={a} readOnly={readOnly} onChanged={load}
                          focusComment={commentFocus === a.phone} onFocused={() => setCommentFocus(null)} />
                      </td></tr>
                    )}
                  </React.Fragment>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      </div>
      {briefFor && <LeadBriefModal phone={briefFor} onClose={() => setBriefFor(null)} />}
    </div>
  );
};

/** Leads: everyone who has submitted their documents, newest first. */
const LeadsBlock: React.FC<{ leads: Application[]; onOpen: (phone: string) => void }> = ({ leads, onOpen }) => (
  <section className="rounded-2xl overflow-hidden shadow-md"
    style={{ background: 'linear-gradient(120deg, #0a3543 0%, #16435a 60%, #1d5a6e 100%)' }}>
    <div className="px-5 py-4 flex flex-wrap items-center justify-between gap-2 text-white">
      <div className="flex items-center gap-2.5">
        <span className="h-9 w-9 rounded-lg flex items-center justify-center" style={{ background: '#f9ab10', color: '#0a3543' }}>
          <Icon name="star" className="text-[20px]" />
        </span>
        <div>
          <h2 className="text-[15px] font-semibold">Leads <span className="ml-1 px-2 py-0.5 rounded-full bg-white/15 text-xs font-bold align-middle">{leads.length}</span></h2>
          <p className="text-xs text-white/65">People who have submitted their documents</p>
        </div>
      </div>
    </div>
    {leads.length === 0 ? (
      <div className="px-5 pb-5 text-sm text-white/70">No one has submitted their documents yet. The Campaign Insights plan lists who to call first.</div>
    ) : (
      <div className="px-4 pb-4 grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
        {leads.map(a => (
          <div key={a.phone} className="p-4 rounded-xl bg-slate-900 border border-slate-800 shadow-sm">
            <div className="flex items-start gap-3">
              <Avatar a={a} tone="bg-amber-950 text-amber-300" />
              <div className="min-w-0 flex-1">
                <div className="font-semibold text-slate-100 truncate">{a.name || a.phone}</div>
                <div className="text-xs font-mono text-slate-400">{a.phone}</div>
              </div>
              <span className={`shrink-0 px-2 py-0.5 rounded-full border text-[10.5px] font-semibold ${VERDICT_STYLE[a.verdict]}`}>{a.verdict}</span>
            </div>
            <div className="mt-3 flex items-center gap-1.5 text-xs text-slate-300">
              <Icon name="location_on" className="text-[15px] text-slate-500" />
              <span className="truncate">{[a.pincode, place(a)].filter(Boolean).join(' · ') || 'No PIN'}</span>
            </div>
            {branch(a) && (
              <div className="mt-1 flex items-center gap-1.5 text-xs text-sky-300">
                <Icon name="account_balance" className="text-[15px]" />
                <span className="truncate">{branch(a)}</span>
              </div>
            )}
            <div className="mt-1.5 flex flex-wrap gap-1.5"><ProgrammeChip a={a} />{a.near_dc && <NearDc a={a} />}</div>
            <div className="mt-1.5 flex flex-wrap gap-1.5 text-[11px]">
              <span className="px-2 py-0.5 rounded-full bg-slate-950 border border-slate-800 text-slate-300">{a.qualification || 'Education —'}</span>
              <span className="px-2 py-0.5 rounded-full bg-slate-950 border border-slate-800 text-slate-300">Docs {a.documents_count}/{a.documents_total}{a.required_documents_done ? ' ✓' : ''}</span>
              <span className="px-2 py-0.5 rounded-full bg-amber-950 text-amber-300">Submitted {formatDateTime(a.submitted_at)}</span>
            </div>
            <div className="mt-3 flex gap-2 text-xs">
              <button onClick={() => onOpen(a.phone)} className="h-8 px-3 rounded-lg border border-slate-800 text-slate-300 hover:bg-slate-950 flex items-center gap-1">
                <Icon name="visibility" className="text-[16px]" />Details</button>
              <a href={`#inbox/${a.phone.replace(/\D/g, '')}`} className="h-8 px-3 rounded-lg border border-slate-800 text-slate-300 hover:bg-slate-950 flex items-center gap-1">
                <Icon name="chat" className="text-[16px]" />Chat</a>
              {a.drive_folder_url && (
                <a href={a.drive_folder_url} target="_blank" rel="noreferrer" className="h-8 px-3 rounded-lg border border-slate-800 text-slate-300 hover:bg-slate-950 flex items-center gap-1">
                  <Icon name="folder_open" className="text-[16px]" />Drive</a>
              )}
            </div>
          </div>
        ))}
      </div>
    )}
  </section>
);

const Field: React.FC<{ icon: string; label: string; value: React.ReactNode }> = ({ icon, label, value }) => (
  <div className="flex gap-2.5 min-w-0">
    <Icon name={icon} className="text-[18px] text-slate-500 mt-0.5" />
    <div className="min-w-0">
      <div className="text-[11px] uppercase tracking-wider text-slate-500">{label}</div>
      <div className="text-sm text-slate-200 mt-0.5 break-words">{value || '—'}</div>
    </div>
  </div>
);

const ApplicationDetails: React.FC<{
  app: Application; readOnly?: boolean; onChanged: () => void; focusComment?: boolean; onFocused?: () => void;
}> = ({ app, readOnly, onChanged, focusComment, onFocused }) => {
  const [draft, setDraft] = useState('');
  const [saving, setSaving] = useState(false);
  const box = React.useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    if (!focusComment) return;
    box.current?.scrollIntoView({ behavior: 'smooth', block: 'center' });
    box.current?.focus();
    onFocused?.();
  }, [focusComment]);

  const add = async () => {
    if (!draft.trim()) return;
    setSaving(true);
    // The box empties and keeps focus, ready for the next comment.
    try { await addApplicationComment(app.phone, draft.trim()); setDraft(''); onChanged(); box.current?.focus(); }
    catch (e: any) { alert(e.message); }
    finally { setSaving(false); }
  };
  const drop = async (id: string) => {
    if (!confirm('Delete this comment?')) return;
    try { await deleteApplicationComment(id); onChanged(); } catch (e: any) { alert(e.message); }
  };

  return (
    <div className="grid gap-4 pt-2 lg:grid-cols-[1.2fr_1fr]">
      <div className="space-y-4 min-w-0">
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 p-4 rounded-xl border border-slate-800 bg-slate-900">
          <Field icon="pin_drop" label="PIN code" value={app.pincode && [app.pincode, app.tehsil, app.district, app.state].filter(Boolean).join(' · ')} />
          <Field icon="account_balance" label="Nearest SBI branch" value={branch(app)} />
          <Field icon="near_me" label="Nearest target PIN" value={app.place && `${app.place}${app.distance_km ? ` · ${app.distance_km} km away` : ''}`} />
          <Field icon="school" label="Qualification" value={app.qualification} />
          <Field icon="payments" label="Can invest ₹5 lakh" value={yesNo(app.can_invest)} />
          <Field icon="campaign" label="Campaign" value={app.source?.campaign} />
          <Field icon="storefront" label="Business" value={app.source && [app.source.business_name, app.source.category, app.source.district].filter(Boolean).join(' · ')} />
          <Field icon="play_circle" label="Started" value={formatDateTime(app.started_at)} />
          <Field icon="forum" label="Last message" value={formatDateTime(app.last_message_at)} />
        </div>
        <div className="flex flex-wrap gap-2 text-sm">
          <a href={`#inbox/${app.phone.replace(/\D/g, '')}`} className="h-9 px-3.5 rounded-lg bg-sky-600 text-white hover:opacity-90 flex items-center gap-1.5">
            <Icon name="chat" className="text-[18px]" />Open chat in Inbox</a>
          {app.drive_folder_url && (
            <a href={app.drive_folder_url} target="_blank" rel="noreferrer" className="h-9 px-3.5 rounded-lg border border-slate-800 bg-slate-900 text-slate-300 hover:bg-slate-800 flex items-center gap-1.5">
              <Icon name="folder_open" className="text-[18px]" />Drive folder</a>
          )}
        </div>
        <div>
          <div className="text-xs font-semibold text-slate-400 mb-2">Documents ({app.documents_count}/{app.documents_total})</div>
          {app.documents.length ? (
            <ul className="grid sm:grid-cols-2 gap-2">
              {app.documents.map(d => (
                <li key={d.document_id}>
                  <a href={d.drive_url || documentUrl(d.document_id)} target="_blank" rel="noreferrer"
                    className="flex items-center gap-2.5 px-3 py-2 rounded-lg bg-slate-900 border border-slate-800 hover:border-sky-500">
                    <Icon name="description" className="text-[20px] text-sky-300" />
                    <span className="min-w-0 flex-1">
                      <span className="block text-sm text-slate-200 truncate">{d.label}</span>
                      {d.name && <span className="block text-[11px] text-slate-500 truncate">{d.name}</span>}
                    </span>
                    <Icon name="open_in_new" className="text-[16px] text-slate-500" />
                  </a>
                </li>
              ))}
            </ul>
          ) : <div className="text-sm text-slate-500">No documents uploaded yet.</div>}
        </div>
      </div>

      <div className="min-w-0">
        <div className="text-xs font-semibold text-slate-400 mb-2">
          Comment history {app.comments.length > 0 && <span className="text-slate-500 font-normal">({app.comments.length}, oldest first)</span>}
        </div>
        <ol className="space-y-2">
          {app.comments.map((c, i) => (
            <li key={c.comment_id} className="flex gap-2.5 px-3 py-2.5 rounded-lg bg-slate-900 border border-slate-800 text-sm">
              <span className="shrink-0 h-6 w-6 rounded-full bg-sky-950 text-sky-300 text-[11px] flex items-center justify-center font-semibold">{i + 1}</span>
              <div className="flex-1 min-w-0">
                <div className="flex justify-between gap-2 text-[11px]">
                  <span><span className="text-slate-300 font-semibold">{c.author}</span>
                    <span className="text-slate-500"> · {formatDateTime(c.created_at)}</span></span>
                  {!readOnly && <button onClick={() => drop(c.comment_id)} className="text-slate-500 hover:text-rose-300" title="Delete comment">
                    <Icon name="delete" className="text-[16px]" /></button>}
                </div>
                <div className="text-slate-200 whitespace-pre-wrap mt-0.5">{c.body}</div>
              </div>
            </li>
          ))}
          {!app.comments.length && <li className="text-sm text-slate-500">No comments yet.</li>}
        </ol>
        {!readOnly && (
          <div className="mt-2.5 rounded-lg border border-slate-800 bg-slate-900 p-2 focus-within:border-sky-500">
            <textarea ref={box} value={draft} onChange={e => setDraft(e.target.value)} rows={2} maxLength={2000}
              onKeyDown={e => { if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) add(); }}
              placeholder={app.comments.length ? 'Add another comment, e.g. what happened on the call (Ctrl+Enter to save)'
                : 'Add a comment for the team (the applicant does not see it)'}
              className="w-full px-1.5 py-1 bg-transparent text-sm text-slate-200 outline-none resize-none" />
            <div className="flex justify-end">
              <button onClick={add} disabled={saving || !draft.trim()}
                className="h-8 px-4 rounded-lg bg-emerald-500 hover:opacity-90 text-white text-sm font-semibold disabled:opacity-40">
                {saving ? 'Saving…' : app.comments.length ? 'Add another' : 'Add comment'}
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

/**
 * One lead on one page (19 Nov 2026, Kavya's Summary button): what happened in the chat,
 * everything they told us, and a warm, polite call script for where they are now.
 */
const LeadBriefModal: React.FC<{ phone: string; onClose: () => void }> = ({ phone, onClose }) => {
  const [b, setB] = useState<LeadBrief | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    let alive = true;
    fetchLeadBrief(phone).then(r => alive && setB(r)).catch(e => alive && setError(e.message));
    const esc = (e: KeyboardEvent) => e.key === 'Escape' && onClose();
    window.addEventListener('keydown', esc);
    return () => { alive = false; window.removeEventListener('keydown', esc); };
  }, [phone, onClose]);
  const digits = phone.replace(/\D/g, '');
  const esaf = b?.programme === 'esaf';
  return (
    <div className="fixed inset-0 z-50 bg-slate-950/80 flex items-start justify-center p-3 sm:p-6 overflow-y-auto" onClick={onClose}>
      <div className="w-full max-w-3xl rounded-2xl overflow-hidden border border-slate-800 bg-slate-900 shadow-2xl" onClick={e => e.stopPropagation()}>
        <div className="px-5 py-4 text-white" style={{ background: esaf ? 'linear-gradient(120deg, #3b0764 0%, #6d28d9 60%, #8b5cf6 100%)'
          : 'linear-gradient(120deg, #0a3543 0%, #16435a 60%, #1d5a6e 100%)' }}>
          <div className="flex items-start gap-3">
            <span className="h-10 w-10 rounded-xl bg-white/15 flex items-center justify-center shrink-0"><Icon name="summarize" className="text-[22px]" /></span>
            <div className="min-w-0 flex-1">
              <div className="text-[17px] font-semibold leading-tight truncate">{b?.name || phone}</div>
              <div className="text-[12px] text-white/75 mt-0.5">{phone}{b ? ` · ${esaf ? 'Interested in ESAF' : 'For SBI'}` : ''}{b?.headline ? ` · ${b.headline}` : ''}</div>
            </div>
            <button onClick={onClose} title="Close" className="h-8 w-8 rounded-full bg-white/15 hover:bg-white/25 flex items-center justify-center"><Icon name="close" className="text-[18px]" /></button>
          </div>
          <div className="mt-3 flex flex-wrap gap-2">
            <a href={`#inbox/${digits}`} onClick={onClose} className="h-8 px-3 rounded-lg bg-white/15 hover:bg-white/25 text-white text-[12.5px] font-semibold flex items-center gap-1"><Icon name="chat" className="text-[16px]" />Open chat</a>
          </div>
        </div>
        {error ? <div className="p-5 text-sm text-rose-300">{error}</div> : !b ? (
          <div className="p-8 text-center text-sm text-slate-500"><Icon name="progress_activity" className="animate-spin text-[22px] block mx-auto mb-1" />Loading…</div>
        ) : (
          <div className="p-5 space-y-5">
            {b.in_short && (
              <div className="rounded-xl border border-sky-800/50 bg-sky-950 p-3.5 text-[13.5px] leading-relaxed text-slate-100">
                <div className="text-[11px] font-semibold uppercase tracking-wider text-sky-300 mb-1">In short</div>{b.in_short}
              </div>
            )}
            <section>
              <h3 className="text-[13px] font-semibold text-slate-100 mb-2 flex items-center gap-1.5"><Icon name="badge" className="text-[17px] text-sky-300" />What we know</h3>
              <div className="grid sm:grid-cols-2 gap-2">
                {b.facts.map(f => (
                  <div key={f.label} className="rounded-lg border border-slate-800 bg-slate-950/60 px-3 py-2">
                    <div className="text-[10.5px] uppercase tracking-wider text-slate-500">{f.label}</div>
                    <div className="text-[13px] text-slate-200 mt-0.5">{f.value}</div>
                  </div>
                ))}
              </div>
            </section>
            {b.story.length > 0 && (
              <section>
                <h3 className="text-[13px] font-semibold text-slate-100 mb-2 flex items-center gap-1.5"><Icon name="forum" className="text-[17px] text-sky-300" />What happened in the chat</h3>
                <ol className="space-y-1.5 border-l-2 border-slate-800 pl-3">
                  {b.story.map((line, i) => <li key={i} className="text-[13px] text-slate-300 leading-snug">{line}</li>)}
                </ol>
              </section>
            )}
            {b.their_questions.length > 0 && (
              <section className="rounded-xl border border-amber-800/50 bg-amber-950 p-3.5">
                <h3 className="text-[13px] font-semibold text-amber-300 mb-1.5 flex items-center gap-1.5"><Icon name="help" className="text-[17px]" />Their questions to answer</h3>
                <ul className="space-y-1">{b.their_questions.map(q => <li key={q} className="text-[13px] text-slate-100">“{q}”</li>)}</ul>
              </section>
            )}
            <section>
              <h3 className="text-[13px] font-semibold text-slate-100 mb-2 flex items-center gap-1.5"><Icon name="record_voice_over" className="text-[17px] text-emerald-300" />Call script</h3>
              <div className="space-y-2.5">
                {b.script.map((part, i) => (
                  <div key={part.title} className="rounded-xl border border-slate-800 bg-slate-950/60 p-3.5">
                    <div className="flex items-center gap-2 text-[13px] font-semibold text-slate-100">
                      <span className="h-6 w-6 rounded-full bg-emerald-500/15 text-emerald-300 flex items-center justify-center text-[11px] font-bold">{i + 1}</span>
                      <Icon name={part.icon} className="text-[17px] text-emerald-300" />{part.title}
                    </div>
                    <ul className="mt-2 space-y-1.5 pl-1">
                      {part.lines.map((line, j) => <li key={j} className="text-[13px] leading-relaxed text-slate-200 flex gap-2"><span className="text-emerald-400 mt-0.5">•</span><span>{line}</span></li>)}
                    </ul>
                  </div>
                ))}
              </div>
            </section>
            <section className="rounded-xl border border-rose-800/50 bg-rose-950 p-3.5">
              <h3 className="text-[13px] font-semibold text-rose-300 mb-1.5 flex items-center gap-1.5"><Icon name="do_not_disturb_on" className="text-[17px]" />Please avoid</h3>
              <ul className="space-y-1">{b.avoid.map(t => <li key={t} className="text-[12.5px] text-slate-200">{t}</li>)}</ul>
            </section>
            {b.comments.length > 0 && (
              <section>
                <h3 className="text-[13px] font-semibold text-slate-100 mb-2 flex items-center gap-1.5"><Icon name="comment" className="text-[17px] text-sky-300" />Comments</h3>
                <ul className="space-y-1.5">{b.comments.map(c => (
                  <li key={c.comment_id} className="rounded-lg border border-slate-800 bg-slate-950/60 px-3 py-2 text-[13px] text-slate-200">
                    {c.body}<div className="text-[11px] text-slate-500 mt-0.5">{formatDateTime(c.created_at)} · {c.author}</div>
                  </li>))}
                </ul>
              </section>
            )}
          </div>
        )}
      </div>
    </div>
  );
};
