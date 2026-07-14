'use client';

import { useCallback, useEffect, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import {
  getMe, listJoinRequests, approveJoinRequest, rejectJoinRequest,
  listMembers, removeMember, inviteMember, listCloudAccounts,
  getCloudSetupInfo, connectCloudRoleAccount, verifyCloudAccount,
  saveClaudeKey, getClaudeKeyStatus, updateOrg,
  type Me, type JoinRequest, type OrgMember, type CloudAccount, type CloudSetupInfo,
} from '@/lib/api';
import {
  Users, Settings2, Blocks, CheckCircle2, XCircle, Trash2, Mail,
  Copy, Check, RefreshCw, Shield, Cloud, Key, AlertTriangle,
  ChevronRight, Loader2,
} from 'lucide-react';

// ── Helpers ────────────────────────────────────────────────────────────────────

function timeAgo(dateStr: string) {
  const diff = Date.now() - new Date(dateStr).getTime();
  const days = Math.floor(diff / 86400000);
  if (days < 1) return 'today';
  if (days === 1) return 'yesterday';
  return `${days}d ago`;
}

function Avatar({ name, picture, size = 8 }: { name: string | null; picture: string | null; size?: number }) {
  const sz = `w-${size} h-${size}`;
  return picture ? (
    <img src={picture} alt="" className={`${sz} rounded-full object-cover shrink-0`} />
  ) : (
    <div className={`${sz} rounded-full bg-indigo-500/20 border border-indigo-500/30
      flex items-center justify-center shrink-0 text-xs font-semibold text-indigo-300`}>
      {name?.[0]?.toUpperCase() ?? '?'}
    </div>
  );
}

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  const copy = () => {
    navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };
  return (
    <button onClick={copy}
      className="flex items-center gap-1 text-[10px] px-2 py-1 rounded-md
        text-slate-400 hover:text-white hover:bg-white/[0.06] transition-all border border-white/[0.06]">
      {copied ? <Check className="w-3 h-3 text-emerald-400" /> : <Copy className="w-3 h-3" />}
      {copied ? 'Copied' : 'Copy'}
    </button>
  );
}

// ── Tab bar ────────────────────────────────────────────────────────────────────

const TABS = [
  { id: 'members', label: 'Members', icon: Users },
  { id: 'integrations', label: 'Integrations', icon: Blocks },
  { id: 'organization', label: 'Organization', icon: Settings2 },
] as const;

type TabId = typeof TABS[number]['id'];

// ── Members Tab ────────────────────────────────────────────────────────────────

function MembersTab({ orgId }: { orgId: string }) {
  const [requests, setRequests] = useState<JoinRequest[]>([]);
  const [members, setMembers] = useState<OrgMember[]>([]);
  const [loading, setLoading] = useState(true);
  const [actioning, setActioning] = useState<string | null>(null);
  const [inviteEmail, setInviteEmail] = useState('');
  const [inviteRole, setInviteRole] = useState('member');
  const [inviteUrl, setInviteUrl] = useState<string | null>(null);
  const [inviting, setInviting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [reqs, mems] = await Promise.all([listJoinRequests(orgId), listMembers(orgId)]);
      setRequests(reqs);
      setMembers(mems);
    } catch (e: any) { setError(e.message); }
    finally { setLoading(false); }
  }, [orgId]);

  useEffect(() => { load(); }, [load]);

  const approve = async (userId: string) => {
    setActioning(userId);
    try {
      await approveJoinRequest(orgId, userId);
      await load();
    } catch (e: any) { setError(e.message); }
    finally { setActioning(null); }
  };

  const reject = async (userId: string) => {
    setActioning(`reject-${userId}`);
    try {
      await rejectJoinRequest(orgId, userId);
      setRequests((r) => r.filter((x) => x.user_id !== userId));
    } catch (e: any) { setError(e.message); }
    finally { setActioning(null); }
  };

  const kick = async (userId: string) => {
    if (!confirm('Remove this member?')) return;
    setActioning(`kick-${userId}`);
    try {
      await removeMember(orgId, userId);
      setMembers((m) => m.filter((x) => x.user_id !== userId));
    } catch (e: any) { setError(e.message); }
    finally { setActioning(null); }
  };

  const sendInvite = async (e: React.FormEvent) => {
    e.preventDefault();
    setInviting(true);
    setInviteUrl(null);
    try {
      const res = await inviteMember(orgId, inviteEmail, inviteRole);
      setInviteUrl(res.invite_url);
      setInviteEmail('');
    } catch (e: any) { setError(e.message); }
    finally { setInviting(false); }
  };

  if (loading) return <div className="flex justify-center py-16"><Loader2 className="w-5 h-5 animate-spin text-slate-500" /></div>;

  return (
    <div className="space-y-6">
      {error && (
        <div className="flex items-center gap-2 px-4 py-3 rounded-xl bg-rose-500/10 border border-rose-500/20 text-sm text-rose-400">
          <AlertTriangle className="w-4 h-4 shrink-0" /> {error}
        </div>
      )}

      {/* Pending requests */}
      {requests.length > 0 && (
        <section>
          <div className="flex items-center gap-2 mb-3">
            <span className="text-xs font-semibold text-amber-400 uppercase tracking-wider">
              Pending Requests
            </span>
            <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-amber-500/20 text-amber-400 border border-amber-500/30 font-bold">
              {requests.length}
            </span>
          </div>
          <div className="rounded-xl border overflow-hidden" style={{ borderColor: 'var(--border)' }}>
            {requests.map((req, i) => (
              <div key={req.user_id}
                className={`flex items-center gap-3 px-4 py-3 ${i < requests.length - 1 ? 'border-b' : ''}`}
                style={{ background: 'var(--card)', borderColor: 'var(--border)' }}>
                <Avatar name={req.name} picture={req.picture} size={8} />
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium text-slate-200 truncate">{req.name ?? req.email}</p>
                  <p className="text-xs text-slate-500 truncate">{req.email} · {timeAgo(req.requested_at)}</p>
                </div>
                <div className="flex items-center gap-2 shrink-0">
                  <button onClick={() => approve(req.user_id)} disabled={actioning === req.user_id}
                    className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium
                      bg-emerald-500/15 text-emerald-400 border border-emerald-500/25
                      hover:bg-emerald-500/25 transition-all disabled:opacity-50">
                    {actioning === req.user_id
                      ? <Loader2 className="w-3 h-3 animate-spin" />
                      : <CheckCircle2 className="w-3 h-3" />}
                    Approve
                  </button>
                  <button onClick={() => reject(req.user_id)} disabled={actioning === `reject-${req.user_id}`}
                    className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium
                      text-slate-400 border border-white/[0.08] hover:text-rose-400
                      hover:border-rose-500/25 transition-all disabled:opacity-50">
                    <XCircle className="w-3 h-3" />
                    Reject
                  </button>
                </div>
              </div>
            ))}
          </div>
        </section>
      )}

      {/* Member list */}
      <section>
        <p className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-3">
          Members ({members.length})
        </p>
        <div className="rounded-xl border overflow-hidden" style={{ borderColor: 'var(--border)' }}>
          {members.length === 0 ? (
            <div className="px-4 py-8 text-center text-xs text-slate-600" style={{ background: 'var(--card)' }}>
              No members yet
            </div>
          ) : members.map((m, i) => (
            <div key={m.user_id}
              className={`flex items-center gap-3 px-4 py-3 ${i < members.length - 1 ? 'border-b' : ''}`}
              style={{ background: 'var(--card)', borderColor: 'var(--border)' }}>
              <Avatar name={m.name} picture={m.picture} size={8} />
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium text-slate-200 truncate">{m.name ?? m.email}</p>
                <p className="text-xs text-slate-500 truncate">{m.email}</p>
              </div>
              <span className={`text-[10px] px-2 py-0.5 rounded-full font-medium border
                ${m.role === 'owner' ? 'bg-indigo-500/15 text-indigo-300 border-indigo-500/25'
                  : m.role === 'admin' ? 'bg-violet-500/15 text-violet-300 border-violet-500/25'
                  : 'bg-white/5 text-slate-400 border-white/10'}`}>
                {m.role}
              </span>
              {m.role !== 'owner' && (
                <button onClick={() => kick(m.user_id)} disabled={actioning === `kick-${m.user_id}`}
                  className="p-1.5 rounded-lg text-slate-600 hover:text-rose-400
                    hover:bg-rose-500/10 transition-all disabled:opacity-50">
                  {actioning === `kick-${m.user_id}`
                    ? <Loader2 className="w-3.5 h-3.5 animate-spin" />
                    : <Trash2 className="w-3.5 h-3.5" />}
                </button>
              )}
            </div>
          ))}
        </div>
      </section>

      {/* Invite */}
      <section>
        <p className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-3">Invite by Email</p>
        <div className="rounded-xl border p-4" style={{ background: 'var(--card)', borderColor: 'var(--border)' }}>
          <form onSubmit={sendInvite} className="flex items-center gap-2">
            <input
              type="email" required placeholder="colleague@example.com"
              value={inviteEmail} onChange={(e) => setInviteEmail(e.target.value)}
              className="flex-1 px-3 py-2 rounded-lg text-sm bg-white/[0.04] border text-slate-200
                placeholder:text-slate-600 focus:outline-none focus:border-indigo-500/50 transition-colors"
              style={{ borderColor: 'var(--border)' }} />
            <select value={inviteRole} onChange={(e) => setInviteRole(e.target.value)}
              className="px-3 py-2 rounded-lg text-xs bg-white/[0.04] border text-slate-400
                focus:outline-none focus:border-indigo-500/50 transition-colors"
              style={{ borderColor: 'var(--border)' }}>
              <option value="member">Member</option>
              <option value="admin">Admin</option>
            </select>
            <button type="submit" disabled={inviting}
              className="flex items-center gap-1.5 px-4 py-2 rounded-lg text-xs font-medium
                bg-indigo-500/20 text-indigo-300 border border-indigo-500/30
                hover:bg-indigo-500/30 transition-all disabled:opacity-50">
              {inviting ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Mail className="w-3.5 h-3.5" />}
              Send Invite
            </button>
          </form>

          {inviteUrl && (
            <div className="mt-3 p-3 rounded-lg bg-emerald-500/5 border border-emerald-500/15">
              <p className="text-xs text-emerald-400 mb-2 font-medium">Invite link generated — share this with them:</p>
              <div className="flex items-center gap-2">
                <code className="flex-1 text-[10px] font-mono text-slate-400 truncate">{inviteUrl}</code>
                <CopyButton text={inviteUrl} />
              </div>
            </div>
          )}
        </div>
      </section>
    </div>
  );
}

// ── Integrations Tab ───────────────────────────────────────────────────────────

function IntegrationsTab({ orgId }: { orgId: string }) {
  const [keyStatus, setKeyStatus] = useState<{ configured: boolean; source: string } | null>(null);
  const [keyInput, setKeyInput] = useState('');
  const [savingKey, setSavingKey] = useState(false);
  const [keyError, setKeyError] = useState<string | null>(null);
  const [keySaved, setKeySaved] = useState(false);

  const [cloudAccounts, setCloudAccounts] = useState<CloudAccount[]>([]);
  const [setupInfo, setSetupInfo] = useState<CloudSetupInfo | null>(null);
  const [awsStep, setAwsStep] = useState<1 | 2 | 3>(1);
  const [roleArn, setRoleArn] = useState('');
  const [displayName, setDisplayName] = useState('');
  const [awsRegion, setAwsRegion] = useState('us-east-1');
  const [connectingAws, setConnectingAws] = useState(false);
  const [awsError, setAwsError] = useState<string | null>(null);
  const [verifying, setVerifying] = useState<string | null>(null);

  useEffect(() => {
    getClaudeKeyStatus().then(setKeyStatus).catch(() => {});
    listCloudAccounts().then(setCloudAccounts).catch(() => {});
  }, []);

  const saveKey = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!keyInput.startsWith('sk-ant-')) {
      setKeyError('Key must start with sk-ant-');
      return;
    }
    setSavingKey(true);
    setKeyError(null);
    try {
      await saveClaudeKey(keyInput);
      setKeySaved(true);
      setKeyInput('');
      setKeyStatus({ configured: true, source: 'org_key' });
      setTimeout(() => setKeySaved(false), 3000);
    } catch (e: any) { setKeyError(e.message); }
    finally { setSavingKey(false); }
  };

  const loadSetupInfo = async () => {
    try {
      const info = await getCloudSetupInfo();
      setSetupInfo(info);
      setAwsStep(2);
    } catch (e: any) { setAwsError(e.message); }
  };

  const connectAws = async (e: React.FormEvent) => {
    e.preventDefault();
    setConnectingAws(true);
    setAwsError(null);
    try {
      await connectCloudRoleAccount({ display_name: displayName, role_arn: roleArn, region: awsRegion });
      const updated = await listCloudAccounts();
      setCloudAccounts(updated);
      setAwsStep(1);
      setRoleArn('');
      setDisplayName('');
    } catch (e: any) { setAwsError(e.message); }
    finally { setConnectingAws(false); }
  };

  const reVerify = async (id: string) => {
    setVerifying(id);
    try {
      const updated = await verifyCloudAccount(id);
      setCloudAccounts((prev) => prev.map((a) => a.id === id ? updated : a));
    } catch (e: any) { setAwsError(e.message); }
    finally { setVerifying(null); }
  };

  const trustPolicy = setupInfo ? JSON.stringify(setupInfo.trust_policy, null, 2) : '';

  return (
    <div className="space-y-6">
      {/* Claude API Key */}
      <div className="rounded-xl border p-5" style={{ background: 'var(--card)', borderColor: 'var(--border)' }}>
        <div className="flex items-start gap-3 mb-4">
          <div className="w-8 h-8 rounded-lg bg-indigo-500/15 border border-indigo-500/20
            flex items-center justify-center shrink-0">
            <Key className="w-4 h-4 text-indigo-400" />
          </div>
          <div>
            <p className="text-sm font-semibold text-slate-200">Claude API Key</p>
            <p className="text-xs text-slate-500 mt-0.5">Used for all AI generation within your org</p>
          </div>
          {keyStatus && (
            <div className={`ml-auto flex items-center gap-1.5 text-xs px-2.5 py-1 rounded-full border font-medium
              ${keyStatus.configured
                ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20'
                : 'bg-amber-500/10 text-amber-400 border-amber-500/20'}`}>
              <span className={`w-1.5 h-1.5 rounded-full ${keyStatus.configured ? 'bg-emerald-400' : 'bg-amber-400'}`} />
              {keyStatus.configured ? `Configured (${keyStatus.source === 'org_key' ? 'org key' : 'shared key'})` : 'Not configured'}
            </div>
          )}
        </div>

        <form onSubmit={saveKey} className="flex items-center gap-2">
          <input
            type="password" placeholder="sk-ant-api03-…" value={keyInput}
            onChange={(e) => setKeyInput(e.target.value)}
            className="flex-1 px-3 py-2 rounded-lg text-sm font-mono bg-white/[0.04] border
              text-slate-200 placeholder:text-slate-600 focus:outline-none
              focus:border-indigo-500/50 transition-colors"
            style={{ borderColor: 'var(--border)' }} />
          <button type="submit" disabled={savingKey || !keyInput}
            className="flex items-center gap-1.5 px-4 py-2 rounded-lg text-xs font-medium
              bg-indigo-500/20 text-indigo-300 border border-indigo-500/30
              hover:bg-indigo-500/30 transition-all disabled:opacity-50">
            {savingKey ? <Loader2 className="w-3.5 h-3.5 animate-spin" />
              : keySaved ? <Check className="w-3.5 h-3.5 text-emerald-400" />
              : null}
            {keySaved ? 'Saved!' : keyStatus?.configured ? 'Rotate key' : 'Save key'}
          </button>
        </form>
        {keyError && <p className="mt-2 text-xs text-rose-400">{keyError}</p>}
      </div>

      {/* AWS Cloud */}
      <div className="rounded-xl border p-5" style={{ background: 'var(--card)', borderColor: 'var(--border)' }}>
        <div className="flex items-start gap-3 mb-4">
          <div className="w-8 h-8 rounded-lg bg-amber-500/10 border border-amber-500/20
            flex items-center justify-center shrink-0">
            <Cloud className="w-4 h-4 text-amber-400" />
          </div>
          <div>
            <p className="text-sm font-semibold text-slate-200">AWS Cloud Account</p>
            <p className="text-xs text-slate-500 mt-0.5">Connect your AWS account for deployments</p>
          </div>
        </div>

        {cloudAccounts.length > 0 ? (
          <div className="space-y-2">
            {cloudAccounts.map((acct) => (
              <div key={acct.id} className="flex items-center gap-3 px-4 py-3 rounded-lg
                bg-white/[0.02] border" style={{ borderColor: 'var(--border)' }}>
                <span className={`w-2 h-2 rounded-full shrink-0
                  ${acct.status === 'verified' ? 'bg-emerald-400' : 'bg-amber-400'}`} />
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium text-slate-200 truncate">{acct.display_name}</p>
                  <p className="text-xs text-slate-500 font-mono truncate">{acct.role_arn ?? acct.external_id}</p>
                </div>
                <span className={`text-[10px] px-2 py-0.5 rounded-full font-medium border
                  ${acct.status === 'verified'
                    ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20'
                    : 'bg-amber-500/10 text-amber-400 border-amber-500/20'}`}>
                  {acct.status}
                </span>
                <button onClick={() => reVerify(acct.id)} disabled={verifying === acct.id}
                  className="p-1.5 rounded-lg text-slate-500 hover:text-slate-300
                    hover:bg-white/[0.04] transition-all disabled:opacity-50">
                  <RefreshCw className={`w-3.5 h-3.5 ${verifying === acct.id ? 'animate-spin' : ''}`} />
                </button>
              </div>
            ))}
            <button onClick={() => setAwsStep(1)}
              className="mt-2 text-xs text-indigo-400 hover:text-indigo-300 transition-colors">
              + Connect another account
            </button>
          </div>
        ) : (
          <div>
            {/* Step indicator */}
            <div className="flex items-center gap-2 mb-4">
              {[1, 2, 3].map((s) => (
                <div key={s} className="flex items-center gap-2">
                  <div className={`w-5 h-5 rounded-full flex items-center justify-center text-[10px] font-bold
                    border transition-all
                    ${awsStep >= s
                      ? 'bg-indigo-500/20 text-indigo-300 border-indigo-500/40'
                      : 'bg-white/[0.03] text-slate-600 border-white/[0.08]'}`}>
                    {s}
                  </div>
                  {s < 3 && <div className={`h-px w-6 ${awsStep > s ? 'bg-indigo-500/40' : 'bg-white/[0.08]'}`} />}
                </div>
              ))}
              <span className="ml-2 text-xs text-slate-500">
                {awsStep === 1 ? 'Get your External ID' : awsStep === 2 ? 'Create IAM role' : 'Connect'}
              </span>
            </div>

            {awsStep === 1 && (
              <div className="space-y-3">
                <p className="text-xs text-slate-400">
                  We&apos;ll generate a unique External ID for your org. You&apos;ll use it when creating the IAM trust policy in AWS.
                </p>
                <button onClick={loadSetupInfo}
                  className="flex items-center gap-2 px-4 py-2 rounded-lg text-xs font-medium
                    bg-indigo-500/20 text-indigo-300 border border-indigo-500/30
                    hover:bg-indigo-500/30 transition-all">
                  <ChevronRight className="w-3.5 h-3.5" />
                  Get setup info
                </button>
              </div>
            )}

            {awsStep === 2 && setupInfo && (
              <div className="space-y-3">
                <div className="p-3 rounded-lg bg-white/[0.02] border" style={{ borderColor: 'var(--border)' }}>
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-[10px] text-slate-500 font-medium uppercase tracking-wider">Loomaris Deployer ARN</span>
                    <CopyButton text={setupInfo.loomaris_deployer_arn} />
                  </div>
                  <code className="text-xs font-mono text-slate-300 break-all">{setupInfo.loomaris_deployer_arn}</code>
                </div>
                <div className="p-3 rounded-lg bg-white/[0.02] border" style={{ borderColor: 'var(--border)' }}>
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-[10px] text-slate-500 font-medium uppercase tracking-wider">Your External ID</span>
                    <CopyButton text={setupInfo.sts_external_id} />
                  </div>
                  <code className="text-xs font-mono text-slate-300">{setupInfo.sts_external_id}</code>
                </div>
                <div className="p-3 rounded-lg bg-white/[0.02] border" style={{ borderColor: 'var(--border)' }}>
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-[10px] text-slate-500 font-medium uppercase tracking-wider">Trust Policy JSON</span>
                    <CopyButton text={trustPolicy} />
                  </div>
                  <pre className="text-[10px] font-mono text-slate-400 overflow-x-auto whitespace-pre-wrap">{trustPolicy}</pre>
                </div>
                <p className="text-xs text-slate-500">
                  In AWS console → IAM → Roles → Create role → Another AWS account → paste the above trust policy, then add the <code className="text-slate-400">AdministratorAccess</code> policy.
                </p>
                <button onClick={() => setAwsStep(3)}
                  className="flex items-center gap-2 px-4 py-2 rounded-lg text-xs font-medium
                    bg-indigo-500/20 text-indigo-300 border border-indigo-500/30
                    hover:bg-indigo-500/30 transition-all">
                  <ChevronRight className="w-3.5 h-3.5" />
                  I've created the role
                </button>
              </div>
            )}

            {awsStep === 3 && (
              <form onSubmit={connectAws} className="space-y-3">
                <input required placeholder="My Production Account"
                  value={displayName} onChange={(e) => setDisplayName(e.target.value)}
                  className="w-full px-3 py-2 rounded-lg text-sm bg-white/[0.04] border
                    text-slate-200 placeholder:text-slate-600 focus:outline-none
                    focus:border-indigo-500/50 transition-colors"
                  style={{ borderColor: 'var(--border)' }} />
                <input required placeholder="arn:aws:iam::123456789012:role/LoomarisDeployer"
                  value={roleArn} onChange={(e) => setRoleArn(e.target.value)}
                  className="w-full px-3 py-2 rounded-lg text-sm font-mono bg-white/[0.04] border
                    text-slate-200 placeholder:text-slate-600 focus:outline-none
                    focus:border-indigo-500/50 transition-colors"
                  style={{ borderColor: 'var(--border)' }} />
                <select value={awsRegion} onChange={(e) => setAwsRegion(e.target.value)}
                  className="w-full px-3 py-2 rounded-lg text-sm bg-white/[0.04] border
                    text-slate-400 focus:outline-none focus:border-indigo-500/50 transition-colors"
                  style={{ borderColor: 'var(--border)' }}>
                  {['us-east-1','us-west-2','eu-west-1','eu-central-1','ap-south-1','ap-southeast-1','ap-northeast-1'].map(r => (
                    <option key={r} value={r}>{r}</option>
                  ))}
                </select>
                <button type="submit" disabled={connectingAws}
                  className="flex items-center gap-2 px-4 py-2 rounded-lg text-xs font-medium
                    bg-indigo-500/20 text-indigo-300 border border-indigo-500/30
                    hover:bg-indigo-500/30 transition-all disabled:opacity-50">
                  {connectingAws ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <CheckCircle2 className="w-3.5 h-3.5" />}
                  Connect & verify
                </button>
              </form>
            )}
            {awsError && <p className="mt-2 text-xs text-rose-400">{awsError}</p>}
          </div>
        )}
      </div>

      {/* GitHub placeholder */}
      <div className="rounded-xl border p-5 opacity-60" style={{ background: 'var(--card)', borderColor: 'var(--border)' }}>
        <div className="flex items-start gap-3">
          <div className="w-8 h-8 rounded-lg bg-white/5 border border-white/10
            flex items-center justify-center shrink-0">
            <Key className="w-4 h-4 text-slate-400" />
          </div>
          <div className="flex-1">
            <div className="flex items-center gap-2">
              <p className="text-sm font-semibold text-slate-300">GitHub Integration</p>
              <span className="text-[9px] px-1.5 py-0.5 rounded-full bg-slate-700 text-slate-400 border border-slate-600 font-medium uppercase tracking-wide">
                Coming soon
              </span>
            </div>
            <p className="text-xs text-slate-500 mt-1">
              Connect your org&apos;s GitHub to push generated code directly to your repositories.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}

// ── Organization Tab ───────────────────────────────────────────────────────────

function OrganizationTab({ me }: { me: Me }) {
  const [name, setName] = useState(me.org!.name);
  const [description, setDescription] = useState(me.org!.description ?? '');
  const [joinPolicy, setJoinPolicy] = useState(me.org!.join_policy);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const save = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    setError(null);
    try {
      await updateOrg(me.org!.id, { name, description, join_policy: joinPolicy });
      setSaved(true);
      setTimeout(() => setSaved(false), 3000);
    } catch (e: any) { setError(e.message); }
    finally { setSaving(false); }
  };

  const JOIN_POLICIES = [
    { value: 'open', label: 'Open', desc: 'Anyone can join without approval' },
    { value: 'approval_required', label: 'Approval required', desc: 'Admins must approve each request' },
    { value: 'invite_only', label: 'Invite only', desc: 'Members can only join via invite link' },
  ];

  return (
    <div className="space-y-6 max-w-lg">
      <form onSubmit={save} className="space-y-4">
        <div className="rounded-xl border p-5 space-y-4" style={{ background: 'var(--card)', borderColor: 'var(--border)' }}>
          <div>
            <label className="block text-xs font-medium text-slate-400 mb-1.5">Organization name</label>
            <input value={name} onChange={(e) => setName(e.target.value)} required
              className="w-full px-3 py-2 rounded-lg text-sm bg-white/[0.04] border
                text-slate-200 placeholder:text-slate-600 focus:outline-none
                focus:border-indigo-500/50 transition-colors"
              style={{ borderColor: 'var(--border)' }} />
          </div>
          <div>
            <label className="block text-xs font-medium text-slate-400 mb-1.5">Description</label>
            <textarea value={description} onChange={(e) => setDescription(e.target.value)} rows={3}
              placeholder="What does your org build?"
              className="w-full px-3 py-2 rounded-lg text-sm bg-white/[0.04] border resize-none
                text-slate-200 placeholder:text-slate-600 focus:outline-none
                focus:border-indigo-500/50 transition-colors"
              style={{ borderColor: 'var(--border)' }} />
          </div>
          <div>
            <label className="block text-xs font-medium text-slate-400 mb-2">Join policy</label>
            <div className="space-y-2">
              {JOIN_POLICIES.map((p) => (
                <label key={p.value}
                  className={`flex items-start gap-3 p-3 rounded-lg border cursor-pointer transition-all
                    ${joinPolicy === p.value
                      ? 'border-indigo-500/40 bg-indigo-500/5'
                      : 'border-white/[0.06] hover:border-white/10 bg-white/[0.02]'}`}>
                  <input type="radio" name="join_policy" value={p.value}
                    checked={joinPolicy === p.value} onChange={() => setJoinPolicy(p.value)}
                    className="mt-0.5 accent-indigo-500" />
                  <div>
                    <p className="text-xs font-medium text-slate-200">{p.label}</p>
                    <p className="text-xs text-slate-500 mt-0.5">{p.desc}</p>
                  </div>
                </label>
              ))}
            </div>
          </div>
        </div>

        {error && <p className="text-xs text-rose-400">{error}</p>}
        <button type="submit" disabled={saving}
          className="flex items-center gap-2 px-4 py-2 rounded-lg text-xs font-medium
            bg-indigo-500/20 text-indigo-300 border border-indigo-500/30
            hover:bg-indigo-500/30 transition-all disabled:opacity-50">
          {saving ? <Loader2 className="w-3.5 h-3.5 animate-spin" />
            : saved ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : null}
          {saved ? 'Saved!' : 'Save changes'}
        </button>
      </form>

      {/* Read-only info */}
      <div className="rounded-xl border p-5 space-y-3" style={{ background: 'var(--card)', borderColor: 'var(--border)' }}>
        <p className="text-xs font-semibold text-slate-500 uppercase tracking-wider">Details</p>
        {[
          { label: 'Slug', value: me.org!.slug },
          { label: 'Plan', value: me.org!.plan },
        ].map(({ label, value }) => (
          <div key={label} className="flex items-center justify-between">
            <span className="text-xs text-slate-500">{label}</span>
            <span className="text-xs font-mono text-slate-300">{value}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

// ── Page ───────────────────────────────────────────────────────────────────────

export default function OrgSettingsPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const tab = (searchParams.get('tab') ?? 'members') as TabId;

  const [me, setMe] = useState<Me | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    getMe()
      .then((data) => {
        if (data.role !== 'owner' && data.role !== 'admin') {
          router.replace('/chat');
          return;
        }
        setMe(data);
        setLoading(false);
      })
      .catch(() => router.replace('/login'));
  }, [router]);

  if (loading || !me?.org) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <Loader2 className="w-5 h-5 animate-spin text-slate-500" />
      </div>
    );
  }

  const setTab = (id: TabId) => router.push(`/org-settings?tab=${id}`, { scroll: false });

  return (
    <div className="flex-1 flex flex-col overflow-hidden">
      {/* Header */}
      <div className="px-8 pt-8 pb-0 border-b flex-shrink-0" style={{ borderColor: 'var(--border)' }}>
        <div className="flex items-center gap-3 mb-5">
          <div className="w-8 h-8 rounded-lg bg-indigo-500/15 border border-indigo-500/25
            flex items-center justify-center">
            <Settings2 className="w-4 h-4 text-indigo-400" />
          </div>
          <div>
            <h1 className="text-lg font-semibold text-white">{me.org.name}</h1>
            <p className="text-xs text-slate-500">Org Settings · {me.role}</p>
          </div>
          {me.user.is_superadmin && (
            <span className="ml-2 inline-flex items-center gap-1 text-[10px] px-2 py-0.5 rounded-full
              bg-indigo-500/15 border border-indigo-500/25 text-indigo-300 font-medium">
              <Shield className="w-2.5 h-2.5" /> Superadmin
            </span>
          )}
        </div>

        {/* Tabs */}
        <div className="flex gap-0">
          {TABS.map(({ id, label, icon: Icon }) => (
            <button key={id} onClick={() => setTab(id)}
              className={`flex items-center gap-2 px-4 py-2.5 text-xs font-medium border-b-2 transition-all
                ${tab === id
                  ? 'text-white border-indigo-400'
                  : 'text-slate-500 border-transparent hover:text-slate-300'}`}>
              <Icon className="w-3.5 h-3.5" />
              {label}
            </button>
          ))}
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto px-8 py-6">
        {tab === 'members' && <MembersTab orgId={me.org.id} />}
        {tab === 'integrations' && <IntegrationsTab orgId={me.org.id} />}
        {tab === 'organization' && <OrganizationTab me={me} />}
      </div>
    </div>
  );
}
