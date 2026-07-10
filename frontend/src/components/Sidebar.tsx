'use client';

import Link from 'next/link';
import { useParams, useRouter } from 'next/navigation';
import { useEffect, useRef, useState } from 'react';
import { createSession, listSessions, listCloudAccounts, getMe, type Session, type CloudAccount, type Me } from '@/lib/api';
import { clearToken } from '@/lib/auth';
import { Plus, MessageSquare, LogOut, Home, Sparkles, Cloud, ChevronUp, Shield, Building2, Key } from 'lucide-react';

function timeAgo(dateStr: string): string {
  const diff = Date.now() - new Date(dateStr).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return 'now';
  if (mins < 60) return `${mins}m`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h`;
  return `${Math.floor(hrs / 24)}d`;
}

interface Props {
  onOpenCloudConnect?: () => void;
}

export default function Sidebar({ onOpenCloudConnect }: Props) {
  const [sessions, setSessions] = useState<Session[]>([]);
  const [creating, setCreating] = useState(false);
  const [cloudAccount, setCloudAccount] = useState<CloudAccount | null | undefined>(undefined);
  const [me, setMe] = useState<Me | null>(null);
  const [profileOpen, setProfileOpen] = useState(false);
  const profileRef = useRef<HTMLDivElement>(null);
  const params = useParams();
  const router = useRouter();
  const activeId = params?.sessionId as string | undefined;

  useEffect(() => {
    listSessions().then(setSessions).catch(() => {});
    listCloudAccounts()
      .then((accounts) => setCloudAccount(accounts.find((a) => a.status === 'verified') ?? null))
      .catch(() => setCloudAccount(null));
    getMe().then(setMe).catch(() => {});
  }, []);

  // Close popover on outside click
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (profileRef.current && !profileRef.current.contains(e.target as Node)) {
        setProfileOpen(false);
      }
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, []);

  const handleNew = async () => {
    setCreating(true);
    try {
      const s = await createSession();
      setSessions((prev) => [s, ...prev]);
      router.push(`/chat/${s.id}`);
    } finally {
      setCreating(false);
    }
  };

  const handleLogout = () => {
    clearToken();
    router.replace('/login');
  };

  return (
    <aside className="w-[220px] shrink-0 flex flex-col border-r"
      style={{ background: 'var(--ink)', borderColor: 'var(--border)' }}>

      {/* Logo */}
      <div className="px-4 py-4 flex items-center gap-2.5 border-b" style={{ borderColor: 'var(--border)' }}>
        <div className="w-7 h-7 rounded-lg bg-gradient-to-br from-indigo-500 to-violet-600
          flex items-center justify-center shrink-0 shadow-[0_0_15px_rgba(99,102,241,0.3)]">
          <Sparkles className="w-3.5 h-3.5 text-white" />
        </div>
        <div>
          <span className="text-sm font-semibold text-white">Loomaris</span>
          <span className="ml-1.5 text-[9px] font-mono text-indigo-400/70 bg-indigo-400/10
            px-1 py-0.5 rounded-sm border border-indigo-400/15">Labs</span>
        </div>
      </div>

      {/* Actions */}
      <div className="px-3 py-3 space-y-1 border-b" style={{ borderColor: 'var(--border)' }}>
        <Link href="/chat"
          className="flex items-center gap-2.5 px-3 py-2 rounded-lg text-xs text-slate-400
            hover:text-slate-200 hover:bg-white/[0.04] transition-all group">
          <Home className="w-3.5 h-3.5 group-hover:text-indigo-400 transition-colors" />
          Home
        </Link>

        <button onClick={handleNew} disabled={creating}
          className="w-full flex items-center gap-2.5 px-3 py-2 rounded-lg text-xs
            font-medium transition-all group disabled:opacity-50
            text-indigo-300 hover:text-white hover:bg-indigo-500/10
            border border-indigo-500/20 hover:border-indigo-500/35">
          <Plus className="w-3.5 h-3.5 group-hover:rotate-90 transition-transform duration-200" />
          {creating ? 'Creating…' : 'New conversation'}
        </button>
      </div>

      {/* Cloud status */}
      {cloudAccount !== undefined && (
        <div className="px-3 py-2.5 border-b" style={{ borderColor: 'var(--border)' }}>
          {cloudAccount ? (
            <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg"
              style={{ background: 'rgba(52,211,153,0.05)' }}>
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 shrink-0" />
              <div className="min-w-0 flex-1">
                <p className="text-[10px] font-medium text-emerald-400/80 truncate">
                  {cloudAccount.display_name}
                </p>
                <p className="text-[9px] font-mono text-slate-600 truncate">
                  {cloudAccount.external_id}
                </p>
              </div>
            </div>
          ) : (
            <button onClick={onOpenCloudConnect}
              className="w-full flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs
                text-amber-500/70 hover:text-amber-400 hover:bg-amber-500/5 transition-all group">
              <span className="w-1.5 h-1.5 rounded-full bg-amber-400/60 shrink-0" />
              <Cloud className="w-3 h-3 shrink-0" />
              Connect AWS
            </button>
          )}
        </div>
      )}

      {/* Session list */}
      <div className="flex-1 overflow-y-auto py-2 px-2">
        {sessions.length === 0 && (
          <div className="flex flex-col items-center justify-center py-10 text-center px-4">
            <MessageSquare className="w-6 h-6 text-slate-700 mb-2" />
            <p className="text-xs text-slate-600">No conversations yet</p>
            <p className="text-[11px] text-slate-700 mt-1">Start one above</p>
          </div>
        )}

        {sessions.map((s) => {
          const isActive = s.id === activeId;
          return (
            <Link key={s.id} href={`/chat/${s.id}`}
              className={`group flex items-start gap-2.5 px-3 py-2.5 rounded-lg mb-0.5
                transition-all relative overflow-hidden
                ${isActive
                  ? 'bg-indigo-500/10 text-white border border-indigo-500/20'
                  : 'text-slate-500 hover:text-slate-300 hover:bg-white/[0.03]'
                }`}>

              {isActive && (
                <div className="absolute inset-y-0 left-0 w-0.5 bg-indigo-400 rounded-r-full" />
              )}

              <MessageSquare className={`w-3.5 h-3.5 shrink-0 mt-0.5
                ${isActive ? 'text-indigo-400' : 'text-slate-600 group-hover:text-slate-500'}`} />

              <div className="min-w-0 flex-1">
                <p className="text-xs truncate leading-tight">
                  {s.title || 'Untitled'}
                </p>
                <p className="text-[10px] mt-0.5 text-slate-600">
                  {timeAgo(s.last_active_at)}
                </p>
              </div>
            </Link>
          );
        })}
      </div>

      {/* Profile footer */}
      <div className="px-3 py-3 border-t relative" style={{ borderColor: 'var(--border)' }} ref={profileRef}>

        {/* Profile popover */}
        {profileOpen && me && (
          <div className="absolute bottom-full left-2 right-2 mb-2 rounded-xl border shadow-2xl overflow-hidden"
            style={{ background: 'var(--card)', borderColor: 'var(--border)' }}>

            {/* User info */}
            <div className="px-4 py-3 border-b" style={{ borderColor: 'var(--border)' }}>
              <div className="flex items-center gap-3 mb-2">
                {me.user.picture ? (
                  <img src={me.user.picture} alt="" className="w-9 h-9 rounded-full object-cover shrink-0" />
                ) : (
                  <div className="w-9 h-9 rounded-full bg-indigo-500/20 border border-indigo-500/30
                    flex items-center justify-center shrink-0 text-sm font-semibold text-indigo-300">
                    {me.user.name?.[0]?.toUpperCase() ?? '?'}
                  </div>
                )}
                <div className="min-w-0">
                  <p className="text-sm font-semibold text-white truncate">{me.user.name}</p>
                  <p className="text-xs text-slate-500 truncate">{me.user.email}</p>
                </div>
              </div>

              {/* Badges */}
              <div className="flex flex-wrap gap-1.5">
                {me.user.is_superadmin && (
                  <span className="inline-flex items-center gap-1 text-[10px] px-1.5 py-0.5 rounded-md
                    bg-indigo-500/15 border border-indigo-500/25 text-indigo-300 font-medium">
                    <Shield className="w-2.5 h-2.5" /> Superadmin
                  </span>
                )}
                {me.org && (
                  <span className="inline-flex items-center gap-1 text-[10px] px-1.5 py-0.5 rounded-md
                    bg-white/5 border border-white/10 text-slate-400 font-medium">
                    <Building2 className="w-2.5 h-2.5" />
                    {me.org.name} · {me.role}
                  </span>
                )}
              </div>
            </div>

            {/* Actions */}
            <div className="py-1">
              {me.user.is_superadmin && (
                <button
                  onClick={() => { setProfileOpen(false); router.push('/admin'); }}
                  className="w-full flex items-center gap-2.5 px-4 py-2 text-xs text-slate-400
                    hover:text-white hover:bg-white/[0.04] transition-all">
                  <Shield className="w-3.5 h-3.5 text-indigo-400" />
                  Admin panel
                </button>
              )}
              {(me.role === 'owner' || me.role === 'admin' || me.user.is_superadmin) && (
                <button
                  onClick={() => { setProfileOpen(false); onOpenCloudConnect?.(); }}
                  className="w-full flex items-center gap-2.5 px-4 py-2 text-xs text-slate-400
                    hover:text-white hover:bg-white/[0.04] transition-all">
                  <Key className="w-3.5 h-3.5 text-slate-500" />
                  {me.user.has_claude_key ? 'Rotate API key' : 'Add API key'}
                </button>
              )}
              <button
                onClick={() => { setProfileOpen(false); handleLogout(); }}
                className="w-full flex items-center gap-2.5 px-4 py-2 text-xs text-slate-400
                  hover:text-rose-400 hover:bg-white/[0.04] transition-all">
                <LogOut className="w-3.5 h-3.5" />
                Sign out
              </button>
            </div>
          </div>
        )}

        {/* Profile trigger */}
        <button
          onClick={() => setProfileOpen((p) => !p)}
          className="w-full flex items-center gap-2.5 px-2 py-2 rounded-xl
            hover:bg-white/[0.04] transition-all group">
          {me?.user.picture ? (
            <img src={me.user.picture} alt="" className="w-7 h-7 rounded-full object-cover shrink-0" />
          ) : (
            <div className="w-7 h-7 rounded-full bg-indigo-500/20 border border-indigo-500/30
              flex items-center justify-center shrink-0 text-xs font-semibold text-indigo-300">
              {me?.user.name?.[0]?.toUpperCase() ?? '?'}
            </div>
          )}
          <div className="flex-1 min-w-0 text-left">
            <p className="text-xs font-medium text-slate-300 truncate">{me?.user.name ?? '…'}</p>
            <p className="text-[10px] text-slate-600 truncate">{me?.org?.name ?? 'No org'}</p>
          </div>
          <ChevronUp className={`w-3.5 h-3.5 text-slate-600 shrink-0 transition-transform
            ${profileOpen ? 'rotate-180' : ''}`} />
        </button>
      </div>
    </aside>
  );
}
