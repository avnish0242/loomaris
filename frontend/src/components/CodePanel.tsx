'use client';

import { useState, useMemo } from 'react';
import { Copy, Check, Code2, FileCode, ChevronRight, Download } from 'lucide-react';
import { downloadArchive } from '@/lib/api';

interface CodeFile {
  path: string;
  content: string;
  lang: string;
}

const EXT_LANG: Record<string, string> = {
  py: 'Python', ts: 'TypeScript', tsx: 'TypeScript React', js: 'JavaScript',
  jsx: 'JavaScript React', json: 'JSON', yaml: 'YAML', yml: 'YAML',
  md: 'Markdown', css: 'CSS', html: 'HTML', sh: 'Shell', bash: 'Shell',
  dockerfile: 'Dockerfile', toml: 'TOML', sql: 'SQL', go: 'Go',
  rs: 'Rust', txt: 'Text',
};

const EXT_COLOR: Record<string, string> = {
  py: '#3b82f6', ts: '#0ea5e9', tsx: '#06b6d4', js: '#eab308',
  jsx: '#f59e0b', json: '#10b981', yaml: '#8b5cf6', yml: '#8b5cf6',
  md: '#94a3b8', css: '#ec4899', html: '#f97316', sh: '#22d3ee',
  bash: '#22d3ee', dockerfile: '#2563eb', toml: '#a78bfa', sql: '#34d399',
};

function extOf(path: string): string {
  const parts = path.split('.');
  return parts.length > 1 ? parts.pop()!.toLowerCase() : path.toLowerCase();
}

function parseFiles(content: string): CodeFile[] {
  const files: CodeFile[] = [];
  const re = /```file:([^\n]+)\n([\s\S]*?)```/g;
  let match;
  while ((match = re.exec(content)) !== null) {
    const path = match[1].trim();
    const ext = extOf(path);
    files.push({ path, content: match[2], lang: EXT_LANG[ext] ?? ext.toUpperCase() });
  }
  return files;
}

function FileTab({ file, active, onClick }: { file: CodeFile; active: boolean; onClick: () => void }) {
  const ext = extOf(file.path);
  const color = EXT_COLOR[ext] ?? '#818cf8';
  const name = file.path.split('/').pop() ?? file.path;

  return (
    <button onClick={onClick}
      className={`flex items-center gap-2 px-4 py-2.5 text-xs font-mono whitespace-nowrap
        border-b-2 transition-all shrink-0
        ${active
          ? 'text-white border-indigo-400'
          : 'text-slate-500 hover:text-slate-300 border-transparent hover:border-slate-600'
        }`}>
      <div className="w-2 h-2 rounded-sm shrink-0" style={{ background: color }} />
      {name}
    </button>
  );
}

function CopyBtn({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  const copy = () => {
    navigator.clipboard.writeText(text).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  };
  return (
    <button onClick={copy}
      className="flex items-center gap-1.5 text-xs text-slate-500 hover:text-slate-200
        transition-colors px-3 py-1.5 rounded-lg hover:bg-white/[0.05] border border-transparent
        hover:border-white/[0.08]">
      {copied ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5" />}
      {copied ? 'Copied' : 'Copy'}
    </button>
  );
}

interface Props {
  /** Latest complete assistant message content (to parse file blocks from) */
  latestContent: string;
  streaming: boolean;
  appId?: string;
  appSlug?: string;
}

export default function CodePanel({ latestContent, streaming, appId, appSlug }: Props) {
  const [activeIdx, setActiveIdx] = useState(0);

  const files = useMemo(() => {
    const parsed = parseFiles(latestContent);
    setActiveIdx(0);
    return parsed;
  }, [latestContent]);

  const activeFile = files[activeIdx];

  // Empty state
  if (files.length === 0) {
    return (
      <div className="flex flex-col h-full items-center justify-center px-8 text-center"
        style={{ background: 'var(--ink)' }}>
        <div className="w-16 h-16 rounded-2xl bg-indigo-500/10 border border-indigo-500/20
          flex items-center justify-center mb-5">
          {streaming
            ? <Code2 className="w-7 h-7 text-indigo-400 animate-pulse" />
            : <FileCode className="w-7 h-7 text-slate-600" />
          }
        </div>
        <h3 className="text-sm font-medium text-slate-400 mb-2">
          {streaming ? 'Generating code…' : 'Code will appear here'}
        </h3>
        <p className="text-xs text-slate-600 max-w-[220px] leading-relaxed">
          {streaming
            ? 'Files will populate as Loomaris writes them'
            : 'Send a message and Loomaris will generate files visible in this panel'
          }
        </p>
        {streaming && (
          <div className="mt-4 flex gap-1">
            {[0, 1, 2].map((i) => (
              <div key={i} className="w-1 h-6 rounded-full bg-indigo-500/30"
                style={{ animation: `pulse ${0.8 + i * 0.15}s ease-in-out ${i * 0.15}s infinite alternate` }}
              />
            ))}
          </div>
        )}
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full" style={{ background: 'var(--ink)' }}>

      {/* Header */}
      <div className="flex items-center justify-between px-4 py-2.5 border-b shrink-0"
        style={{ borderColor: 'var(--border)', background: 'var(--surface)' }}>
        <div className="flex items-center gap-2">
          <Code2 className="w-3.5 h-3.5 text-indigo-400" />
          <span className="text-xs font-medium text-slate-300">Generated Files</span>
          <span className="text-[10px] bg-indigo-500/15 text-indigo-400 border border-indigo-500/20
            px-1.5 py-0.5 rounded-full font-mono">
            {files.length}
          </span>
        </div>
        <div className="flex items-center gap-1">
          {appId && appSlug && files.length > 0 && (
            <button
              onClick={() => downloadArchive(appId, appSlug)}
              className="flex items-center gap-1.5 text-xs text-slate-500 hover:text-slate-200
                transition-colors px-3 py-1.5 rounded-lg hover:bg-white/[0.05] border border-transparent
                hover:border-white/[0.08]">
              <Download className="w-3.5 h-3.5" />
              Download
            </button>
          )}
          {activeFile && <CopyBtn text={activeFile.content} />}
        </div>
      </div>

      {/* File tabs */}
      <div className="flex overflow-x-auto border-b shrink-0 scrollbar-none"
        style={{ borderColor: 'var(--border)', background: 'rgba(0,0,0,0.2)' }}>
        {files.map((f, i) => (
          <FileTab key={f.path} file={f} active={i === activeIdx} onClick={() => setActiveIdx(i)} />
        ))}
      </div>

      {/* File path breadcrumb */}
      {activeFile && (
        <div className="flex items-center gap-1 px-4 py-2 text-[11px] font-mono text-slate-600 border-b shrink-0"
          style={{ borderColor: 'var(--border)' }}>
          {activeFile.path.split('/').map((seg, i, arr) => (
            <span key={i} className="flex items-center gap-1">
              {i > 0 && <ChevronRight className="w-2.5 h-2.5 text-slate-700" />}
              <span className={i === arr.length - 1 ? 'text-slate-400' : ''}>{seg}</span>
            </span>
          ))}
          <span className="ml-auto text-slate-700">{activeFile.lang}</span>
        </div>
      )}

      {/* Code content */}
      {activeFile && (
        <div className="flex-1 overflow-auto">
          <pre className="min-h-full p-5">
            <code className="text-xs font-mono text-slate-300 leading-relaxed">
              {activeFile.content}
            </code>
          </pre>
        </div>
      )}
    </div>
  );
}
