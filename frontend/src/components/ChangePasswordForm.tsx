import React, { useState } from 'react';
import { changePassword } from '../api';

// Changing a password asks for the current one: that is the proof that the
// person typing is the account's owner, signed in or not. A forgotten password
// cannot be changed here; the administrator has to be asked.

const field =
  'w-full bg-slate-950 border border-slate-700 rounded px-3 py-2.5 text-sm text-slate-100 ' +
  'placeholder:text-slate-600 focus:border-sky-500 focus:outline-none focus:ring-1 ' +
  'focus:ring-sky-500 transition-colors';

interface Props {
  /** Fixed when the person is signed in; typed on the sign-in page. */
  email?: string;
  onDone: (message: string) => void;
  onCancel?: () => void;
}

export const ChangePasswordForm: React.FC<Props> = ({ email: fixedEmail, onDone, onCancel }) => {
  const [email, setEmail] = useState(fixedEmail || '');
  const [current, setCurrent] = useState('');
  const [next, setNext] = useState('');
  const [again, setAgain] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const mismatch = again.length > 0 && next !== again;

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (next !== again) {
      setError('The two new passwords do not match.');
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const res = await changePassword(email.trim(), current, next);
      onDone(res.message);
    } catch (err: any) {
      setError(err?.message || 'Could not change the password.');
    } finally {
      setBusy(false);
    }
  };

  return (
    <form onSubmit={submit} className="flex flex-col gap-3">
      {!fixedEmail && (
        <div>
          <label className="block text-xs text-slate-400 font-semibold mb-1">Work email</label>
          <input className={field} type="email" required value={email}
                 onChange={e => setEmail(e.target.value)} autoComplete="email" />
        </div>
      )}
      <div>
        <label className="block text-xs text-slate-400 font-semibold mb-1">Current password</label>
        <input className={field} type="password" required value={current}
               onChange={e => setCurrent(e.target.value)} autoComplete="current-password" />
      </div>
      <div>
        <label className="block text-xs text-slate-400 font-semibold mb-1">New password</label>
        <input className={field} type="password" required value={next}
               onChange={e => setNext(e.target.value)} autoComplete="new-password"
               placeholder="At least 10 characters" />
        <p className="text-[11px] text-slate-500 mt-1">
          At least 10 characters, mixing letters with numbers or symbols.
        </p>
      </div>
      <div>
        <label className="block text-xs text-slate-400 font-semibold mb-1">New password again</label>
        <input className={field} type="password" required value={again}
               onChange={e => setAgain(e.target.value)} autoComplete="new-password" />
        {mismatch && <p className="text-[11px] text-amber-400 mt-1">These do not match yet.</p>}
      </div>

      {error && (
        <p className="text-xs text-rose-400 flex items-start gap-1.5">
          <span className="material-symbols-outlined text-[15px] mt-px shrink-0">error</span>
          {error}
        </p>
      )}

      <div className="flex gap-2 mt-1">
        <button type="submit" disabled={busy || mismatch}
                className="flex-1 h-10 rounded bg-sky-600 hover:bg-sky-500 text-white text-sm font-semibold
                           transition-colors disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer">
          {busy ? 'Please wait…' : 'Change password'}
        </button>
        {onCancel && (
          <button type="button" onClick={onCancel}
                  className="h-10 px-4 rounded border border-slate-700 bg-slate-800 text-slate-200 text-sm
                             hover:bg-slate-700 transition-colors cursor-pointer">
            Cancel
          </button>
        )}
      </div>
      <p className="text-[11px] text-slate-500 leading-relaxed">
        Changing it signs you out everywhere, so you sign in again with the new password.
        If you have forgotten the current one, ask the administrator.
      </p>
    </form>
  );
};
