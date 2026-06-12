'use client';

import { useState, useEffect } from 'react';
import { Cloud, X, Shield, CheckCircle2, AlertCircle, ChevronDown } from 'lucide-react';
import { connectCloudAccount, type CloudAccount } from '@/lib/api';

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

export default function CloudConnectModal({ onConnected, onDismiss }: Props) {
  const [displayName, setDisplayName] = useState('My AWS Account');
  const [accessKeyId, setAccessKeyId] = useState('');
  const [secretKey, setSecretKey] = useState('');
  const [region, setRegion] = useState('us-east-1');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [connected, setConnected] = useState<CloudAccount | null>(null);

  const accessKeyValid = /^(AKIA|ASIA)[A-Z0-9]{16}$/.test(accessKeyId);
  const canSubmit = displayName.trim().length > 0 && accessKeyValid && secretKey.length > 0;

  const handleConnect = async () => {
    if (!canSubmit) return;
    setLoading(true);
    setError(null);
    try {
      const account = await connectCloudAccount({
        display_name: displayName.trim(),
        access_key_id: accessKeyId.trim(),
        secret_access_key: secretKey,
        region,
      });
      setConnected(account);
      setTimeout(() => onConnected(account), 1800);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to connect account');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    const handler = (e: KeyboardEvent) => { if (e.key === 'Escape') onDismiss(); };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [onDismiss]);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4"
      style={{ background: 'rgba(0,0,0,0.75)', backdropFilter: 'blur(8px)' }}>
      <div className="w-full max-w-md rounded-2xl border p-6 shadow-2xl"
        style={{ background: 'var(--card)', borderColor: 'var(--border)' }}>

        {/* Header */}
        <div className="flex items-start justify-between mb-5">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-amber-500/15 border border-amber-500/25
              flex items-center justify-center">
              <Cloud className="w-5 h-5 text-amber-400" />
            </div>
            <div>
              <h2 className="text-base font-semibold text-white">Connect AWS Account</h2>
              <p className="text-xs text-slate-500 mt-0.5">Required to deploy apps to your cloud</p>
            </div>
          </div>
          <button onClick={onDismiss}
            className="p-1.5 rounded-lg text-slate-600 hover:text-slate-400 hover:bg-white/5 transition-colors">
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Trust signals */}
        <div className="space-y-2 mb-5">
          {[
            { icon: Shield,       text: 'Credentials validated live via AWS STS' },
            { icon: CheckCircle2, text: 'Stored encrypted, never logged or exposed' },
            { icon: Cloud,        text: 'Used only when you trigger a deployment' },
          ].map(({ icon: Icon, text }) => (
            <div key={text} className="flex items-center gap-2.5 text-xs text-slate-400">
              <Icon className="w-3.5 h-3.5 text-emerald-400 shrink-0" />
              {text}
            </div>
          ))}
        </div>

        {connected ? (
          /* Success state */
          <div className="rounded-xl border p-4 mb-4"
            style={{ background: 'rgba(52,211,153,0.06)', borderColor: 'rgba(52,211,153,0.2)' }}>
            <div className="flex items-center gap-2 mb-2">
              <CheckCircle2 className="w-4 h-4 text-emerald-400" />
              <span className="text-sm font-medium text-emerald-300">Connected!</span>
            </div>
            <p className="text-xs text-slate-400">
              Account ID: <span className="font-mono text-slate-300">{connected.external_id}</span>
            </p>
            {connected.arn && (
              <p className="text-xs text-slate-500 mt-0.5 font-mono truncate">{connected.arn}</p>
            )}
          </div>
        ) : (
          /* Form */
          <div className="space-y-3 mb-4">
            <div>
              <label className="block text-xs font-medium text-slate-400 mb-1.5">Display name</label>
              <input
                type="text"
                value={displayName}
                onChange={(e) => { setDisplayName(e.target.value); setError(null); }}
                placeholder="My AWS Account"
                className="w-full px-3.5 py-2.5 rounded-xl text-sm text-slate-200
                  placeholder:text-slate-600 border outline-none transition-all
                  focus:ring-1 focus:ring-amber-500/50"
                style={{ background: 'rgba(0,0,0,0.3)', borderColor: 'var(--border)' }}
              />
            </div>

            <div>
              <label className="block text-xs font-medium text-slate-400 mb-1.5">AWS Access Key ID</label>
              <input
                type="text"
                value={accessKeyId}
                onChange={(e) => { setAccessKeyId(e.target.value.trim()); setError(null); }}
                placeholder="AKIAIOSFODNN7EXAMPLE"
                autoFocus
                className="w-full px-3.5 py-2.5 rounded-xl text-sm font-mono text-slate-200
                  placeholder:text-slate-600 border outline-none transition-all
                  focus:ring-1 focus:ring-amber-500/50"
                style={{
                  background: 'rgba(0,0,0,0.3)',
                  borderColor: accessKeyId.length > 4 && !accessKeyValid
                    ? 'rgba(251,113,133,0.4)' : 'var(--border)',
                }}
              />
              {accessKeyId.length > 4 && !accessKeyValid && (
                <p className="mt-1 text-xs text-amber-500/80">Should start with AKIA or ASIA and be 20 chars</p>
              )}
            </div>

            <div>
              <label className="block text-xs font-medium text-slate-400 mb-1.5">AWS Secret Access Key</label>
              <input
                type="password"
                value={secretKey}
                onChange={(e) => { setSecretKey(e.target.value); setError(null); }}
                onKeyDown={(e) => { if (e.key === 'Enter') handleConnect(); }}
                placeholder="wJalrXUtnFEMI/K7MDENG/bPxRfiCY..."
                className="w-full px-3.5 py-2.5 rounded-xl text-sm font-mono text-slate-200
                  placeholder:text-slate-600 border outline-none transition-all
                  focus:ring-1 focus:ring-amber-500/50"
                style={{ background: 'rgba(0,0,0,0.3)', borderColor: 'var(--border)' }}
              />
            </div>

            <div>
              <label className="block text-xs font-medium text-slate-400 mb-1.5">Default region</label>
              <div className="relative">
                <select
                  value={region}
                  onChange={(e) => setRegion(e.target.value)}
                  className="w-full appearance-none px-3.5 py-2.5 rounded-xl text-sm text-slate-200
                    border outline-none transition-all focus:ring-1 focus:ring-amber-500/50 pr-9"
                  style={{ background: 'rgba(0,0,0,0.3)', borderColor: 'var(--border)' }}>
                  {AWS_REGIONS.map((r) => (
                    <option key={r.value} value={r.value}>{r.label}</option>
                  ))}
                </select>
                <ChevronDown className="absolute right-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-slate-500 pointer-events-none" />
              </div>
            </div>

            {error && (
              <p className="flex items-start gap-1.5 text-xs text-rose-400 pt-1">
                <AlertCircle className="w-3.5 h-3.5 shrink-0 mt-0.5" />
                {error}
              </p>
            )}
          </div>
        )}

        {/* Actions */}
        <div className="flex gap-2.5">
          <button onClick={handleConnect} disabled={!canSubmit || loading || !!connected}
            className="flex-1 py-2.5 px-4 rounded-xl text-sm font-medium transition-all
              disabled:opacity-40 disabled:cursor-not-allowed"
            style={{
              background: connected ? 'rgba(52,211,153,0.15)' : 'rgba(245,158,11,0.15)',
              border: `1px solid ${connected ? 'rgba(52,211,153,0.3)' : 'rgba(245,158,11,0.3)'}`,
              color: connected ? '#34d399' : '#fbbf24',
            }}>
            {connected ? '✓ Connected!' : loading ? 'Validating via STS…' : 'Connect Account'}
          </button>
          <button onClick={onDismiss}
            className="px-4 py-2.5 rounded-xl text-sm font-medium text-slate-500
              hover:text-slate-300 hover:bg-white/5 transition-colors border border-transparent">
            Skip for now
          </button>
        </div>

        <p className="mt-4 text-center text-xs text-slate-600">
          Need an IAM user?{' '}
          <a href="https://docs.aws.amazon.com/IAM/latest/UserGuide/id_users_create.html"
            target="_blank" rel="noopener noreferrer"
            className="text-amber-500/70 hover:text-amber-400">
            AWS IAM docs →
          </a>
        </p>
      </div>
    </div>
  );
}
