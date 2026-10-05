import React, { useState } from 'react';
import type { AuthUser } from '../api';

/**
 * The way in, and the way to ask to be let in.
 *
 * Signing up and signing in share one screen because they are the same
 * decision from the visitor's side. What the form makes unmissable is that
 * they are not the same outcome: a request is recorded, and access starts
 * only once an administrator approves it.
 */

interface Props {
  onLogin: (email: string, password: string) => Promise<AuthUser>;
  onSignup: (email: string, password: string, fullName?: string,
             role?: 'member' | 'manager' | 'operator') => Promise<{ message: string }>;
}

const ALLOWED_DOMAIN = 'eko.co.in';

const field =
  'w-full bg-slate-950 border border-slate-700 rounded px-3 py-2.5 text-sm text-slate-100 ' +
  'placeholder:text-slate-600 focus:border-sky-500 focus:outline-none focus:ring-1 ' +
  'focus:ring-sky-500 transition-colors';

export const LoginView: React.FC<Props> = ({ onLogin, onSignup }) => {
  const [mode, setMode] = useState<'login' | 'signup'>('login');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [fullName, setFullName] = useState('');
  const [role, setRole] = useState<'member' | 'manager' | 'operator'>('member');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const domainLooksWrong =
    mode === 'signup' && email.includes('@') && !email.trim().toLowerCase().endsWith('@' + ALLOWED_DOMAIN);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      if (mode === 'login') {
        await onLogin(email.trim(), password);
      } else {
        const res = await onSignup(email.trim(), password, fullName.trim() || undefined, role);
        setNotice(res.message);
        setPassword('');
        setMode('login');
      }
    } catch (err: any) {
      setError(err?.message || 'Something went wrong. Try again.');
    } finally {
      setBusy(false);
    }
  };

  const switchTo = (next: 'login' | 'signup') => {
    setMode(next);
    setError(null);
    setNotice(null);
  };

  return (
    <div className="min-h-screen w-full bg-slate-950 text-slate-100 flex flex-col
                    items-center justify-center px-4 py-10">
      <div className="w-full max-w-sm">
        <div className="flex items-center gap-3 mb-8">
          <img src={`${import.meta.env.BASE_URL}eko-wordmark.svg`} alt="Eko" className="h-8 w-auto" />
          <div className="min-w-0">
            <h1 className="text-lg font-semibold tracking-tight truncate">AutoGMap</h1>
            <p className="text-xs text-slate-500">Discovery &amp; outreach console</p>
          </div>
        </div>

        <div className="bg-slate-900 border border-slate-800 rounded-lg p-5 sm:p-6 shadow-sm">
          <div className="flex gap-1 p-1 bg-slate-950 border border-slate-800 rounded mb-5">
            {(['login', 'signup'] as const).map(m => (
              <button
                key={m}
                type="button"
                onClick={() => switchTo(m)}
                className={`flex-1 py-1.5 text-xs font-semibold rounded transition-colors cursor-pointer ${
                  mode === m ? 'bg-slate-800 text-slate-100' : 'text-slate-500 hover:text-slate-300'
                }`}
              >
                {m === 'login' ? 'Sign in' : 'Request access'}
              </button>
            ))}
          </div>

          <form onSubmit={submit} className="flex flex-col gap-3">
            {mode === 'signup' && (
              <div>
                <label className="block text-xs text-slate-400 font-semibold mb-1">Your name</label>
                <input className={field} value={fullName} onChange={e => setFullName(e.target.value)}
                       placeholder="Mansi Kanchan" autoComplete="name" />
              </div>
            )}

            {mode === 'signup' && (
              <div>
                <label className="block text-xs text-slate-400 font-semibold mb-1">Access you need</label>
                <select className={field} value={role} onChange={e => setRole(e.target.value as typeof role)}>
                  <option value="member">Member — use every tab</option>
                  <option value="manager">Manager — use every tab, shown as manager</option>
                  <option value="operator">Operator — view only: dashboard, data, templates, campaigns</option>
                </select>
                <p className="mt-1 text-[11px] text-slate-500">
                  This is a request. The administrator decides the role when approving.
                </p>
              </div>
            )}

            <div>
              <label className="block text-xs text-slate-400 font-semibold mb-1">Work email</label>
              <input
                className={field}
                type="email"
                required
                value={email}
                onChange={e => setEmail(e.target.value)}
                placeholder={`you@${ALLOWED_DOMAIN}`}
                autoComplete="email"
              />
              {domainLooksWrong && (
                <p className="text-[11px] text-amber-400 mt-1">
                  Only @{ALLOWED_DOMAIN} addresses can request access.
                </p>
              )}
            </div>

            <div>
              <label className="block text-xs text-slate-400 font-semibold mb-1">Password</label>
              <input
                className={field}
                type="password"
                required
                value={password}
                onChange={e => setPassword(e.target.value)}
                placeholder={mode === 'signup' ? 'At least 10 characters' : '••••••••'}
                autoComplete={mode === 'signup' ? 'new-password' : 'current-password'}
              />
              {mode === 'signup' && (
                <p className="text-[11px] text-slate-500 mt-1">
                  At least 10 characters, mixing letters with numbers or symbols.
                </p>
              )}
            </div>

            {error && (
              <p className="text-xs text-rose-400 flex items-start gap-1.5">
                <span className="material-symbols-outlined text-[15px] mt-px shrink-0">error</span>
                {error}
              </p>
            )}
            {notice && (
              <p className="text-xs text-emerald-400 flex items-start gap-1.5">
                <span className="material-symbols-outlined text-[15px] mt-px shrink-0">check_circle</span>
                {notice}
              </p>
            )}

            <button
              type="submit"
              disabled={busy}
              className="mt-1 h-10 rounded bg-sky-600 hover:bg-sky-500 text-white text-sm font-semibold
                         transition-colors disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer"
            >
              {busy ? 'Please wait…' : mode === 'login' ? 'Sign in' : 'Send request'}
            </button>
          </form>

          {mode === 'signup' && (
            <p className="text-[11px] text-slate-500 mt-4 leading-relaxed border-t border-slate-800 pt-4">
              Requesting access does not create an account you can use. An administrator
              reviews every request, and you will be able to sign in once yours is approved.
            </p>
          )}
        </div>
      </div>
    </div>
  );
};
