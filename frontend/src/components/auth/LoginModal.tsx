import React, { useEffect, useState } from 'react';
import {
  ShieldCheck,
  X,
  Check,
  UserPlus,
  Trash2,
  LogOut,
  KeyRound,
  Cpu,
  Users,
} from 'lucide-react';
import { useModelStore } from '../../store/useModelStore';
import { api } from '../../services/api';
import type { UserDirectoryItem, UserRole } from '../../types/metamodel';

const ROLE_BADGE_MAP: Record<UserRole, string> = {
  Admin: 'bg-rose-500/20 text-rose-300 border-rose-500/40',
  'Data Architect': 'bg-blue-500/20 text-blue-300 border-blue-500/40',
  'Data Steward': 'bg-amber-500/20 text-amber-300 border-amber-500/40',
  Viewer: 'bg-slate-700 text-slate-300 border-slate-600',
};

const ROLE_DESCRIPTIONS: Record<UserRole, string> = {
  Admin:
    'Full access to user directory management, role assignment, physical model structure, and agent execution.',
  'Data Architect':
    'Full CRUD on tables, views, columns, Crow’s Foot relationships, domains, physical storage, and DDL/dbt generation.',
  'Data Steward':
    'Governance-scoped: Can edit business metadata (logical_name, description, pii_classification, glossary); blocked from altering physical types or PK/FKs.',
  Viewer:
    'Read-only canvas exploration, natural-language model Q&A, and DDL/dbt export inspection.',
};

export const LoginModal: React.FC = () => {
  const isAuthenticated = useModelStore((s) => s.isAuthenticated);
  const isLoginModalOpen = useModelStore((s) => s.isLoginModalOpen);
  const currentUser = useModelStore((s) => s.currentUser);
  const authToken = useModelStore((s) => s.authToken);
  const setLoginModalOpen = useModelStore((s) => s.setLoginModalOpen);
  const loginAsUser = useModelStore((s) => s.loginAsUser);
  const logout = useModelStore((s) => s.logout);
  const setStatusBanner = useModelStore((s) => s.setStatusBanner);

  // Login Form State (defaults to Admin for first login!)
  const [loginEmail, setLoginEmail] = useState('admin@metaforge.local');
  const [loginPassword, setLoginPassword] = useState('password123');
  const [loginError, setLoginError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  // User Directory State
  const [users, setUsers] = useState<UserDirectoryItem[]>([]);

  // Admin Create New User Form State
  const [newFullName, setNewFullName] = useState('');
  const [newEmail, setNewEmail] = useState('');
  const [newPassword, setNewPassword] = useState('password123');
  const [newRole, setNewRole] = useState<UserRole>('Data Architect');

  const fetchUsers = async () => {
    try {
      const list = await api.listUsers(authToken);
      setUsers(list);
    } catch {
      // ignore if backend still starting
    }
  };

  useEffect(() => {
    if (!isAuthenticated || isLoginModalOpen) {
      fetchUsers();
    }
  }, [isAuthenticated, isLoginModalOpen, authToken]);

  const handleLoginSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoginError(null);
    setIsSubmitting(true);
    const ok = await loginAsUser(loginEmail, loginPassword);
    setIsSubmitting(false);
    if (!ok) {
      setLoginError(
        'Invalid credentials. Default password is password123 (First login: admin@metaforge.local).'
      );
    }
  };

  const handleCreateUser = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newEmail.trim() || !newFullName.trim()) return;
    try {
      const created = await api.createUser(
        {
          email: newEmail.trim(),
          full_name: newFullName.trim(),
          password: newPassword || 'password123',
          role: newRole,
        },
        authToken
      );
      setNewFullName('');
      setNewEmail('');
      setNewPassword('password123');
      await fetchUsers();
      setStatusBanner({
        type: 'success',
        message: `Admin created user '${created.email}' with role [${created.role}]`,
      });
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to create user';
      setStatusBanner({ type: 'error', message: msg });
    }
  };

  const handleRoleUpdate = async (userId: number, role: UserRole) => {
    try {
      const updated = await api.updateUser(userId, { role }, authToken);
      await fetchUsers();
      setStatusBanner({
        type: 'success',
        message: `Updated ${updated.email} role to [${updated.role}]`,
      });
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to update role';
      setStatusBanner({ type: 'error', message: msg });
    }
  };

  const handleDeleteUser = async (userId: number) => {
    try {
      const res = await api.deleteUser(userId, authToken);
      await fetchUsers();
      setStatusBanner({
        type: 'info',
        message: `Deleted user ${res.email}`,
      });
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to delete user';
      setStatusBanner({ type: 'error', message: msg });
    }
  };

  // ---------------------------------------------------------------------------
  // MODE 1: Mandatory Full-Screen Login Gate (First Login by Admin)
  // ---------------------------------------------------------------------------
  if (!isAuthenticated) {
    return (
      <div className="fixed inset-0 z-50 bg-slate-950 flex items-center justify-center p-4 overflow-y-auto">
        <div className="bg-slate-900 border border-slate-800 rounded-2xl w-full max-w-4xl grid grid-cols-1 md:grid-cols-12 shadow-2xl overflow-hidden">
          {/* Left Panel: Sign In Form */}
          <div className="md:col-span-6 p-8 flex flex-col justify-between space-y-6 border-b md:border-b-0 md:border-r border-slate-800">
            <div className="space-y-3">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-blue-600 to-indigo-600 flex items-center justify-center shadow-lg shadow-blue-500/30">
                  <Cpu className="w-5 h-5 text-white" />
                </div>
                <div>
                  <h1 className="text-lg font-bold text-white tracking-tight">
                    MetaForge Studio
                  </h1>
                  <p className="text-xs text-slate-400">
                    Enterprise Data Modeling, Canonical Governance &amp; Autonomous dbt
                  </p>
                </div>
              </div>

              <div className="p-3 rounded-xl bg-rose-500/10 border border-rose-500/30 text-xs text-rose-200 leading-relaxed">
                <span className="font-bold text-rose-300 block mb-0.5">
                  Bootstrap Admin First Login
                </span>
                Sign in initially as <code>admin@metaforge.local</code> to provision team members and assign RBAC roles (<code>Admin</code>, <code>Data Architect</code>, <code>Data Steward</code>, <code>Viewer</code>).
              </div>
            </div>

            <form onSubmit={handleLoginSubmit} className="space-y-4">
              <div>
                <label className="text-xs font-semibold text-slate-300 block mb-1.5">
                  Enterprise Email
                </label>
                <input
                  type="email"
                  required
                  value={loginEmail}
                  onChange={(e) => setLoginEmail(e.target.value)}
                  placeholder="admin@metaforge.local"
                  className="w-full bg-slate-950 text-sm font-mono text-white px-3.5 py-2.5 rounded-xl border border-slate-700 focus:border-blue-500 outline-none"
                />
              </div>

              <div>
                <label className="text-xs font-semibold text-slate-300 block mb-1.5">
                  Password
                </label>
                <input
                  type="password"
                  required
                  value={loginPassword}
                  onChange={(e) => setLoginPassword(e.target.value)}
                  placeholder="••••••••"
                  className="w-full bg-slate-950 text-sm font-mono text-white px-3.5 py-2.5 rounded-xl border border-slate-700 focus:border-blue-500 outline-none"
                />
              </div>

              {loginError && (
                <div className="p-2.5 rounded-lg bg-rose-950/80 border border-rose-500/50 text-xs text-rose-200">
                  {loginError}
                </div>
              )}

              <button
                type="submit"
                disabled={isSubmitting}
                className="w-full py-2.5 rounded-xl bg-blue-600 hover:bg-blue-500 text-white font-bold text-sm shadow-lg shadow-blue-600/25 flex items-center justify-center gap-2 transition-all"
              >
                <KeyRound className="w-4 h-4" />
                <span>
                  {isSubmitting
                    ? 'Authenticating...'
                    : 'Sign In to MetaForge Studio'}
                </span>
              </button>
            </form>

            <div className="text-[11px] text-slate-500">
              Default password for seeded accounts: <code className="text-slate-300">password123</code>
            </div>
          </div>

          {/* Right Panel: Quick Account Selector */}
          <div className="md:col-span-6 p-8 bg-slate-950/60 flex flex-col justify-between space-y-4">
            <div>
              <h2 className="text-xs font-bold uppercase tracking-wider text-slate-400 mb-3 flex items-center gap-2">
                <Users className="w-4 h-4 text-blue-400" />
                Active Enterprise Directory ({users.length || 4} Accounts)
              </h2>
              <p className="text-xs text-slate-400 mb-4">
                Click any account below to pre-fill credentials (start with <strong>Admin</strong> to create or manage users):
              </p>

              <div className="space-y-2.5 max-h-[340px] overflow-y-auto pr-1">
                {(users.length > 0
                  ? users
                  : [
                      {
                        id: 1,
                        email: 'admin@metaforge.local',
                        full_name: 'Elena Vance (Enterprise Admin)',
                        role: 'Admin' as UserRole,
                        is_active: true,
                      },
                      {
                        id: 2,
                        email: 'architect@metaforge.local',
                        full_name: 'Marcus Sterling (Principal Data Architect)',
                        role: 'Data Architect' as UserRole,
                        is_active: true,
                      },
                      {
                        id: 3,
                        email: 'steward@metaforge.local',
                        full_name: 'Priya Nair (Lead Data Governance Steward)',
                        role: 'Data Steward' as UserRole,
                        is_active: true,
                      },
                      {
                        id: 4,
                        email: 'viewer@metaforge.local',
                        full_name: 'Alex Chen (Analytics Consumer / Viewer)',
                        role: 'Viewer' as UserRole,
                        is_active: true,
                      },
                    ]
                ).map((acct) => {
                  const selected = loginEmail.toLowerCase() === acct.email.toLowerCase();
                  return (
                    <button
                      key={acct.id}
                      type="button"
                      onClick={() => {
                        setLoginEmail(acct.email);
                        setLoginPassword('password123');
                      }}
                      className={`w-full text-left p-3 rounded-xl border transition-all ${
                        selected
                          ? 'bg-blue-600/15 border-blue-500 ring-1 ring-blue-500/40'
                          : 'bg-slate-900 hover:bg-slate-800 border-slate-800'
                      }`}
                    >
                      <div className="flex items-center justify-between gap-2">
                        <span className="text-xs font-bold text-white">
                          {acct.full_name}
                        </span>
                        <span
                          className={`px-2 py-0.5 rounded text-[10px] font-bold border ${
                            ROLE_BADGE_MAP[acct.role] || ROLE_BADGE_MAP.Viewer
                          }`}
                        >
                          {acct.role}
                        </span>
                      </div>
                      <div className="text-[11px] font-mono text-sky-400 mt-0.5">
                        {acct.email}
                      </div>
                      <p className="text-[11px] text-slate-400 mt-1 leading-snug">
                        {ROLE_DESCRIPTIONS[acct.role]}
                      </p>
                    </button>
                  );
                })}
              </div>
            </div>
          </div>
        </div>
      </div>
    );
  }

  // ---------------------------------------------------------------------------
  // MODE 2: In-App Admin User Management & Role Switcher Modal
  // ---------------------------------------------------------------------------
  if (!isLoginModalOpen) return null;

  const isAdmin = currentUser.role === 'Admin';

  return (
    <div className="fixed inset-0 z-50 bg-black/75 backdrop-blur-sm flex items-center justify-center p-4">
      <div className="bg-slate-900 border border-slate-700 rounded-2xl w-full max-w-4xl max-h-[88vh] flex flex-col shadow-2xl overflow-hidden">
        {/* Header */}
        <div className="px-6 py-4 bg-slate-950 border-b border-slate-800 flex items-center justify-between">
          <div>
            <h2 className="text-base font-bold text-white flex items-center gap-2">
              <ShieldCheck className="w-4 h-4 text-blue-400" />
              Enterprise User Directory, Admin Provisioning &amp; RBAC Switcher
            </h2>
            <p className="text-xs text-slate-400">
              Signed in as <strong>{currentUser.full_name}</strong> (<code>{currentUser.email}</code> —{' '}
              <span className="text-sky-400 font-semibold">{currentUser.role}</span>)
            </p>
          </div>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={logout}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-rose-500/15 hover:bg-rose-500/25 text-rose-300 border border-rose-500/30 text-xs font-semibold"
            >
              <LogOut className="w-3.5 h-3.5" />
              <span>Sign Out</span>
            </button>
            <button
              type="button"
              onClick={() => setLoginModalOpen(false)}
              className="text-slate-400 hover:text-white p-1"
            >
              <X className="w-5 h-5" />
            </button>
          </div>
        </div>

        {/* Body */}
        <div className="p-6 overflow-y-auto grid grid-cols-1 lg:grid-cols-12 gap-6">
          {/* Left: Active Users & Role Assignment */}
          <div className="lg:col-span-7 space-y-3">
            <h3 className="text-xs font-bold uppercase tracking-wider text-slate-400">
              Registered Users ({users.length}) — Click &ldquo;Switch Session&rdquo; to Test Role
            </h3>

            <div className="space-y-2.5">
              {users.map((u) => {
                const isCurrent =
                  u.email.toLowerCase() === currentUser.email.toLowerCase();
                return (
                  <div
                    key={u.id}
                    className={`p-3.5 rounded-xl border flex flex-col gap-2 ${
                      isCurrent
                        ? 'bg-blue-600/15 border-blue-500/60'
                        : 'bg-slate-950 border-slate-800'
                    }`}
                  >
                    <div className="flex items-center justify-between gap-2">
                      <div>
                        <div className="text-xs font-bold text-white flex items-center gap-2">
                          <span>{u.full_name}</span>
                          {isCurrent && (
                            <span className="px-1.5 py-0.5 rounded bg-emerald-500/20 text-emerald-300 text-[10px]">
                              Active Session
                            </span>
                          )}
                        </div>
                        <div className="text-[11px] font-mono text-slate-400">
                          {u.email}
                        </div>
                      </div>

                      <div className="flex items-center gap-2">
                        {/* If current user is Admin, allow changing any user's role inline */}
                        {isAdmin ? (
                          <select
                            value={u.role}
                            onChange={(e) =>
                              handleRoleUpdate(u.id, e.target.value as UserRole)
                            }
                            className="bg-slate-900 text-xs font-semibold text-sky-300 px-2.5 py-1 rounded-lg border border-slate-700"
                          >
                            <option value="Admin">Role: Admin</option>
                            <option value="Data Architect">
                              Role: Data Architect
                            </option>
                            <option value="Data Steward">
                              Role: Data Steward
                            </option>
                            <option value="Viewer">Role: Viewer</option>
                          </select>
                        ) : (
                          <span
                            className={`px-2 py-0.5 rounded text-[10px] font-bold border ${
                              ROLE_BADGE_MAP[u.role] || ROLE_BADGE_MAP.Viewer
                            }`}
                          >
                            {u.role}
                          </span>
                        )}

                        {!isCurrent && (
                          <button
                            type="button"
                            onClick={() => loginAsUser(u.email, 'password123')}
                            className="px-2.5 py-1 rounded-lg bg-blue-600 hover:bg-blue-500 text-white text-xs font-semibold flex items-center gap-1"
                          >
                            <Check className="w-3 h-3" />
                            <span>Switch Session</span>
                          </button>
                        )}

                        {isAdmin && u.email !== 'admin@metaforge.local' && (
                          <button
                            type="button"
                            onClick={() => handleDeleteUser(u.id)}
                            title="Delete user"
                            className="p-1 text-slate-500 hover:text-rose-400"
                          >
                            <Trash2 className="w-3.5 h-3.5" />
                          </button>
                        )}
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>

          {/* Right: Admin Create User Panel */}
          <div className="lg:col-span-5 bg-slate-950 p-5 rounded-xl border border-slate-800 space-y-4">
            <div className="flex items-center gap-2">
              <UserPlus className="w-4 h-4 text-rose-400" />
              <h3 className="text-xs font-bold uppercase tracking-wider text-white">
                Create New Enterprise User
              </h3>
            </div>

            {!isAdmin ? (
              <div className="p-4 rounded-xl bg-amber-500/10 border border-amber-500/30 text-xs text-amber-200 space-y-2">
                <p className="font-semibold">Admin Privileges Required</p>
                <p>
                  Your active role is <strong>{currentUser.role}</strong>. Click{' '}
                  <strong>Switch Session</strong> next to{' '}
                  <code>admin@metaforge.local</code> on the left to create new users or assign Admin/Architect/Steward/Viewer roles.
                </p>
              </div>
            ) : (
              <form onSubmit={handleCreateUser} className="space-y-3 text-xs">
                <div>
                  <label className="text-[11px] text-slate-400 block mb-1">
                    Full Name
                  </label>
                  <input
                    required
                    value={newFullName}
                    onChange={(e) => setNewFullName(e.target.value)}
                    placeholder="e.g. Jordan Rivera"
                    className="w-full bg-slate-900 text-white px-3 py-2 rounded-lg border border-slate-700"
                  />
                </div>

                <div>
                  <label className="text-[11px] text-slate-400 block mb-1">
                    Email Address
                  </label>
                  <input
                    type="email"
                    required
                    value={newEmail}
                    onChange={(e) => setNewEmail(e.target.value)}
                    placeholder="e.g. jordan@metaforge.local"
                    className="w-full bg-slate-900 font-mono text-white px-3 py-2 rounded-lg border border-slate-700"
                  />
                </div>

                <div>
                  <label className="text-[11px] text-slate-400 block mb-1">
                    Initial Password
                  </label>
                  <input
                    type="text"
                    required
                    value={newPassword}
                    onChange={(e) => setNewPassword(e.target.value)}
                    className="w-full bg-slate-900 font-mono text-white px-3 py-2 rounded-lg border border-slate-700"
                  />
                </div>

                <div>
                  <label className="text-[11px] text-slate-400 block mb-1">
                    Assign RBAC Role (Including Admin)
                  </label>
                  <select
                    value={newRole}
                    onChange={(e) => setNewRole(e.target.value as UserRole)}
                    className="w-full bg-slate-900 text-white px-3 py-2 rounded-lg border border-slate-700 font-semibold"
                  >
                    <option value="Admin">Admin (Full System &amp; User Admin)</option>
                    <option value="Data Architect">
                      Data Architect (Full Physical &amp; Logical Modeling)
                    </option>
                    <option value="Data Steward">
                      Data Steward (Business Metadata &amp; PII Governance Only)
                    </option>
                    <option value="Viewer">Viewer (Read-Only &amp; Model Q&amp;A)</option>
                  </select>
                </div>

                <p className="text-[11px] text-slate-400 leading-relaxed pt-1">
                  {ROLE_DESCRIPTIONS[newRole]}
                </p>

                <button
                  type="submit"
                  className="w-full py-2.5 rounded-lg bg-rose-600 hover:bg-rose-500 text-white font-bold shadow flex items-center justify-center gap-1.5"
                >
                  <UserPlus className="w-3.5 h-3.5" />
                  <span>Create User Account</span>
                </button>
              </form>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};
