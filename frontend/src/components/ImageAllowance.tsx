import React, { useEffect, useState } from 'react';
import { fetchImageAllowance } from '../api/whatsapp';
import type { ImageAllowance as Allowance } from '../api/whatsapp';

/** A time as it reads in India, with the day when it is not today. */
const ist = (iso: string) => {
  const d = new Date(iso);
  const opts: Intl.DateTimeFormatOptions = { timeZone: 'Asia/Kolkata', hour: '2-digit', minute: '2-digit' };
  const day = (x: Date) => x.toLocaleDateString('en-IN', { timeZone: 'Asia/Kolkata' });
  const time = d.toLocaleTimeString('en-IN', opts);
  return day(d) === day(new Date())
    ? `${time} IST`
    : `${time} IST on ${d.toLocaleDateString('en-IN', { timeZone: 'Asia/Kolkata', day: 'numeric', month: 'short' })}`;
};

/**
 * How many free images can still be made today. Hugging Face does not report
 * its allowance, so the server counts the images it has made in the 24 hours
 * since the first one, and switches to the time Hugging Face gave whenever it
 * refuses for want of allowance.
 */
export const ImageAllowance: React.FC<{ refreshKey?: unknown }> = ({ refreshKey }) => {
  const [a, setA] = useState<Allowance | null>(null);
  useEffect(() => {
    const load = () => fetchImageAllowance().then(setA).catch(() => {});
    load();
    const t = setInterval(load, 60000);
    return () => clearInterval(t);
  }, [refreshKey]);
  if (!a) return null;

  if (a.reached) {
    return (
      <div className="flex items-start gap-2 rounded-lg border border-amber-700/60 bg-amber-900/20 px-4 py-3 text-sm text-amber-200">
        <span className="material-symbols-outlined text-[20px]">hourglass_top</span>
        <div>
          <b>You have reached today's image generation limit.</b>
          {a.resets_at && <> The limit will reset after 24 hours at <b>{ist(a.resets_at)}</b>.</>}
          <div className="text-xs text-amber-300/80 mt-0.5">
            Drafts made meanwhile keep their text and get their photo automatically once it resets.
          </div>
        </div>
      </div>
    );
  }
  return (
    <div className="flex items-start gap-2 rounded-lg border border-emerald-800/60 bg-emerald-900/20 px-4 py-3 text-sm text-emerald-200">
      <span className="material-symbols-outlined text-[20px]">image</span>
      <div>
        <b>{a.used === 0
          ? `You can generate ${a.remaining} image${a.remaining === 1 ? '' : 's'} today.`
          : `You can generate ${a.remaining} more image${a.remaining === 1 ? '' : 's'} today.`}</b>
        <span className="text-xs text-emerald-300/80"> {a.used} of {a.limit} used. Each draft uses 1–{a.images_per_draft} images.</span>
      </div>
    </div>
  );
};
