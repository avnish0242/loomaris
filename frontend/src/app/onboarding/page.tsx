'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { Building2, Users, ChevronRight, Loader2, Search, ArrowLeft } from 'lucide-react';
import { consumeAuthHash, getToken, setToken } from '@/lib/auth';
import { createOrg, listOrgs, requestToJoin, type OrgPublic } from '@/lib/api';

type Step = 'choose' | 'create' | 'join';

export default function OnboardingPage() {
  const router = useRouter();
  const [step, setStep] = useState<Step>('choose');
  const [orgs, setOrgs] = useState<OrgPublic[]>([]);
  const [search, setSearch] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Create form
  const [orgName, setOrgName] = useState('');
  const [orgDesc, setOrgDesc] = useState('');
  const [joinPolicy, setJoinPolicy] = useState('approval_required');

  useEffect(() => {
    // Handle fresh OAuth token landing on this page
    const auth = consumeAuthHash();
    if (auth) setToken(auth.token);

    if (!getToken()) { router.replace('/login'); return; }
    listOrgs().then(setOrgs).catch(() => {});
  }, [router]);

  const filtered = orgs.filter(o =>
    o.name.toLowerCase().includes(search.toLowerCase()) ||
    (o.description ?? '').toLowerCase().includes(search.toLowerCase())
  );

  const handleCreate = async () => {
    if (!orgName.trim()) return;
    setLoading(true); setError(null);
    try {
      await createOrg({ name: orgName.trim(), description: orgDesc.trim() || undefined, join_policy: joinPolicy });
      router.replace('/chat');
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to create org');
    } finally { setLoading(false); }
  };

  const handleJoin = async (org: OrgPublic) => {
    setLoading(true); setError(null);
    try {
      const res = await requestToJoin(org.id);
      if (res.status === 'active') {
        router.replace('/chat');
      } else {
        router.replace('/waiting');
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to send join request');
    } finally { setLoading(false); }
  };

  const card = 'rounded-2xl border p-6 transition-all';
  const cardStyle = { background: 'var(--card)', borderColor: 'var(--border)' };

  return (
    <div className="min-h-screen mesh-bg dot-grid flex flex-col items-center justify-center px-6 py-12">
      <div className="w-full max-w-lg">

        {/* Logo */}
        <div className="text-center mb-8">
          <div className="inline-flex items-center justify-center w-12 h-12 rounded-xl
            bg-gradient-to-br from-indigo-500 to-violet-600 mb-4">
            <span className="text-white text-xl font-bold">L</span>
          </div>
          <h1 className="text-2xl font-bold text-white">Set up your workspace</h1>
          <p className="text-sm text-slate-400 mt-1">Create a new org or join an existing one</p>
        </div>

        {/* ── Step: choose ── */}
        {step === 'choose' && (
          <div className="grid grid-cols-2 gap-4">
            <button onClick={() => setStep('create')}
              className={`${card} text-left hover:border-indigo-500/50 hover:bg-indigo-500/5 group`}
              style={cardStyle}>
              <Building2 className="w-7 h-7 text-indigo-400 mb-3" />
              <h3 className="text-sm font-semibold text-white mb-1">Create org</h3>
              <p className="text-xs text-slate-500 leading-relaxed">Start fresh — you'll be the admin</p>
              <ChevronRight className="w-4 h-4 text-slate-600 mt-3 group-hover:text-indigo-400 transition-colors" />
            </button>

            <button onClick={() => setStep('join')}
              className={`${card} text-left hover:border-violet-500/50 hover:bg-violet-500/5 group`}
              style={cardStyle}>
              <Users className="w-7 h-7 text-violet-400 mb-3" />
              <h3 className="text-sm font-semibold text-white mb-1">Join org</h3>
              <p className="text-xs text-slate-500 leading-relaxed">Request to join an existing team</p>
              <ChevronRight className="w-4 h-4 text-slate-600 mt-3 group-hover:text-violet-400 transition-colors" />
            </button>
          </div>
        )}

        {/* ── Step: create ── */}
        {step === 'create' && (
          <div className={card} style={cardStyle}>
            <button onClick={() => setStep('choose')}
              className="flex items-center gap-1.5 text-xs text-slate-500 hover:text-slate-300 mb-5 transition-colors">
              <ArrowLeft className="w-3.5 h-3.5" /> Back
            </button>
            <h2 className="text-base font-semibold text-white mb-4">Create your organization</h2>
            <div className="space-y-3">
              <div>
                <label className="block text-xs font-medium text-slate-400 mb-1.5">Organization name *</label>
                <input type="text" value={orgName} onChange={e => setOrgName(e.target.value)}
                  placeholder="Acme Inc." autoFocus
                  className="w-full px-3.5 py-2.5 rounded-xl text-sm text-slate-200 placeholder:text-slate-600
                    border outline-none focus:ring-1 focus:ring-indigo-500/50"
                  style={{ background: 'rgba(0,0,0,0.3)', borderColor: 'var(--border)' }} />
              </div>
              <div>
                <label className="block text-xs font-medium text-slate-400 mb-1.5">Description</label>
                <input type="text" value={orgDesc} onChange={e => setOrgDesc(e.target.value)}
                  placeholder="What does your team build?"
                  className="w-full px-3.5 py-2.5 rounded-xl text-sm text-slate-200 placeholder:text-slate-600
                    border outline-none focus:ring-1 focus:ring-indigo-500/50"
                  style={{ background: 'rgba(0,0,0,0.3)', borderColor: 'var(--border)' }} />
              </div>
              <div>
                <label className="block text-xs font-medium text-slate-400 mb-1.5">Who can join?</label>
                <select value={joinPolicy} onChange={e => setJoinPolicy(e.target.value)}
                  className="w-full px-3.5 py-2.5 rounded-xl text-sm text-slate-200 border outline-none"
                  style={{ background: 'rgba(0,0,0,0.3)', borderColor: 'var(--border)' }}>
                  <option value="approval_required">Approval required (recommended)</option>
                  <option value="open">Open — anyone can join</option>
                  <option value="invite_only">Invite only</option>
                </select>
              </div>

              {error && <p className="text-xs text-rose-400">{error}</p>}

              <button onClick={handleCreate} disabled={!orgName.trim() || loading}
                className="w-full py-2.5 rounded-xl text-sm font-medium transition-all
                  disabled:opacity-40 disabled:cursor-not-allowed mt-2"
                style={{
                  background: 'rgba(99,102,241,0.2)',
                  border: '1px solid rgba(99,102,241,0.35)',
                  color: '#a5b4fc',
                }}>
                {loading ? <><Loader2 className="w-3.5 h-3.5 inline animate-spin mr-2" />Creating…</> : 'Create Organization'}
              </button>
            </div>
          </div>
        )}

        {/* ── Step: join ── */}
        {step === 'join' && (
          <div className={card} style={cardStyle}>
            <button onClick={() => setStep('choose')}
              className="flex items-center gap-1.5 text-xs text-slate-500 hover:text-slate-300 mb-5 transition-colors">
              <ArrowLeft className="w-3.5 h-3.5" /> Back
            </button>
            <h2 className="text-base font-semibold text-white mb-4">Join an organization</h2>

            <div className="relative mb-4">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-slate-500" />
              <input type="text" value={search} onChange={e => setSearch(e.target.value)}
                placeholder="Search organizations…"
                className="w-full pl-9 pr-3.5 py-2.5 rounded-xl text-sm text-slate-200 placeholder:text-slate-600
                  border outline-none focus:ring-1 focus:ring-violet-500/50"
                style={{ background: 'rgba(0,0,0,0.3)', borderColor: 'var(--border)' }} />
            </div>

            {error && <p className="text-xs text-rose-400 mb-3">{error}</p>}

            <div className="space-y-2 max-h-72 overflow-y-auto">
              {filtered.length === 0 ? (
                <p className="text-xs text-slate-600 text-center py-6">No organizations found</p>
              ) : filtered.map(org => (
                <div key={org.id}
                  className="flex items-center justify-between p-3 rounded-xl border hover:border-violet-500/30
                    hover:bg-violet-500/5 transition-all"
                  style={{ borderColor: 'var(--border)' }}>
                  <div className="min-w-0">
                    <p className="text-sm font-medium text-white truncate">{org.name}</p>
                    {org.description && (
                      <p className="text-xs text-slate-500 truncate mt-0.5">{org.description}</p>
                    )}
                    <div className="flex items-center gap-2 mt-1">
                      <span className="text-[11px] text-slate-600">{org.member_count} members</span>
                      {org.join_policy === 'open' && (
                        <span className="text-[11px] text-emerald-500/80">Open</span>
                      )}
                      {org.join_policy === 'approval_required' && (
                        <span className="text-[11px] text-amber-500/80">Approval required</span>
                      )}
                      {org.join_policy === 'invite_only' && (
                        <span className="text-[11px] text-slate-500">Invite only</span>
                      )}
                    </div>
                  </div>
                  <button onClick={() => handleJoin(org)}
                    disabled={loading || org.join_policy === 'invite_only'}
                    className="ml-3 shrink-0 px-3 py-1.5 rounded-lg text-xs font-medium transition-all
                      disabled:opacity-40 disabled:cursor-not-allowed"
                    style={{
                      background: 'rgba(139,92,246,0.15)',
                      border: '1px solid rgba(139,92,246,0.3)',
                      color: '#c4b5fd',
                    }}>
                    {loading ? <Loader2 className="w-3 h-3 animate-spin" /> : 'Request'}
                  </button>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
