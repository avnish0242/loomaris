'use client';

import { useState, useEffect } from 'react';
import { Cloud, X, Shield, CheckCircle2, AlertCircle, ChevronDown, Copy, ExternalLink } from 'lucide-react';
import { connectCloudRoleAccount, getCloudSetupInfo, type CloudAccount, type CloudSetupInfo } from '@/lib/api';

const AWS_REGIONS = [
  { value: 'us-east-1',      label: 'US East (N. Virginia)' },
  { value: 'us-east-2',      label: 'US East (Ohio)' },
  { value: 'us-west-1',      label: 'US West (N. California)' },
  { value: 'us-west-2',      label: 'US West (Oregon)' },
  { value: 'eu-west-1',      label: 'Europe (Ireland)' },
  { value: 'eu-west-2',      label: 'Europe (London)' },
  { value: 'eu-central-1',   label: 'Europe (Frankfurt)' },
  { value: 'ap-south-1',     label: 'Asia Pacific (Mumbai)' },
  { value: 'ap-southeast-1', label: 'Asia Pacific (Singapore)' },
  { value: 'ap-northeast-1', label: 'Asia Pacific (Tokyo)' },
];

interface Props {
  onConnected: (account: CloudAccount) => void;
  onDismiss: () => void;
}

type Step = 'setup' | 'connect' | 'done';

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <button onClick={() => { navigator.clipboard.writeText(text); setCopied(true); setTimeout(() => setCopied(false), 2000); }}
      className="flex items-center gap-1 px-2 py-1 rounded text-xs text-slate-400 hover:text-slate-200 hover:bg-slate-700 transition-all">
      {copied ? <CheckCircle2 className="w-3 h-3 text-emerald-400" /> : <Copy className="w-3 h-3" />}
      {copied ? 'Copied' : 'Copy'}
    </button>
  );
}

export default function CloudConnectModal({ onConnected, onDismiss }: Props) {
  const [step, setStep] = useState<Step>('setup');
  const [setupInfo, setSetupInfo] = useState<CloudSetupInfo | null>(null);
  const [setupLoading, setSetupLoading] = useState(true);

  const [displayName, setDisplayName] = useState('My AWS Account');
  const [roleArn, setRoleArn] = useState('');
  const [region, setRegion] = useState('us-east-1');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [connected, setConnected] = useState<CloudAccount | null>(null);

  useEffect(() => {
    getCloudSetupInfo()
      .then(setSetupInfo)
      .catch(() => {})
      .finally(() => setSetupLoading(false));
  }, []);

  useEffect(() => {
    const handler = (e: KeyboardEvent) => { if (e.key === 'Escape') onDismiss(); };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [onDismiss]);

  const roleArnValid = /^arn:aws:iam::\d{12}:role\/.+$/.test(roleArn.trim());
  const canConnect = displayName.trim().length > 0 && roleArnValid;

  const handleConnect = async () => {
    if (!canConnect) return;
    setLoading(true);
    setError(null);
    try {
      const account = await connectCloudRoleAccount({
        display_name: displayName.trim(),
        role_arn: roleArn.trim(),
        region,
      });
      setConnected(account);
      setStep('done');
      setTimeout(() => onConnected(account), 1800);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to connect account');
    } finally {
      setLoading(false);
    }
  };

  const trustPolicyJson = setupInfo
    ? JSON.stringify(setupInfo.trust_policy, null, 2)
    : '';

  const inputCls = `w-full px-3.5 py-2.5 rounded-xl text-sm text-slate-200
    placeholder:text-slate-600 border outline-none transition-all focus:ring-1 focus:ring-amber-500/50`;
  const inputStyle = { background: 'rgba(0,0,0,0.3)', borderColor: 'var(--border)' };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4"
      style={{ background: 'rgba(0,0,0,0.75)', backdropFilter: 'blur(8px)' }}>
      <div className="w-full max-w-lg rounded-2xl border shadow-2xl overflow-hidden"
        style={{ background: 'var(--card)', borderColor: 'var(--border)' }}>

        {/* Header */}
        <div className="flex items-start justify-between px-6 py-5 border-b"
          style={{ borderColor: 'var(--border)' }}>
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-xl flex items-center justify-center"
              style={{ background: 'rgba(245,158,11,0.15)', border: '1px solid rgba(245,158,11,0.3)' }}>
              <Cloud className="w-4.5 h-4.5 text-amber-400" />
            </div>
            <div>
              <h2 className="text-sm font-semibold text-white">Connect AWS Account</h2>
              <p className="text-xs text-slate-500 mt-0.5">Cross-account IAM role — no stored credentials</p>
            </div>
          </div>
          <button onClick={onDismiss}
            className="p-1.5 rounded-lg text-slate-600 hover:text-slate-400 hover:bg-white/5 transition-colors">
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Step tabs */}
        <div className="flex border-b" style={{ borderColor: 'var(--border)' }}>
          {(['setup', 'connect'] as const).map((s, i) => (
            <button key={s} onClick={() => step !== 'done' && setStep(s)}
              className={`flex-1 py-2.5 text-xs font-medium transition-colors ${
                step === s || (step === 'done' && s === 'connect')
                  ? 'text-amber-400 border-b-2 border-amber-400'
                  : 'text-slate-500 hover:text-slate-300'
              }`}>
              Step {i + 1}: {s === 'setup' ? 'Create IAM Role' : 'Paste Role ARN'}
            </button>
          ))}
        </div>

        <div className="px-6 py-5">
          {/* Step 1: Setup instructions */}
          {step === 'setup' && (
            <div className="space-y-4">
              <p className="text-xs text-slate-400 leading-relaxed">
                In your AWS console, create an IAM role that Loomaris can assume.
                This is more secure than access keys — no long-lived credentials are stored.
              </p>

              <div className="space-y-3">
                <div className="flex items-start gap-2">
                  <span className="w-5 h-5 rounded-full bg-amber-500/20 text-amber-400 text-[10px] font-bold flex items-center justify-center shrink-0 mt-0.5">1</span>
                  <div>
                    <p className="text-xs text-slate-300 mb-1">Go to <strong>IAM → Roles → Create Role</strong></p>
                    <a href="https://us-east-1.console.aws.amazon.com/iam/home#/roles/create"
                      target="_blank" rel="noreferrer"
                      className="flex items-center gap-1 text-xs text-amber-400/70 hover:text-amber-400">
                      Open AWS IAM Console <ExternalLink className="w-3 h-3" />
                    </a>
                  </div>
                </div>

                <div className="flex items-start gap-2">
                  <span className="w-5 h-5 rounded-full bg-amber-500/20 text-amber-400 text-[10px] font-bold flex items-center justify-center shrink-0 mt-0.5">2</span>
                  <div className="flex-1">
                    <p className="text-xs text-slate-300 mb-2">Set the <strong>trust policy</strong> to allow Loomaris to assume the role:</p>
                    {setupLoading ? (
                      <div className="text-xs text-slate-500 animate-pulse">Loading trust policy…</div>
                    ) : setupInfo ? (
                      <div className="relative rounded-lg overflow-hidden"
                        style={{ background: 'rgba(0,0,0,0.4)', border: '1px solid rgba(255,255,255,0.07)' }}>
                        <div className="flex items-center justify-between px-3 py-2 border-b"
                          style={{ borderColor: 'rgba(255,255,255,0.07)' }}>
                          <span className="text-xs text-slate-500 font-mono">Trust Policy JSON</span>
                          <CopyButton text={trustPolicyJson} />
                        </div>
                        <pre className="px-3 py-2 text-[11px] font-mono text-slate-300 overflow-x-auto max-h-36">
                          {trustPolicyJson}
                        </pre>
                      </div>
                    ) : (
                      <p className="text-xs text-rose-400">Could not load trust policy — check backend connection</p>
                    )}
                  </div>
                </div>

                <div className="flex items-start gap-2">
                  <span className="w-5 h-5 rounded-full bg-amber-500/20 text-amber-400 text-[10px] font-bold flex items-center justify-center shrink-0 mt-0.5">3</span>
                  <p className="text-xs text-slate-300">
                    Attach the <strong>minimum required permissions</strong> policy (shown on the next step) and name the role <code className="text-amber-400/80">LoomarisDeployRole</code>.
                  </p>
                </div>
              </div>

              <button onClick={() => setStep('connect')}
                className="w-full py-2.5 rounded-xl text-sm font-medium text-amber-300 border border-amber-500/30 hover:bg-amber-500/10 transition-all mt-2">
                I've created the role — Next →
              </button>
            </div>
          )}

          {/* Step 2: Paste role ARN */}
          {(step === 'connect' || step === 'done') && (
            <div className="space-y-4">
              {step === 'done' && connected ? (
                <div className="rounded-xl border p-4"
                  style={{ background: 'rgba(52,211,153,0.06)', borderColor: 'rgba(52,211,153,0.2)' }}>
                  <div className="flex items-center gap-2 mb-1">
                    <CheckCircle2 className="w-4 h-4 text-emerald-400" />
                    <span className="text-sm font-medium text-emerald-300">Connected!</span>
                  </div>
                  <p className="text-xs text-slate-400">
                    AWS Account ID: <span className="font-mono text-slate-300">{connected.external_id}</span>
                  </p>
                </div>
              ) : (
                <>
                  <div className="space-y-3">
                    <div>
                      <label className="block text-xs font-medium text-slate-400 mb-1.5">Display name</label>
                      <input type="text" value={displayName} autoFocus
                        onChange={e => { setDisplayName(e.target.value); setError(null); }}
                        placeholder="My AWS Account" className={inputCls} style={inputStyle} />
                    </div>

                    <div>
                      <label className="block text-xs font-medium text-slate-400 mb-1.5">Role ARN</label>
                      <input type="text" value={roleArn}
                        onChange={e => { setRoleArn(e.target.value.trim()); setError(null); }}
                        onKeyDown={e => { if (e.key === 'Enter') handleConnect(); }}
                        placeholder="arn:aws:iam::123456789012:role/LoomarisDeployRole"
                        className={`${inputCls} font-mono text-xs`}
                        style={{
                          background: 'rgba(0,0,0,0.3)',
                          borderColor: roleArn.length > 10 && !roleArnValid
                            ? 'rgba(251,113,133,0.4)' : 'var(--border)',
                        }} />
                      {roleArn.length > 10 && !roleArnValid && (
                        <p className="mt-1 text-xs text-rose-400/80">Must be in format arn:aws:iam::&lt;account_id&gt;:role/&lt;name&gt;</p>
                      )}
                    </div>

                    <div>
                      <label className="block text-xs font-medium text-slate-400 mb-1.5">Default region</label>
                      <div className="relative">
                        <select value={region} onChange={e => setRegion(e.target.value)}
                          className="w-full appearance-none px-3.5 py-2.5 rounded-xl text-sm text-slate-200
                            border outline-none transition-all focus:ring-1 focus:ring-amber-500/50 pr-9"
                          style={{ background: 'rgba(0,0,0,0.3)', borderColor: 'var(--border)' }}>
                          {AWS_REGIONS.map(r => (
                            <option key={r.value} value={r.value}>{r.label}</option>
                          ))}
                        </select>
                        <ChevronDown className="absolute right-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-slate-500 pointer-events-none" />
                      </div>
                    </div>
                  </div>

                  {/* Trust signals */}
                  <div className="space-y-1.5 pt-1">
                    {[
                      { icon: Shield,       text: 'Validated via STS AssumeRole — no stored credentials' },
                      { icon: CheckCircle2, text: 'Temporary 1-hour session tokens only — auto-expire' },
                      { icon: Cloud,        text: 'You can revoke access instantly in your AWS console' },
                    ].map(({ icon: Icon, text }) => (
                      <div key={text} className="flex items-center gap-2 text-xs text-slate-500">
                        <Icon className="w-3 h-3 text-emerald-400 shrink-0" />
                        {text}
                      </div>
                    ))}
                  </div>

                  {error && (
                    <div className="flex items-start gap-1.5 px-3 py-2.5 rounded-xl text-xs text-rose-300"
                      style={{ background: 'rgba(251,113,133,0.08)', border: '1px solid rgba(251,113,133,0.2)' }}>
                      <AlertCircle className="w-3.5 h-3.5 shrink-0 mt-0.5 text-rose-400" />
                      <span className="whitespace-pre-line">{error}</span>
                    </div>
                  )}

                  <div className="flex gap-2.5">
                    <button onClick={() => setStep('setup')}
                      className="px-3 py-2.5 rounded-xl text-xs text-slate-500 hover:text-slate-300 hover:bg-white/5 border border-transparent transition-all">
                      ← Back
                    </button>
                    <button onClick={handleConnect} disabled={!canConnect || loading}
                      className="flex-1 py-2.5 rounded-xl text-sm font-medium transition-all disabled:opacity-40 disabled:cursor-not-allowed"
                      style={{
                        background: 'rgba(245,158,11,0.15)',
                        border: '1px solid rgba(245,158,11,0.3)',
                        color: '#f59e0b',
                      }}>
                      {loading ? 'Verifying via STS…' : 'Connect Account'}
                    </button>
                  </div>
                </>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
