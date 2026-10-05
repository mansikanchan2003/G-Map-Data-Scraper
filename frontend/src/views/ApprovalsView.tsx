import React, { useCallback, useEffect, useState } from 'react';
import { approveUser, fetchUsers, rejectUser, revokeUser, type AuthUser, type GrantRole } from '../api';

/**
 * The approvals queue.
 *
 * Pending requests come first and stay at the top, because they are the only
 * rows that need a decision — everything below is history, kept so an
 * approval can be traced back to whoever made it.
 */

const statusStyle = (status: string) => {
  switch (status) {
    case 'APPROVED': return 'text-emerald-400 border-emerald-800 bg-emerald-950/50';
    case 'PENDING': return 'text-amber-400 border-amber-800 bg-amber-950/50';
    case 'REJECTED': return 'text-rose-400 border-rose-800 bg-rose-950/50';
    case 'DISABLED': return 'text-slate-300 border-slate-600 bg-slate-800';
    default: return 'text-slate-400 border-slate-700 bg-slate-800/50';
  }
};

const when = (iso: string | null) =>
  iso ? new Date(iso).toLocaleString(undefined, { day: '2-digit', month: 'short', year: 'numeric',
                                                  hour: '2-digit', minute: '2-digit' }) : '—';

export const ApprovalsView: React.FC = () => {
  const [users, setUsers] = useState<AuthUser[]>([]);
  const [loading, setLoading] = useState(true);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setUsers(await fetchUsers());
      setError(null);
    } catch (e: any) {
      setError(e?.message || 'Could not load the approvals queue.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  // The role each pending request will be approved with; member unless changed.
  const [roles, setRoles] = useState<Record<string, GrantRole>>({});
  const roleFor = (u: AuthUser) => roles[u.user_id] || (u.role === 'manager' || u.role === 'operator' ? u.role : 'member');

  const changeRole = async (user: AuthUser, role: GrantRole) => {
    setBusyId(user.user_id);
    try {
      await approveUser(user.user_id, role);
      await load();
    } catch (e: any) {
      setError(e?.message || 'Could not change the role.');
    } finally {
      setBusyId(null);
    }
  };

  const revoke = async (user: AuthUser) => {
    if (!window.confirm(`Remove ${user.email}'s access? They are signed out at once. You can restore it later.`)) return;
    setBusyId(user.user_id);
    try {
      await revokeUser(user.user_id);
      await load();
    } catch (e: any) {
      setError(e?.message || 'Could not remove access.');
    } finally {
      setBusyId(null);
    }
  };

  const decide = async (user: AuthUser, approve: boolean) => {
    if (!approve) {
      const reason = window.prompt(`Decline ${user.email}? You can give a reason (optional):`, '');
      if (reason === null) return;
      setBusyId(user.user_id);
      try {
        await rejectUser(user.user_id, reason || undefined);
        await load();
      } catch (e: any) {
        setError(e?.message || 'Could not decline this request.');
      } finally {
        setBusyId(null);
      }
      return;
    }

    setBusyId(user.user_id);
    try {
      await approveUser(user.user_id, roleFor(user));
      await load();
    } catch (e: any) {
      setError(e?.message || 'Could not approve this request.');
    } finally {
      setBusyId(null);
    }
  };

  // Pending first; the rest newest-first underneath.
  const ordered = [...users].sort((a, b) => {
    if (a.status === 'PENDING' && b.status !== 'PENDING') return -1;
    if (b.status === 'PENDING' && a.status !== 'PENDING') return 1;
    return new Date(b.created_at).getTime() - new Date(a.created_at).getTime();
  });
  const pendingCount = users.filter(u => u.status === 'PENDING').length;

  return (
    <div className="flex-1 flex flex-col min-w-0 h-full bg-slate-950 text-slate-100 p-4 sm:p-6 overflow-y-auto">
      <div className="flex flex-wrap items-start justify-between gap-3 mb-5">
        <div className="min-w-0">
          <h1 className="text-xl sm:text-2xl font-semibold tracking-tight">Access Requests</h1>
          <p className="text-xs text-slate-400 mt-0.5">
            Only @eko.co.in addresses can request access, and only you can grant it
          </p>
        </div>
        <div className="flex items-center gap-2">
          {pendingCount > 0 && (
            <span className="text-[11px] font-mono-code font-bold uppercase px-2 py-1 rounded border
                             text-amber-400 border-amber-800 bg-amber-950/50">
              {pendingCount} waiting
            </span>
          )}
          <button
            onClick={load}
            className="h-8 px-3 bg-slate-800 hover:bg-slate-700 border border-slate-700 text-slate-200
                       text-xs rounded flex items-center gap-1.5 transition-colors cursor-pointer"
          >
            <span className={`material-symbols-outlined text-[15px] ${loading ? 'animate-spin' : ''}`}>
              refresh
            </span>
            Refresh
          </button>
        </div>
      </div>

      {error && (
        <div className="bg-rose-950/30 border border-rose-900 rounded p-3 text-rose-300 text-xs mb-4">
          {error}
        </div>
      )}

      <div className="bg-slate-900 border border-slate-800 rounded-lg overflow-hidden shrink-0">
        <div className="overflow-x-auto">
          <table className="w-full text-left border-collapse text-sm">
            <thead className="bg-slate-950 border-b border-slate-800 sticky top-0 z-10">
              <tr>
                <th className="px-3 py-2.5 text-xs font-semibold text-slate-400">Person</th>
                <th className="px-3 py-2.5 text-xs font-semibold text-slate-400">Status</th>
                <th className="px-3 py-2.5 text-xs font-semibold text-slate-400 hidden sm:table-cell">Requested</th>
                <th className="px-3 py-2.5 text-xs font-semibold text-slate-400 hidden lg:table-cell">Decided by</th>
                <th className="px-3 py-2.5 text-xs font-semibold text-slate-400 text-right">Action</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800">
              {loading ? (
                <tr><td colSpan={5} className="px-4 py-10 text-center text-slate-500">Loading…</td></tr>
              ) : ordered.length === 0 ? (
                <tr><td colSpan={5} className="px-4 py-10 text-center text-slate-500">
                  No requests yet.
                </td></tr>
              ) : (
                ordered.map(u => (
                  <tr key={u.user_id} className="hover:bg-slate-800/40 transition-colors">
                    <td className="px-3 py-2.5 max-w-[220px]">
                      <span className="block font-medium text-slate-200 truncate">
                        {u.full_name || u.email.split('@')[0]}
                      </span>
                      <span className="block text-[11px] font-mono-code text-slate-500 truncate"
                            title={u.email}>
                        {u.email}
                      </span>
                    </td>
                    <td className="px-3 py-2.5">
                      <span className={`text-[10px] px-1.5 py-0.5 rounded uppercase font-semibold border
                                        ${statusStyle(u.status)}`}>
                        {u.status}
                      </span>
                      {u.role === 'admin' && (
                        <span className="ml-1 text-[10px] px-1.5 py-0.5 rounded uppercase font-semibold
                                         border text-sky-400 border-sky-800 bg-sky-950/50">
                          admin
                        </span>
                      )}
                      {u.role === 'operator' && u.status === 'APPROVED' && (
                        <span className="ml-1 text-[10px] px-1.5 py-0.5 rounded uppercase font-semibold
                                         border text-amber-300 border-amber-800 bg-amber-950/50">
                          operator
                        </span>
                      )}
                      {u.role === 'manager' && u.status === 'APPROVED' && (
                        <span className="ml-1 text-[10px] px-1.5 py-0.5 rounded uppercase font-semibold
                                         border text-violet-300 border-violet-800 bg-violet-950/50">
                          manager
                        </span>
                      )}
                    </td>
                    <td className="px-3 py-2.5 text-xs text-slate-400 whitespace-nowrap hidden sm:table-cell">
                      {when(u.created_at)}
                    </td>
                    <td className="px-3 py-2.5 text-xs text-slate-400 hidden lg:table-cell">
                      {u.decided_by ? (
                        <span className="block truncate max-w-[180px]" title={u.decided_by}>
                          {u.decided_by}
                          <span className="block text-[10px] text-slate-600">{when(u.decided_at)}</span>
                        </span>
                      ) : '—'}
                    </td>
                    <td className="px-3 py-2.5">
                      <div className="flex items-center justify-end gap-1.5">
                        {(u.status === 'PENDING' || u.status === 'APPROVED') && u.role !== 'admin' && (
                          <select
                            value={roleFor(u)}
                            disabled={busyId === u.user_id}
                            title={u.status === 'PENDING'
                              ? `Asked for ${u.role}. Approve as:` : 'Change role'}
                            onChange={e => {
                              const role = e.target.value as GrantRole;
                              if (u.status === 'PENDING') setRoles(r => ({ ...r, [u.user_id]: role }));
                              else changeRole(u, role);
                            }}
                            className="h-7 px-1.5 rounded text-[11px] border border-slate-700 bg-slate-900
                                       text-slate-200 cursor-pointer disabled:opacity-40"
                          >
                            <option value="member">Member</option>
                            <option value="manager">Manager</option>
                            <option value="operator">Operator (view only)</option>
                          </select>
                        )}
                        {u.status === 'PENDING' ? (
                          <>
                            <button
                              onClick={() => decide(u, true)}
                              disabled={busyId === u.user_id}
                              className="h-7 px-2.5 rounded text-[11px] font-semibold border
                                         border-emerald-800 bg-emerald-950 text-emerald-300
                                         hover:bg-emerald-900 transition-colors cursor-pointer
                                         disabled:opacity-40"
                            >
                              Approve
                            </button>
                            <button
                              onClick={() => decide(u, false)}
                              disabled={busyId === u.user_id}
                              className="h-7 px-2.5 rounded text-[11px] font-semibold border
                                         border-rose-800 bg-rose-950 text-rose-300
                                         hover:bg-rose-900 transition-colors cursor-pointer
                                         disabled:opacity-40"
                            >
                              Decline
                            </button>
                          </>
                        ) : u.status === 'REJECTED' ? (
                          <button
                            onClick={() => decide(u, true)}
                            disabled={busyId === u.user_id}
                            className="h-7 px-2.5 rounded text-[11px] font-semibold border
                                       border-slate-700 bg-slate-800 text-slate-300
                                       hover:border-emerald-700 hover:text-emerald-300
                                       transition-colors cursor-pointer disabled:opacity-40"
                          >
                            Allow after all
                          </button>
                        ) : u.status === 'DISABLED' ? (
                          <button
                            onClick={() => decide(u, true)}
                            disabled={busyId === u.user_id}
                            className="h-7 px-2.5 rounded text-[11px] font-semibold border
                                       border-slate-700 bg-slate-800 text-slate-300
                                       hover:border-emerald-700 hover:text-emerald-300
                                       transition-colors cursor-pointer disabled:opacity-40"
                          >
                            Restore access
                          </button>
                        ) : u.role !== 'admin' ? (
                          <button
                            onClick={() => revoke(u)}
                            disabled={busyId === u.user_id}
                            className="h-7 px-2.5 rounded text-[11px] font-semibold border
                                       border-rose-900 bg-slate-900 text-rose-300
                                       hover:bg-rose-950 transition-colors cursor-pointer
                                       disabled:opacity-40"
                          >
                            Remove access
                          </button>
                        ) : (
                          <span className="text-[11px] text-slate-600">—</span>
                        )}
                      </div>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};
