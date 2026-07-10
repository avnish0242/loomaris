'use client';

import { useEffect, useState } from 'react';
import { X, ChevronRight } from 'lucide-react';
import { getAppFiles, AppFile } from '@/lib/api';

interface Props {
  appId: string;
  open: boolean;
  onClose: () => void;
}

function getLanguage(path: string): string {
  const ext = path.split('.').pop()?.toLowerCase() ?? '';
  const map: Record<string, string> = {
    ts: 'typescript', tsx: 'typescript', js: 'javascript', jsx: 'javascript',
    py: 'python', json: 'json', md: 'markdown', html: 'html', css: 'css',
    sh: 'bash', yml: 'yaml', yaml: 'yaml', toml: 'toml', dockerfile: 'docker',
  };
  return map[ext] ?? 'text';
}

export default function CodeDrawer({ appId, open, onClose }: Props) {
  const [files, setFiles] = useState<AppFile[]>([]);
  const [activeFile, setActiveFile] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!open) return;
    setLoading(true);
    getAppFiles(appId)
      .then((data) => {
        setFiles(data.files);
        if (data.files.length > 0) setActiveFile(data.files[0].path);
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [open, appId]);

  if (!open) return null;

  const currentFile = files.find((f) => f.path === activeFile);

  return (
    <div className="fixed inset-0 z-50 flex flex-col" style={{ background: 'var(--bg)' }}>
      {/* Header */}
      <div className="flex items-center gap-3 px-4 py-3 border-b shrink-0"
        style={{ borderColor: 'var(--border)', background: 'var(--surface)' }}>
        <button onClick={onClose}
          className="p-1.5 rounded-lg text-slate-400 hover:text-slate-200 hover:bg-slate-800 transition-all">
          <X className="w-4 h-4" />
        </button>
        <span className="text-sm font-medium text-slate-300">Source Code</span>
        {activeFile && (
          <>
            <ChevronRight className="w-3.5 h-3.5 text-slate-600" />
            <span className="text-sm text-slate-400 font-mono">{activeFile}</span>
          </>
        )}
      </div>

      <div className="flex flex-1 overflow-hidden">
        {/* File tree */}
        <div className="w-56 shrink-0 border-r overflow-y-auto py-2"
          style={{ borderColor: 'var(--border)', background: 'var(--surface)' }}>
          {loading ? (
            <div className="px-4 py-3 text-xs text-slate-500">Loading files…</div>
          ) : files.length === 0 ? (
            <div className="px-4 py-3 text-xs text-slate-500">No files yet</div>
          ) : (
            files.map((f) => (
              <button
                key={f.path}
                onClick={() => setActiveFile(f.path)}
                className={`w-full text-left px-4 py-1.5 text-xs font-mono truncate transition-colors
                  ${activeFile === f.path
                    ? 'text-indigo-300 bg-indigo-500/10'
                    : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/50'}`}>
                {f.path}
              </button>
            ))
          )}
        </div>

        {/* Code view */}
        <div className="flex-1 overflow-auto">
          {currentFile ? (
            <pre className="px-6 py-4 text-xs font-mono text-slate-300 leading-relaxed min-h-full"
              style={{ tabSize: 2 }}>
              <code>{currentFile.content}</code>
            </pre>
          ) : (
            <div className="flex items-center justify-center h-full text-sm text-slate-500">
              Select a file
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
