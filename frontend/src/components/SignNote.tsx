import React from 'react';
import type { StudioDraft } from '../api/whatsapp';

/**
 * How a Studio draft's image was made: the photo's own sign, read back and
 * matching the phrase, or the phrase set by the renderer because the sign was
 * misspelt or could not be read. Says which, since the reviewer decides.
 */
export const SignNote: React.FC<{ generation: StudioDraft['generation'] }> = ({ generation: g }) => {
  if (!g?.image_mode || !g.image_phrase) return null;
  if (g.image_mode === 'photo_text') {
    return <div className="text-xs text-emerald-300">Image: the sign in the photo reads “{g.image_phrase}”, checked letter by letter.</div>;
  }
  if (g.sign_skipped) {
    return <div className="text-xs text-slate-400">Image: “{g.image_phrase}” is set in type. No sign was tried: signs have kept coming out misspelt, so the free image went to the photo.</div>;
  }
  const tried = (g.text_photo_attempts || []).filter(a => !a.error);
  const last = tried[tried.length - 1];
  const why = !last ? 'no photo with the sign could be made'
    : last.checked === false ? 'the sign in the photo could not be checked'
    : `the photo's sign read “${last.read || '—'}”`;
  return <div className="text-xs text-slate-400">Image: “{g.image_phrase}” is set in type, because {why}.</div>;
};
