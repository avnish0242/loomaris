'use client';

import { Code2, CloudUpload, Download, Zap } from 'lucide-react';
import { downloadArchive } from '@/lib/api';

interface Props {
  appId: string;
  appSlug: string;
  budgetRemaining?: number | null;
  onViewCode: () => void;
  onDeploy: () => void;
  onSimulate: () => void;
}

export default function ActionBar({ appId, appSlug, budgetRemaining, onViewCode, onDeploy, onSimulate }: Props) {
  const budgetLabel = budgetRemaining != null
    ? `$${budgetRemaining.toFixed(2)} remaining this month`
    : 'Up to 15 min free';

  return (
    <div className="flex items-center gap-2 px-4 py-2.5 border-t shrink-0"
      style={{ borderColor: 'var(--border)', background: 'var(--surface)' }}>

      <div className="relative group">
        <button
          onClick={onSimulate}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium text-indigo-300 border border-indigo-500/30 hover:border-indigo-500/60 hover:bg-indigo-500/10 transition-all">
          <Zap className="w-3.5 h-3.5" />
          Simulate
        </button>
        <div className="absolute bottom-full left-0 mb-1.5 px-2 py-1 rounded text-[10px] text-slate-400 whitespace-nowrap opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none"
          style={{ background: 'rgba(0,0,0,0.8)', border: '1px solid rgba(255,255,255,0.08)' }}>
          {budgetLabel}
        </div>
      </div>

      <button
        onClick={onViewCode}
        className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium text-slate-300 border border-slate-700 hover:border-slate-500 hover:bg-slate-800 transition-all">
        <Code2 className="w-3.5 h-3.5" />
        View Code
      </button>

      <button
        onClick={onDeploy}
        className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium text-emerald-300 border border-emerald-500/30 hover:border-emerald-500/60 hover:bg-emerald-500/10 transition-all">
        <CloudUpload className="w-3.5 h-3.5" />
        Deploy to Cloud
      </button>

      <button
        onClick={() => downloadArchive(appId, appSlug)}
        className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium text-slate-400 border border-slate-700 hover:border-slate-500 hover:bg-slate-800 transition-all">
        <Download className="w-3.5 h-3.5" />
        Download
      </button>
    </div>
  );
}
