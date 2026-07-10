'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import {
  Shield, Building2, Users, Ban, CheckCircle2,
  RefreshCw, LogOut, Loader2,
} from 'lucide-react';
import { consumeAuthHash, getToken, setToken, clearToken } from '@/lib/auth';
import { getMe, adminListOrgs, adminSuspendOrg, adminUnsuspendOrg } from '@/lib/api';

interface AdminOrg {
  id: string;
  name: string;
  slug: string;
  plan: string;
  description: string | null;
  member_count: number;
  suspended: boolean;
  suspended_at: string | null;
  created_at: string;
}

export default function AdminPage() {
  const router = useRouter();
  const [orgs, setOrgs] = useState<AdminOrg[]>([]);
  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const auth = consumeAuthHash();
    if (auth) setToken(auth.token);
    if (!getToken()) { router.replace('/login'); return; }

    getMe()
      .then(me => {
        if (!me.user.is_superadmin) {
          router.replace(me.membership_status === 'active' ? '/chat' : '/onboarding');
          return;
        }
        return adminListOrgs();
      })
      .then(data => { if (data) setOrgs(data); })
      .catch(() => setError('Failed to load data'))
      .finally(() => setLoading(false));
  }, [router]);

  const refresh = async () => {
    setLoading(true);
    try { setOrgs(await adminListOrgs()); }
    catch { setError('Failed to refresh'); }
    finally { setLoading(false); }
  };

  const toggleSuspend = async (org: AdminOrg) => {
    setActionLoading(org.id);
    try {
      if (org.suspended) {
        await adminUnsuspendOrg(org.id);
      } else {
        await adminSuspendOrg(org.id);
      }
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Action failed');
    } finally {
      setActionLoading(null);
    }
  };

  const planColor: Record<string, string> = {
    trial: 'text-slate-400',
    starter: 'text-sky-400',
    pro: 'text-indigo-400',
  };

  return (
    <div className="min-h-screen" style={{ background: 'var(--void)' }}>
      {/* Header */}
      <div className="border-b px-6 py-4 flex items-center justify-between"
        style={{ borderColor: 'var(--border)', background: 'var(--surface)' }}>
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-lg bg-indigo-500/20 border border-indigo-500/30
            flex items-center justify-center">
            <Shield className="w-4 h-4 text-indigo-400" />
          </div>
          <div>
            <h1 className="text-sm font-semibold text-white">Loomaris Admin</h1>
            <p className="text-xs text-slate-500">Superadmin panel</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={refresh}
            disabled={loading}
            className="p-1.5 rounded-lg text-slate-500 hover:text-slate-300 hover:bg-white/5 transition-colors">
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
          </button>
          <button
            onClick={() => router.push('/chat')}
            className="text-xs text-slate-500 hover:text-slate-300 transition-colors px-2 py-1 rounded-lg hover:bg-white/5">
            Back to chat
          </button>
          <button
            onClick={() => { clearToken(); router.replace('/login'); }}
            className="flex items-center gap-1.5 text-xs text-slate-500 hover:text-slate-300 transition-colors
              px-2 py-1 rounded-lg hover:bg-white/5">
            <LogOut className="w-3 h-3" /> Sign out
          </button>
        </div>
      </div>

      <div className="max-w-5xl mx-auto px-6 py-8">

        {/* Stats */}
        <div className="grid grid-cols-3 gap-4 mb-8">
          {[
            { label: 'Total orgs', value: orgs.length, icon: Building2 },
            { label: 'Active orgs', value: orgs.filter(o => !o.suspended).length, icon: CheckCircle2 },
            { label: 'Total members', value: orgs.reduce((s, o) => s + o.member_count, 0), icon: Users },
          ].map(({ label, value, icon: Icon }) => (
            <div key={label} className="rounded-xl border p-4 flex items-center gap-4"
              style={{ background: 'var(--card)', borderColor: 'var(--border)' }}>
              <div className="w-10 h-10 rounded-lg bg-indigo-500/10 border border-indigo-500/20
                flex items-center justify-center shrink-0">
                <Icon className="w-4.5 h-4.5 text-indigo-400" />
              </div>
              <div>
                <p className="text-2xl font-bold text-white">{value}</p>
                <p className="text-xs text-slate-500">{label}</p>
              </div>
            </div>
          ))}
        </div>

        {error && (
          <div className="mb-4 text-xs text-rose-400 px-3 py-2 rounded-lg border border-rose-500/20
            bg-rose-500/5">
            {error}
          </div>
        )}

        {/* Orgs table */}
        <div className="rounded-xl border overflow-hidden"
          style={{ borderColor: 'var(--border)', background: 'var(--card)' }}>
          <div className="px-4 py-3 border-b flex items-center justify-between"
            style={{ borderColor: 'var(--border)' }}>
            <span className="text-xs font-medium text-slate-400">All Organizations</span>
            <span className="text-xs text-slate-600">{orgs.length} total</span>
          </div>

          {loading ? (
            <div className="flex items-center justify-center py-16">
              <Loader2 className="w-5 h-5 text-slate-500 animate-spin" />
            </div>
          ) : orgs.length === 0 ? (
            <p className="text-center text-sm text-slate-600 py-16">No organizations yet</p>
          ) : (
            <div className="divide-y" style={{ borderColor: 'var(--border)' }}>
              {orgs.map(org => (
                <div key={org.id}
                  className={`px-4 py-3 flex items-center gap-4 ${org.suspended ? 'opacity-60' : ''}`}>
                  {/* Org info */}
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-medium text-white truncate">{org.name}</span>
                      {org.suspended && (
                        <span className="text-[10px] px-1.5 py-0.5 rounded font-medium bg-rose-500/15
                          text-rose-400 border border-rose-500/20">
                          suspended
                        </span>
                      )}
                      <span className={`text-[11px] font-mono ${planColor[org.plan] ?? 'text-slate-400'}`}>
                        {org.plan}
                      </span>
                    </div>
                    <p className="text-xs text-slate-500 font-mono mt-0.5">{org.slug}</p>
                    {org.description && (
                      <p className="text-xs text-slate-600 mt-0.5 truncate">{org.description}</p>
                    )}
                  </div>

                  {/* Members */}
                  <div className="flex items-center gap-1 text-xs text-slate-500 shrink-0">
                    <Users className="w-3 h-3" />
                    {org.member_count}
                  </div>

                  {/* Created */}
                  <div className="text-xs text-slate-600 shrink-0 hidden md:block w-24 text-right">
                    {new Date(org.created_at).toLocaleDateString()}
                  </div>

                  {/* Actions */}
                  <button
                    onClick={() => toggleSuspend(org)}
                    disabled={actionLoading === org.id}
                    className="shrink-0 flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-xs
                      font-medium transition-all disabled:opacity-50"
                    style={org.suspended ? {
                      background: 'rgba(52,211,153,0.1)',
                      border: '1px solid rgba(52,211,153,0.25)',
                      color: '#34d399',
                    } : {
                      background: 'rgba(251,113,133,0.1)',
                      border: '1px solid rgba(251,113,133,0.2)',
                      color: '#fb7185',
                    }}>
                    {actionLoading === org.id
                      ? <Loader2 className="w-3 h-3 animate-spin" />
                      : org.suspended
                        ? <><CheckCircle2 className="w-3 h-3" />Restore</>
                        : <><Ban className="w-3 h-3" />Suspend</>
                    }
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>

        <p className="mt-6 text-xs text-slate-600 text-center">
          Logged in as superadmin ·{' '}
          <a href="/docs" className="text-indigo-400/70 hover:text-indigo-400">API docs</a>
        </p>
      </div>
    </div>
  );
}
