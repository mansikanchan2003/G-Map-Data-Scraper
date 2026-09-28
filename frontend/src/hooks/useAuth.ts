import { useCallback, useEffect, useState } from 'react';
import {
  fetchMe, login as apiLogin, logout as apiLogout, signup as apiSignup,
  type AuthUser,
} from '../api';

/**
 * Who is signed in, if anyone.
 *
 * The session lives in an httpOnly cookie the page cannot read, so the answer
 * comes from the server rather than from local state. `loading` matters: until
 * that first check returns, "no user" and "not asked yet" look identical, and
 * rendering the login page during the gap would flash it at someone who is
 * already signed in.
 */
export function useAuth() {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    const me = await fetchMe();
    setUser(me);
    setLoading(false);
    return me;
  }, []);

  useEffect(() => { refresh(); }, [refresh]);

  const login = useCallback(async (email: string, password: string) => {
    const me = await apiLogin(email, password);
    setUser(me);
    return me;
  }, []);

  const logout = useCallback(async () => {
    try {
      await apiLogout();
    } finally {
      // Cleared either way: if the call failed the cookie may still be gone,
      // and leaving the UI signed in would be the worse mistake.
      setUser(null);
    }
  }, []);

  return { user, loading, login, logout, signup: apiSignup, refresh };
}
