import React, { useState } from 'react';
import { forgotPassword, resetPassword } from '../api';

// A forgotten password is reset with a code emailed to the administrator,
// who passes it on if the request is genuine. Two steps — ask for the code,
// then enter it, once the administrator has given it, with the new password.

const field =
  'w-full bg-slate-950 border border-slate-700 rounded px-3 py-2.5 text-sm text-slate-100 ' +
  'placeholder:text-slate-600 focus:border-sky-500 focus:outline-none focus:ring-1 ' +
  'focus:ring-sky-500 transition-colors';

interface Props {
  initialEmail?: string;
  onDone: (message: string) => void;
  onCancel: () => void;
}

export const ForgotPasswordForm: React.FC<Props> = ({ initialEmail = '', onDone, onCancel }) => {
  const [step, setStep] = useState<'email' | 'code'>('email');
  const [email, setEmail] = useState(initialEmail);
  const [code, setCode] = useState('');
  const [next, setNext] = useState('');
  const [again, setAgain] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const mismatch = again.length > 0 && next !== again;

  const sendCode = async (e?: React.FormEvent) => {
    e?.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const res = await forgotPassword(email.trim());
      setNotice(res.message);
      setStep('code');
    } catch (err: any) {
      setError(err?.message || 'Could not send the code.');
    } finally {
      setBusy(false);
    }
  };

  const reset = async (e: React.FormEvent) => {
    e.preventDefault();
    if (next !== again) {
      setError('The two new passwords do not match.');
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const res = await resetPassword(email.trim(), code.trim(), next);
      onDone(res.message);
    } catch (err: any) {
      setError(err?.message || 'Could not change the password.');
    } finally {
      setBusy(false);
    }
  };

  const messages = (
    <>
      {notice && (
        <p className="text-xs text-emerald-400 flex items-start gap-1.5">
          <span className="material-symbols-outlined text-[15px] mt-px shrink-0">mark_email_read</span>
          {notice}
        </p>
      )}
      {error && (
        <p className="text-xs text-rose-400 flex items-start gap-1.5">
          <span className="material-symbols-outlined text-[15px] mt-px shrink-0">error</span>
          {error}
        </p>
      )}
    </>
  );

  if (step === 'email') {
    return (
      <form onSubmit={sendCode} className="flex flex-col gap-3">
        <p className="text-xs text-slate-400 leading-relaxed">
          Enter your work email. A 6-digit code is sent to the administrator, who will
          give it to you; then you set a new password here.
        </p>
        <div>
          <label className="block text-xs text-slate-400 font-semibold mb-1">Work email</label>
          <input className={field} type="email" required value={email} autoFocus
                 onChange={e => setEmail(e.target.value)} autoComplete="email" />
        </div>
        {messages}
        <div className="flex gap-2 mt-1">
          <button type="submit" disabled={busy}
                  className="flex-1 h-10 rounded bg-sky-600 hover:bg-sky-500 text-white text-sm font-semibold
                             transition-colors disabled:opacity-50 cursor-pointer">
            {busy ? 'Sending…' : 'Request a code'}
          </button>
          <button type="button" onClick={onCancel}
                  className="h-10 px-4 rounded border border-slate-700 bg-slate-800 text-slate-200 text-sm
                             hover:bg-slate-700 transition-colors cursor-pointer">
            Back
          </button>
        </div>
      </form>
    );
  }

  return (
    <form onSubmit={reset} className="flex flex-col gap-3">
      {messages}
      <div>
        <label className="block text-xs text-slate-400 font-semibold mb-1">Code from the administrator</label>
        <input className={`${field} tracking-[0.4em] font-mono-code`} required value={code} autoFocus
               inputMode="numeric" maxLength={6} placeholder="000000" autoComplete="one-time-code"
               onChange={e => setCode(e.target.value.replace(/\D/g, ''))} />
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
      <div className="flex gap-2 mt-1">
        <button type="submit" disabled={busy || mismatch || code.length !== 6}
                className="flex-1 h-10 rounded bg-sky-600 hover:bg-sky-500 text-white text-sm font-semibold
                           transition-colors disabled:opacity-50 cursor-pointer">
          {busy ? 'Please wait…' : 'Set new password'}
        </button>
        <button type="button" onClick={onCancel}
                className="h-10 px-4 rounded border border-slate-700 bg-slate-800 text-slate-200 text-sm
                           hover:bg-slate-700 transition-colors cursor-pointer">
          Cancel
        </button>
      </div>
      <button type="button" onClick={() => sendCode()} disabled={busy}
              className="text-xs text-sky-400 hover:text-sky-300 self-center cursor-pointer disabled:opacity-50">
        Send a new code
      </button>
    </form>
  );
};
