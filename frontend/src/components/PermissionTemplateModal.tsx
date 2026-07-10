'use client';

import { useState } from 'react';
import { X, Copy, CheckCircle2, ExternalLink, Shield } from 'lucide-react';
import { getPermissionPolicy, APP_TYPE_LABELS, type AppType } from '@/lib/permission-templates';

interface Props {
  appType: string;
  roleArn: string | null;
  open: boolean;
  onClose: () => void;
}

function CopyButton({ text, label = 'Copy' }: { text: string; label?: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <button
      onClick={() => { navigator.clipboard.writeText(text); setCopied(true); setTimeout(() => setCopied(false), 2000); }}
      className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-xs font-medium transition-all"
      style={{ background: 'rgba(255,255,255,0.06)', border: '1px solid rgba(255,255,255,0.1)', color: copied ? '#34d399' : '#94a3b8' }}>
      {copied ? <CheckCircle2 className="w-3 h-3" /> : <Copy className="w-3 h-3" />}
      {copied ? 'Copied!' : label}
    </button>
  );
}

export default function PermissionTemplateModal({ appType, roleArn, open, onClose }: Props) {
  if (!open) return null;

  const normalizedType: AppType =
    appType === 'container' ? 'container' : appType === 'lambda' ? 'lambda' : 'static';
  const policy = getPermissionPolicy(normalizedType);
  const policyJson = JSON.stringify(policy, null, 2);
  const label = APP_TYPE_LABELS[normalizedType];

  // Deep-link to the IAM role's permission tab (works if roleArn is arn:aws:iam::123:role/Name)
  const iamConsoleUrl = roleArn
    ? `https://us-east-1.console.aws.amazon.com/iam/home#/roles/${roleArn.split('/').pop()}`
    : 'https://us-east-1.console.aws.amazon.com/iam/home#/roles';

  return (
    <div
      className="fixed inset-0 z-[60] flex items-center justify-center p-4"
      style={{ background: 'rgba(0,0,0,0.75)', backdropFilter: 'blur(6px)' }}
      onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}>

      <div className="w-full max-w-lg rounded-2xl border shadow-2xl overflow-hidden"
        style={{ background: 'var(--card)', borderColor: 'var(--border)' }}>

        {/* Header */}
        <div className="flex items-start justify-between px-5 py-4 border-b"
          style={{ borderColor: 'var(--border)' }}>
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-lg flex items-center justify-center"
              style={{ background: 'rgba(99,102,241,0.15)', border: '1px solid rgba(99,102,241,0.3)' }}>
              <Shield className="w-4 h-4 text-indigo-400" />
            </div>
            <div>
              <h2 className="text-sm font-semibold text-white">Required IAM Permissions</h2>
              <p className="text-xs text-slate-500 mt-0.5">{label}</p>
            </div>
          </div>
          <button onClick={onClose}
            className="p-1.5 rounded-lg text-slate-600 hover:text-slate-400 hover:bg-white/5 transition-colors">
            <X className="w-4 h-4" />
          </button>
        </div>

        <div className="px-5 py-4 space-y-4">
          <p className="text-xs text-slate-400 leading-relaxed">
            Attach this policy to your <code className="text-indigo-300/80">LoomarisDeployRole</code>.
            It grants the minimum permissions needed to deploy a <strong className="text-slate-300">{normalizedType}</strong> app.
          </p>

          {/* Policy JSON */}
          <div className="rounded-xl overflow-hidden"
            style={{ background: 'rgba(0,0,0,0.4)', border: '1px solid rgba(255,255,255,0.07)' }}>
            <div className="flex items-center justify-between px-3 py-2 border-b"
              style={{ borderColor: 'rgba(255,255,255,0.07)' }}>
              <span className="text-xs text-slate-500 font-mono">Permission Policy JSON</span>
              <CopyButton text={policyJson} label="Copy Policy" />
            </div>
            <pre className="px-3 py-3 text-[11px] font-mono text-slate-300 overflow-x-auto max-h-64 leading-relaxed">
              {policyJson}
            </pre>
          </div>

          {/* Instructions */}
          <div className="space-y-2">
            <p className="text-xs text-slate-400 font-medium">To attach this policy:</p>
            <ol className="space-y-1.5 text-xs text-slate-400">
              <li className="flex gap-2">
                <span className="w-4 h-4 rounded-full bg-indigo-500/20 text-indigo-400 text-[10px] font-bold flex items-center justify-center shrink-0 mt-0.5">1</span>
                Open your AWS IAM role (the <code className="text-slate-300">LoomarisDeployRole</code> you created)
              </li>
              <li className="flex gap-2">
                <span className="w-4 h-4 rounded-full bg-indigo-500/20 text-indigo-400 text-[10px] font-bold flex items-center justify-center shrink-0 mt-0.5">2</span>
                Go to <strong className="text-slate-300">Permissions → Add permissions → Create inline policy</strong>
              </li>
              <li className="flex gap-2">
                <span className="w-4 h-4 rounded-full bg-indigo-500/20 text-indigo-400 text-[10px] font-bold flex items-center justify-center shrink-0 mt-0.5">3</span>
                Switch to the <strong className="text-slate-300">JSON</strong> editor and paste the policy above
              </li>
            </ol>
          </div>

          {/* Actions */}
          <div className="flex items-center gap-2 pt-1">
            <a href={iamConsoleUrl} target="_blank" rel="noreferrer"
              className="flex items-center gap-1.5 px-3 py-2 rounded-xl text-xs font-medium text-indigo-300 transition-all"
              style={{ background: 'rgba(99,102,241,0.1)', border: '1px solid rgba(99,102,241,0.25)' }}>
              <ExternalLink className="w-3.5 h-3.5" />
              Open IAM Role
            </a>
            <button onClick={onClose}
              className="flex-1 py-2 rounded-xl text-xs text-slate-500 hover:text-slate-300 transition-colors">
              Close
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
