import React, { useState } from 'react';
import { BackToParent } from '../components/SubPage';
import type { NavTab } from '../components/Header';
import { DispositionsPanel } from '../components/DispositionsPanel';
import { ActionQueue } from '../components/ActionQueue';
import { FollowUpsPanel } from '../components/FollowUpsPanel';
import { NudgeTemplatesPanel } from '../components/NudgeTemplatesPanel';

/**
 * Every chat's outcome (disposition) on a tab of its own, for those who work
 * the chats without the Dashboard: how many stand where, who is handling
 * which chat now, and what the team recorded lately; then what each
 * disposition set in motion (nudges standing in for calls, tasks for the
 * team and the District Coordinator), and the nudges' templates to review.
 */
export const DispositionsView: React.FC<{ readOnly?: boolean; can?: (t: NavTab) => boolean }> = ({ readOnly, can }) => {
  const [days, setDays] = useState(7);
  return (
    <div className="flex-1 overflow-y-auto bg-slate-950 text-slate-100">
      <div className="px-4 sm:px-6 pt-6 pb-2 max-w-[1300px] mx-auto flex flex-wrap items-end justify-between gap-4">
        <div>
          <BackToParent tab="dispositions" can={can} />
          <h1 className="text-2xl font-semibold tracking-tight text-slate-100">Dispositions</h1>
          <p className="text-sm text-slate-500 mt-1">How every chat stands: recorded by the team, or read from the bot's step where nobody has yet.</p>
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
      <div className="px-4 sm:px-6 py-4 max-w-[1300px] mx-auto">
        <DispositionsPanel days={days} />
        <div className="mt-5 space-y-5">
          <ActionQueue />
          <FollowUpsPanel days={days} />
          <NudgeTemplatesPanel readOnly={readOnly} />
        </div>
      </div>
    </div>
  );
};
