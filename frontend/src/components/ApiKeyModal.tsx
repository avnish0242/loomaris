'use client';

import { useState, useEffect } from 'react';
import { Key, X, ExternalLink, Shield, CheckCircle2, AlertCircle } from 'lucide-react';
import { saveClaudeKey } from '@/lib/api';

interface Props {
  onSaved: () => void;
  onDismiss: () => void;
}

export default function ApiKeyModal({ onSaved, onDismiss }: Props) {
  const [key, setKey] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  const valid = key.startsWith('sk-ant-') && key.length > 20;

  const handleSave = async () => {
    if (!valid) return;
    setLoading(true);
    setError(null);
    try {
      await saveClaudeKey(key);
      setSaved(true);
      setTimeout(onSaved, 1200);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to save key');
    } finally {
      setLoading(false);
    }
  };

  // Trap focus: close on Escape
  useEffect(() => {
    const handler = (e: KeyboardEvent) => { if (e.key === 'Escape') onDismiss(); };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [onDismiss]);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4"
      style={{ background: 'rgba(0,0,0,0.7)', backdropFilter: 'blur(8px)' }}>
      <div className="w-full max-w-md rounded-2xl border p-6 shadow-2xl"
        style={{ background: 'var(--card)', borderColor: 'var(--border)' }}>

        {/* Header */}
        <div className="flex items-start justify-between mb-5">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-indigo-500/15 border border-indigo-500/25
              flex items-center justify-center">
              <Key className="w-5 h-5 text-indigo-400" />
            </div>
            <div>
              <h2 className="text-base font-semibold text-white">Connect Claude API</h2>
              <p className="text-xs text-slate-500 mt-0.5">Required to generate and deploy apps</p>
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
            { icon: Shield, text: 'Encrypted at rest with Fernet symmetric encryption' },
            { icon: CheckCircle2, text: 'Never stored in plaintext, never committed to git' },
            { icon: Key, text: 'Used only on your behalf when you send a message' },
          ].map(({ icon: Icon, text }) => (
            <div key={text} className="flex items-center gap-2.5 text-xs text-slate-400">
              <Icon className="w-3.5 h-3.5 text-emerald-400 shrink-0" />
              {text}
            </div>
          ))}
        </div>

        {/* Input */}
        <div className="mb-4">
          <label className="block text-xs font-medium text-slate-400 mb-1.5">
            Anthropic API Key
          </label>
          <input
            type="password"
            value={key}
            onChange={(e) => { setKey(e.target.value); setError(null); }}
            onKeyDown={(e) => { if (e.key === 'Enter') handleSave(); }}
            placeholder="sk-ant-api03-..."
            autoFocus
            className="w-full px-3.5 py-2.5 rounded-xl text-sm font-mono text-slate-200
              placeholder:text-slate-600 border outline-none transition-all
              focus:ring-1 focus:ring-indigo-500/50"
            style={{
              background: 'rgba(0,0,0,0.3)',
              borderColor: error ? 'rgba(251,113,133,0.4)' : 'var(--border)',
            }}
          />
          {error && (
            <p className="mt-1.5 flex items-center gap-1.5 text-xs text-rose-400">
              <AlertCircle className="w-3.5 h-3.5 shrink-0" />
              {error}
            </p>
          )}
          {!valid && key.length > 3 && !key.startsWith('sk-ant-') && (
            <p className="mt-1.5 text-xs text-amber-500/80">Key should start with sk-ant-</p>
          )}
        </div>

        {/* Actions */}
        <div className="flex gap-2.5">
          <button onClick={handleSave} disabled={!valid || loading || saved}
            className="flex-1 py-2.5 px-4 rounded-xl text-sm font-medium transition-all
              disabled:opacity-40 disabled:cursor-not-allowed"
            style={{
              background: saved ? 'rgba(52,211,153,0.15)' : 'rgba(99,102,241,0.2)',
              border: `1px solid ${saved ? 'rgba(52,211,153,0.3)' : 'rgba(99,102,241,0.3)'}`,
              color: saved ? '#34d399' : '#a5b4fc',
            }}>
            {saved ? '✓ Saved!' : loading ? 'Saving…' : 'Save API Key'}
          </button>
          <button onClick={onDismiss}
            className="px-4 py-2.5 rounded-xl text-sm font-medium text-slate-500
              hover:text-slate-300 hover:bg-white/5 transition-colors border border-transparent">
            Skip for now
          </button>
        </div>

        {/* Get key link */}
        <p className="mt-4 text-center text-xs text-slate-600">
          Don&apos;t have a key?{' '}
          <a href="https://console.anthropic.com/settings/keys" target="_blank" rel="noopener noreferrer"
            className="text-indigo-400 hover:text-indigo-300 inline-flex items-center gap-0.5">
            Get one from Anthropic Console
            <ExternalLink className="w-3 h-3" />
          </a>
        </p>
      </div>
    </div>
  );
}
