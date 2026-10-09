import React, { useEffect, useState } from 'react';
import { fetchImagePromptRecord, studioMediaUrl } from '../api/whatsapp';
import type { ImagePromptRecord } from '../api/whatsapp';
import { CollapsiblePanel } from './CollapsiblePanel';
import { formatDateTime } from '../utils/datetime';

const OUTCOME: Record<string, { label: string; cls: string }> = {
  kept: { label: 'Kept — draft approved', cls: 'bg-emerald-900/40 text-emerald-300' },
  in_review: { label: 'In review', cls: 'bg-sky-900/40 text-sky-300' },
  replaced: { label: 'Replaced by reviewer', cls: 'bg-amber-900/40 text-amber-300' },
  draft_rejected: { label: 'Draft rejected', cls: 'bg-slate-800 text-slate-400' },
  unused: { label: 'Not used', cls: 'bg-slate-800 text-slate-400' },
};

/**
 * Which image prompts have worked. The agent reads the same record before it
 * writes the next photo scene, and the style marked "used next" is the one the
 * next photo of that kind will be asked for in.
 */
export const PhotoPromptRecord: React.FC = () => {
  const [data, setData] = useState<ImagePromptRecord | null>(null);
  useEffect(() => { fetchImagePromptRecord().then(setData).catch(() => {}); }, []);
  if (!data) return null;

  const judged = data.recent.length;
  return (
    <CollapsiblePanel icon="photo_library" iconClass="text-sky-400" title="Photo prompts: what has worked"
      badge={<span className="text-xs text-slate-500">{judged ? `${judged} recent` : 'none yet'}</span>}>
      <div className="space-y-4 text-xs">
        <p className="text-slate-400">
          Every photo is checked as it is made, then kept by approving its draft or replaced with New photo.
          The agent is shown this record before writing the next photo, and the style with the best record is used.
          {data.sign_paused && <span className="text-amber-300"> Signs are paused: they keep coming out misspelt,
            so photos go straight to the typeset poster, with a sign tried again every few photos.</span>}
        </p>

        <div className="overflow-x-auto">
          <table className="w-full">
            <thead className="text-slate-500 text-left">
              <tr>{['Photo', 'Style', 'Tries', 'Worked', 'Gibberish', 'Score', ''].map(h =>
                <th key={h} className="px-2 py-1.5 font-semibold">{h}</th>)}</tr>
            </thead>
            <tbody>
              {data.styles.map(s => (
                <tr key={`${s.kind}-${s.style}`} className="border-t border-slate-800 text-slate-300">
                  <td className="px-2 py-1.5">{s.kind === 'sign' ? 'With sign' : 'Plain'}</td>
                  <td className="px-2 py-1.5">{s.style}</td>
                  <td className="px-2 py-1.5">{s.tries}</td>
                  <td className="px-2 py-1.5">{s.worked}</td>
                  <td className="px-2 py-1.5">{s.gibberish}</td>
                  <td className="px-2 py-1.5">{s.score.toFixed(2)}</td>
                  <td className="px-2 py-1.5">{s.chosen_next && <span className="text-emerald-300">used next</span>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div className="grid gap-3 md:grid-cols-2">
          {data.recent.map(r => {
            const img = r.media_id ? studioMediaUrl(JSON.stringify({ media_id: r.media_id })) : null;
            const out = OUTCOME[r.outcome] || { label: r.outcome, cls: 'bg-slate-800 text-slate-400' };
            return (
              <div key={r.prompt_id} className="flex gap-3 p-2 rounded border border-slate-800 bg-slate-950">
                {img && (
                  <a href={img} target="_blank" rel="noopener noreferrer" className="shrink-0">
                    <img src={img} alt="" className="w-24 h-24 object-cover rounded bg-slate-900" />
                  </a>
                )}
                <div className="min-w-0 space-y-1">
                  <div className="flex flex-wrap gap-1.5">
                    <span className={`px-1.5 py-0.5 rounded ${out.cls}`}>{out.label}</span>
                    <span className="px-1.5 py-0.5 rounded bg-slate-800 text-slate-300">
                      {r.kind === 'sign' ? `sign “${r.phrase}”` : 'plain'} · {r.style}
                    </span>
                    {r.gibberish && <span className="px-1.5 py-0.5 rounded bg-rose-900/40 text-rose-300">gibberish</span>}
                  </div>
                  {r.note && <div className="text-amber-300">{r.note}</div>}
                  {r.scene && <div className="text-slate-300 line-clamp-2" title={r.scene}>{r.scene}</div>}
                  <details>
                    <summary className="cursor-pointer text-slate-500 hover:text-slate-300">
                      Prompt · {formatDateTime(r.created_at)}{r.seed != null ? ` · seed ${r.seed}` : ''}
                    </summary>
                    <div className="mt-1 text-slate-400 whitespace-pre-wrap break-words">{r.prompt}</div>
                  </details>
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </CollapsiblePanel>
  );
};
