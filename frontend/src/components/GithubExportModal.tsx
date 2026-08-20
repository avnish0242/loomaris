'use client';

import { useEffect, useState } from 'react';
import { X, GitFork, Loader2, ExternalLink, CheckCircle2 } from 'lucide-react';
import { exportToGithub } from '@/lib/api';

interface Props {
  appId: string;
  appSlug: string;
  open: boolean;
  onClose: () => void;
}

export default function GithubExportModal({ appId, appSlug, open, onClose }: Props) {
  const [repoName, setRepoName] = useState(appSlug);
  const [isPrivate, setIsPrivate] = useState(true);
  const [pushing, setPushing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [repoUrl, setRepoUrl] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    setRepoName(appSlug);
    setIsPrivate(true);
    setPushing(false);
    setError(null);
    setRepoUrl(null);
  }, [open, appSlug]);

  if (!open) return null;

  const push = async (e: React.FormEvent) => {
    e.preventDefault();
    setPushing(true);
    setError(null);
    try {
      const res = await exportToGithub(appId, { repo_name: repoName, private: isPrivate });
      setRepoUrl(res.repo_url);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Export failed');
    } finally {
      setPushing(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4"
      style={{ background: 'rgba(0,0,0,0.7)' }}
      onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div className="w-full max-w-md rounded-2xl shadow-2xl overflow-hidden flex flex-col"
        style={{ background: 'var(--surface)', border: '1px solid var(--border)' }}>

        <div className="flex items-center justify-between px-5 py-4 border-b" style={{ borderColor: 'var(--border)' }}>
          <h2 className="text-sm font-semibold text-slate-200 flex items-center gap-2">
            <GitFork className="w-4 h-4" />
            {repoUrl ? 'Pushed!' : 'Push to GitHub'}
          </h2>
          <button onClick={onClose}
            className="p-1.5 rounded-lg text-slate-400 hover:text-slate-200 hover:bg-slate-800 transition-all">
            <X className="w-4 h-4" />
          </button>
        </div>

        {repoUrl ? (
          <div className="p-5 flex flex-col items-center gap-4 text-center">
            <div className="w-12 h-12 rounded-full bg-emerald-500/10 flex items-center justify-center">
              <CheckCircle2 className="w-6 h-6 text-emerald-400" />
            </div>
            <p className="text-xs text-slate-400 font-mono break-all">{repoUrl}</p>
            <a href={repoUrl} target="_blank" rel="noreferrer"
              className="flex items-center gap-1.5 px-3 py-2 rounded-lg text-xs font-medium text-emerald-300 border border-emerald-500/30 hover:border-emerald-500/60 transition-all">
              <ExternalLink className="w-3.5 h-3.5" />
              Open on GitHub
            </a>
          </div>
        ) : (
          <form onSubmit={push} className="p-5 flex flex-col gap-3">
            <p className="text-xs text-slate-400">
              Pushes your app&apos;s real commit history — every generation turn is a real commit — to a repo on your connected GitHub account.
            </p>
            <input required value={repoName} onChange={(e) => setRepoName(e.target.value)}
              placeholder="repo-name"
              className="w-full px-3 py-2 rounded-lg text-sm font-mono bg-white/[0.04] border
                text-slate-200 placeholder:text-slate-600 focus:outline-none
                focus:border-indigo-500/50 transition-colors"
              style={{ borderColor: 'var(--border)' }} />
            <label className="flex items-center gap-2 text-xs text-slate-400 cursor-pointer">
              <input type="checkbox" checked={isPrivate} onChange={(e) => setIsPrivate(e.target.checked)} />
              Private repository
            </label>
            <button type="submit" disabled={pushing}
              className="mt-1 flex items-center justify-center gap-2 w-full py-2.5 rounded-xl text-sm font-medium
                bg-indigo-600 text-white hover:bg-indigo-500 disabled:opacity-40 disabled:cursor-not-allowed transition-colors">
              {pushing ? <Loader2 className="w-4 h-4 animate-spin" /> : <GitFork className="w-4 h-4" />}
              {pushing ? 'Pushing…' : 'Push'}
            </button>
            {error && <p className="text-xs text-rose-400">{error}</p>}
          </form>
        )}
      </div>
    </div>
  );
}
