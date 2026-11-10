import React, { useEffect, useRef, useState } from 'react';
import { fetchGoogleConfig } from '../api';

/**
 * Google's own "Sign in with Google" button (Google Identity Services).
 * Google proves the person owns the @eko.co.in address; the server still
 * decides who gets in. Shows nothing when the server has no Google client set.
 */

declare global {
  interface Window { google?: any }
}

const GSI_SRC = 'https://accounts.google.com/gsi/client';
let gsiLoading: Promise<void> | null = null;

function loadGsi(): Promise<void> {
  if (window.google?.accounts?.id) return Promise.resolve();
  if (!gsiLoading) {
    gsiLoading = new Promise((resolve, reject) => {
      const s = document.createElement('script');
      s.src = GSI_SRC;
      s.async = true;
      s.defer = true;
      s.onload = () => resolve();
      s.onerror = () => { gsiLoading = null; reject(new Error('Google sign-in could not load.')); };
      document.head.appendChild(s);
    });
  }
  return gsiLoading;
}

interface Props {
  /** 'signin' or 'signup' changes only the button's words. */
  mode: 'signin' | 'signup';
  onCredential: (credential: string) => void;
  /** Called once we know whether the server offers Google at all. */
  onAvailable?: (available: boolean) => void;
}

export const GoogleButton: React.FC<Props> = ({ mode, onCredential, onAvailable }) => {
  const box = useRef<HTMLDivElement>(null);
  const [clientId, setClientId] = useState<string | null>(null);
  const [failed, setFailed] = useState<string | null>(null);
  // The latest handler, so the button Google rendered once never calls a stale one.
  const handler = useRef(onCredential);
  handler.current = onCredential;

  useEffect(() => {
    let alive = true;
    fetchGoogleConfig()
      .then(c => { if (alive) { setClientId(c.enabled ? c.client_id : null); onAvailable?.(c.enabled); } })
      .catch(() => { if (alive) onAvailable?.(false); });
    return () => { alive = false; };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!clientId || !box.current) return;
    let alive = true;
    loadGsi().then(() => {
      if (!alive || !box.current) return;
      window.google.accounts.id.initialize({
        client_id: clientId,
        callback: (r: { credential: string }) => handler.current(r.credential),
        hd: 'eko.co.in',
        ux_mode: 'popup',
        context: mode === 'signup' ? 'signup' : 'signin',
      });
      box.current.innerHTML = '';
      window.google.accounts.id.renderButton(box.current, {
        theme: 'filled_blue', size: 'large', shape: 'pill', logo_alignment: 'left',
        text: mode === 'signup' ? 'signup_with' : 'signin_with',
        width: Math.min(box.current.clientWidth || 320, 400),
      });
    }).catch(e => alive && setFailed(e.message));
    return () => { alive = false; };
  }, [clientId, mode]);

  if (!clientId) return null;
  return (
    <div>
      <div ref={box} className="flex justify-center min-h-[44px] w-full" />
      {failed && <p className="text-[11px] text-amber-400 mt-1 text-center">{failed}</p>}
    </div>
  );
};
