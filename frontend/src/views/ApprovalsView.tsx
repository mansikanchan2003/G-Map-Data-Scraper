import React, { useCallback, useEffect, useState } from 'react';
import { approveUser, createUser, fetchUsers, rejectUser, revokeUser, setInboxScope, setUserTabs, type AuthUser, type GrantRole } from '../api';

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

// The tabs an admin can give an account, in the sidebar's order.
const TABS: [string, string][] = [
  ['dashboard', 'Dashboard'], ['businesses', 'Business Data'], ['dc-data', 'DC & CSPs near DC'], ['partners', 'Partner Organisations'],
  ['jobs', 'Jobs Monitor'], ['config', 'Configuration'], ['whatsapp-inbox', 'Inbox'], ['applications', 'Applications'],
  ['dispositions', 'Dispositions'], ['whatsapp-campaign', 'WhatsApp Campaign'], ['whatsapp-templates', 'Templates'],
  ['whatsapp-studio', 'Template Studio'], ['whatsapp-history', 'Campaign History'], ['whatsapp-insights', 'Campaign Insights'],
];
const SCOPES: [string, string][] = [['', 'All chats'], ['not_autogmap', 'Only chats not from AutoGMap'], ['autogmap', 'Only AutoGMap chats']];
const tabLabel = (key: string) => TABS.find(([k]) => k === key)?.[1] || key;

const ROLE_INFO: [GrantRole, string, string][] = [
  ['member', 'Member', 'Sees the data, changes nothing'],
  ['operator', 'Operator', 'Works on everything: campaigns, Inbox, Applications'],
  ['manager', 'Manager', 'Everything an operator does, and approves large campaigns'],
];

/** A new account, let in at once (23 Nov 2026). The person is emailed that they have access; never the password. */
const CreateUserForm: React.FC<{ onCreated: (u: AuthUser) => void; onClose: () => void }> = ({ onCreated, onClose }) => {
  const [email, setEmail] = useState('');
  const [name, setName] = useState('');
  const [role, setRole] = useState<GrantRole>('member');
  const [withPassword, setWithPassword] = useState(false);
  const [password, setPassword] = useState('');
  const [show, setShow] = useState(false);
  const [tabs, setTabs] = useState<string[]>([]);
  const [scope, setScope] = useState('');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const toggle = (k: string) => setTabs(t => t.includes(k) ? t.filter(x => x !== k) : [...t, k]);
  const typed = email.trim();
  const fullEmail = typed.includes('@') ? typed : typed ? `${typed}@eko.co.in` : '';
  const field = 'h-9 w-full px-3 rounded-lg border border-slate-700 bg-slate-950 text-sm text-slate-100 outline-none focus:border-sky-500';

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true); setError(null);
    try {
      const u = await createUser({
        email: fullEmail, full_name: name.trim() || undefined, role,
        password: withPassword && password ? password : undefined,
        tabs: tabs.length ? TABS.map(([k]) => k).filter(k => tabs.includes(k)) : null,
        inbox_scope: (scope || null) as 'autogmap' | 'not_autogmap' | null,
      });
      onCreated(u);
    } catch (err: any) { setError(err?.message || 'Could not create the account.'); }
    finally { setSaving(false); }
  };

  return (
    <form onSubmit={submit} className="mb-5 shrink-0 rounded-2xl border border-slate-800 bg-slate-900 overflow-hidden shadow-sm">
      <div className="relative px-5 py-4 text-white" style={{ background: 'linear-gradient(120deg, #0a3543 0%, #16435a 55%, #1d5a6e 100%)' }}>
        <span className="material-symbols-outlined absolute -right-4 -bottom-8 text-[120px] text-white/10 pointer-events-none select-none">person_add</span>
        <div className="relative flex items-center gap-3">
          <span className="material-symbols-outlined text-[28px]">person_add</span>
          <div>
            <div className="text-lg font-semibold">Create a user</div>
            <div className="text-[12px] text-white/75">They can sign in at once. They are emailed that they have access; never a password.</div>
          </div>
        </div>
      </div>
      <div className="p-5 grid gap-4 md:grid-cols-2">
        <label className="block">
          <span className="text-[11px] font-semibold text-slate-400">Work email</span>
          <input autoFocus required value={email} onChange={e => setEmail(e.target.value)} placeholder="name or name@eko.co.in" className={`${field} mt-1`} />
          {fullEmail && !typed.includes('@') && <span className="text-[11px] text-slate-500">{fullEmail}</span>}
        </label>
        <label className="block">
          <span className="text-[11px] font-semibold text-slate-400">Full name <span className="font-normal text-slate-500">(optional)</span></span>
          <input value={name} onChange={e => setName(e.target.value)} placeholder="As the team knows them" className={`${field} mt-1`} />
        </label>

        <div className="md:col-span-2">
          <span className="text-[11px] font-semibold text-slate-400">Role</span>
          <div className="mt-1 grid gap-2 sm:grid-cols-3">
            {ROLE_INFO.map(([k, label, note]) => (
              <button type="button" key={k} onClick={() => setRole(k)}
                className={`text-left rounded-lg border px-3 py-2 cursor-pointer transition-colors ${role === k
                  ? 'border-sky-600 bg-sky-950 text-sky-100' : 'border-slate-700 text-slate-300 hover:border-slate-600'}`}>
                <div className="text-sm font-semibold flex items-center gap-1.5">
                  <span className="material-symbols-outlined text-[16px]">{role === k ? 'radio_button_checked' : 'radio_button_unchecked'}</span>{label}
                </div>
                <div className="text-[11px] text-slate-500 mt-0.5">{note}</div>
              </button>
            ))}
          </div>
        </div>

        <div className="md:col-span-2 rounded-lg border border-slate-800 bg-slate-950/60 p-3">
          <label className="flex items-center gap-2 text-sm text-slate-200 cursor-pointer">
            <input type="checkbox" checked={withPassword} onChange={e => setWithPassword(e.target.checked)} className="accent-sky-500" />
            Give a starting password
          </label>
          {withPassword ? (
            <div className="mt-2 flex flex-wrap items-center gap-2">
              <input type={show ? 'text' : 'password'} value={password} onChange={e => setPassword(e.target.value)}
                autoComplete="new-password" placeholder="At least 8 characters" className={`${field} max-w-sm`} />
              <button type="button" onClick={() => setShow(v => !v)} className="text-[12px] text-sky-300 hover:underline cursor-pointer">{show ? 'Hide' : 'Show'}</button>
              <span className="text-[11px] text-slate-500">Tell it to them yourself; they change it after signing in.</span>
            </div>
          ) : (
            <div className="mt-1 text-[11.5px] text-slate-500">
              Without one they sign in with Google, or set a password with a code from Forgot password on the sign-in page.
            </div>
          )}
        </div>

        <div className="md:col-span-2">
          <span className="text-[11px] font-semibold text-slate-400">Tabs <span className="font-normal text-slate-500">(none ticked: every tab the role allows)</span></span>
          <div className="mt-1 flex flex-wrap gap-1.5">
            {TABS.map(([k, label]) => (
              <label key={k} className={`inline-flex items-center gap-1.5 px-2 py-1 rounded border text-[11.5px] cursor-pointer ${tabs.includes(k)
                ? 'border-sky-700 bg-sky-950 text-sky-200' : 'border-slate-700 text-slate-400 hover:border-slate-600'}`}>
                <input type="checkbox" checked={tabs.includes(k)} onChange={() => toggle(k)} className="accent-sky-500" />{label}
              </label>
            ))}
          </div>
        </div>
        <label className="flex flex-wrap items-center gap-2 md:col-span-2">
          <span className="text-[11px] font-semibold text-slate-400">Inbox shows</span>
          <select value={scope} onChange={e => setScope(e.target.value)}
            className="h-8 px-2 rounded text-[12px] border border-slate-700 bg-slate-950 text-slate-200 cursor-pointer">
            {SCOPES.map(([k, label]) => <option key={k} value={k}>{label}</option>)}
          </select>
        </label>
      </div>
      <div className="px-5 pb-5 flex flex-wrap items-center justify-end gap-2">
        {error && <span className="mr-auto text-[12px] text-rose-300">{error}</span>}
        <button type="button" onClick={onClose} className="h-9 px-4 rounded-lg text-sm text-slate-400 hover:text-slate-200 cursor-pointer">Cancel</button>
        <button type="submit" disabled={saving || !fullEmail}
          className="h-9 px-4 rounded-lg bg-emerald-500 text-white text-sm font-semibold inline-flex items-center gap-1.5 disabled:opacity-50 cursor-pointer">
          <span className="material-symbols-outlined text-[18px]">person_add</span>{saving ? 'Creating...' : 'Create user'}
        </button>
      </div>
    </form>
  );
};

/** What an account may see: its tabs and which chats its Inbox shows. Saved on the server, which enforces it. */
const AccessEditor: React.FC<{ user: AuthUser; onSaved: () => void; onClose: () => void }> = ({ user, onSaved, onClose }) => {
  const [tabs, setTabs] = useState<string[]>(user.allowed_tabs || []);
  const [scope, setScope] = useState<string>(user.inbox_scope || '');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const toggle = (k: string) => setTabs(t => t.includes(k) ? t.filter(x => x !== k) : [...t, k]);
  const save = async () => {
    setSaving(true); setError(null);
    try {
      // Kept in the sidebar's order, so the first is where the account lands.
      await setUserTabs(user.user_id, tabs.length ? TABS.map(([k]) => k).filter(k => tabs.includes(k)) : null);
      await setInboxScope(user.user_id, (scope || null) as 'autogmap' | 'not_autogmap' | null);
      onSaved(); onClose();
    } catch (e: any) { setError(e?.message || 'Could not save.'); }
    finally { setSaving(false); }
  };
  return (
    <div className="p-3 bg-slate-950 border-t border-slate-800 space-y-3">
      <div>
        <div className="text-[11px] font-semibold text-slate-400 mb-1.5">
          Tabs {user.email} sees <span className="font-normal text-slate-500">(none ticked: every tab the role allows)</span>
        </div>
        <div className="flex flex-wrap gap-1.5">
          {TABS.map(([k, label]) => (
            <label key={k} className={`inline-flex items-center gap-1.5 px-2 py-1 rounded border text-[11.5px] cursor-pointer ${tabs.includes(k)
              ? 'border-sky-700 bg-sky-950 text-sky-200' : 'border-slate-700 text-slate-400 hover:border-slate-600'}`}>
              <input type="checkbox" checked={tabs.includes(k)} onChange={() => toggle(k)} className="accent-sky-500" />{label}
            </label>
          ))}
        </div>
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-[11px] font-semibold text-slate-400">Inbox shows</span>
        <select value={scope} onChange={e => setScope(e.target.value)}
          className="h-7 px-1.5 rounded text-[11.5px] border border-slate-700 bg-slate-900 text-slate-200 cursor-pointer">
          {SCOPES.map(([k, label]) => <option key={k} value={k}>{label}</option>)}
        </select>
        <span className="text-[11px] text-slate-500">
          An account limited to some chats can reply and work only in the Inbox; it can change nothing else.
        </span>
      </div>
      {error && <div className="text-[11.5px] text-rose-300">{error}</div>}
      <div className="flex justify-end gap-2">
        <button onClick={onClose} className="h-7 px-3 rounded text-[11.5px] text-slate-400 hover:text-slate-200 cursor-pointer">Cancel</button>
        <button onClick={save} disabled={saving}
          className="h-7 px-3 rounded text-[11.5px] font-semibold border border-emerald-800 bg-emerald-950 text-emerald-300 hover:bg-emerald-900 cursor-pointer disabled:opacity-40">
          {saving ? 'Saving…' : 'Save access'}
        </button>
      </div>
    </div>
  );
};

export const ApprovalsView: React.FC = () => {
  const [editing, setEditing] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [created, setCreated] = useState<AuthUser | null>(null);
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
          <button onClick={() => { setCreating(c => !c); setCreated(null); }}
            className="h-8 px-3 bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-semibold rounded flex items-center gap-1.5 cursor-pointer">
            <span className="material-symbols-outlined text-[16px]">person_add</span>Create user
          </button>
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

      {creating && (
        <CreateUserForm onClose={() => setCreating(false)}
          onCreated={u => { setCreating(false); setCreated(u); load(); }} />
      )}
      {created && (
        <div className="mb-4 shrink-0 rounded-lg border border-emerald-800/60 bg-emerald-950 px-4 py-3 text-[13px] text-emerald-200 flex items-center gap-2">
          <span className="material-symbols-outlined text-[18px]">check_circle</span>
          <span><b>{created.email}</b> can sign in now, as {created.role}. They have been emailed.</span>
          <button onClick={() => setCreated(null)} className="ml-auto text-emerald-300 hover:text-white cursor-pointer">
            <span className="material-symbols-outlined text-[16px]">close</span>
          </button>
        </div>
      )}

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
                  <React.Fragment key={u.user_id}>
                  <tr className="hover:bg-slate-800/40 transition-colors">
                    <td className="px-3 py-2.5 max-w-[220px]">
                      <span className="block font-medium text-slate-200 truncate">
                        {u.full_name || u.email.split('@')[0]}
                      </span>
                      <span className="block text-[11px] font-mono-code text-slate-500 truncate"
                            title={u.email}>
                        {u.email}
                      </span>
                      {u.status === 'APPROVED' && u.role !== 'admin' && (
                        <button onClick={() => setEditing(editing === u.user_id ? null : u.user_id)}
                          title="Which tabs and chats this account sees"
                          className="mt-1 text-left text-[10.5px] text-sky-400 hover:text-sky-300 cursor-pointer">
                          {u.allowed_tabs?.length ? u.allowed_tabs.map(tabLabel).join(', ') : 'All tabs'}
                          {u.inbox_scope ? ` · Inbox: ${u.inbox_scope === 'not_autogmap' ? 'not AutoGMap' : 'AutoGMap only'}` : ''}
                          {' · '}<span className="underline">Edit access</span>
                        </button>
                      )}
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
                                         border text-emerald-300 border-emerald-800 bg-emerald-950/50">
                          operator
                        </span>
                      )}
                      {u.role === 'member' && u.status === 'APPROVED' && (
                        <span className="ml-1 text-[10px] px-1.5 py-0.5 rounded uppercase font-semibold
                                         border text-amber-300 border-amber-800 bg-amber-950/50">
                          member · view only
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
                            <option value="member">Member (view only)</option>
                            <option value="manager">Manager</option>
                            <option value="operator">Operator</option>
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
                  {editing === u.user_id && (
                    <tr><td colSpan={5} className="p-0">
                      <AccessEditor user={u} onSaved={load} onClose={() => setEditing(null)} />
                    </td></tr>
                  )}
                  </React.Fragment>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};
