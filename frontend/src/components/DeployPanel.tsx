'use client';

import { useState, useEffect, useRef } from 'react';
import {
  Rocket, Loader2, CheckCircle2, XCircle, ExternalLink,
  DollarSign, ChevronDown, ChevronUp, Activity,
} from 'lucide-react';
import { getCostEstimate, getDeployStatus, type CostOption, type DeployStatus } from '@/lib/api';
import { authHeaders } from '@/lib/auth';

const BASE = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';

interface DeployLog {
  type: 'log' | 'error' | 'done';
  text?: string;
  message?: string;
  url?: string;
}

interface Props {
  appId: string;
  hasFiles: boolean;
}

export default function DeployPanel({ appId, hasFiles }: Props) {
  const [costOptions, setCostOptions] = useState<CostOption[]>([]);
  const [currentStatus, setCurrentStatus] = useState<DeployStatus | null>(null);
  const [deploying, setDeploying] = useState(false);
  const [logs, setLogs] = useState<DeployLog[]>([]);
  const [showCost, setShowCost] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [deployUrl, setDeployUrl] = useState<string | null>(null);
  const logsEndRef = useRef<HTMLDivElement>(null);

  // Load cost estimate and current status
  useEffect(() => {
    if (!appId) return;
    getCostEstimate(appId).then((r) => setCostOptions(r.options)).catch(() => {});
    getDeployStatus(appId).then(setCurrentStatus).catch(() => {});
  }, [appId]);

  // Auto-scroll logs
  useEffect(() => {
    logsEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [logs]);

  const deploy = async () => {
    setDeploying(true);
    setLogs([]);
    setError(null);
    setDeployUrl(null);

    const headers = authHeaders() as Record<string, string>;
    try {
      const res = await fetch(`${BASE}/api/v1/apps/${appId}/deploy`, {
        method: 'POST',
        headers,
      });

      if (!res.ok || !res.body) {
        const err = await res.json().catch(() => ({ detail: 'Deploy request failed' }));
        throw new Error(err.detail);
      }

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() ?? '';

        for (const line of lines) {
          if (!line.startsWith('data: ')) continue;
          try {
            const event: DeployLog = JSON.parse(line.slice(6));
            setLogs((prev) => [...prev, event]);
            if (event.type === 'done' && event.url) {
              setDeployUrl(event.url);
              setCurrentStatus((s) => s ? { ...s, running: true, url: event.url ?? null } : s);
            }
            if (event.type === 'error') {
              setError(event.message ?? 'Deploy failed');
            }
          } catch {
            // skip malformed line
          }
        }
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Deploy failed');
    } finally {
      setDeploying(false);
    }
  };

  const isRunning = currentStatus?.running || !!deployUrl;
  const liveUrl = deployUrl ?? currentStatus?.url;

  return (
    <div className="flex flex-col gap-3 px-4 py-4 border-t"
      style={{ borderColor: 'var(--border)', background: 'var(--surface)' }}>

      {/* Title row */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Rocket className="w-4 h-4 text-indigo-400" />
          <span className="text-sm font-medium text-slate-200">Deploy</span>
          {isRunning && (
            <span className="flex items-center gap-1 text-[11px] text-emerald-400 font-mono">
              <Activity className="w-3 h-3" />
              running
            </span>
          )}
        </div>

        <div className="flex items-center gap-2">
          {/* Cost toggle */}
          {costOptions.length > 0 && (
            <button onClick={() => setShowCost(!showCost)}
              className="flex items-center gap-1 text-xs text-slate-500 hover:text-slate-300
                transition-colors px-2 py-1 rounded-lg hover:bg-white/5">
              <DollarSign className="w-3.5 h-3.5" />
              Pricing
              {showCost ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
            </button>
          )}

          {/* Live link */}
          {liveUrl && (
            <a href={liveUrl} target="_blank" rel="noopener noreferrer"
              className="flex items-center gap-1.5 text-xs text-emerald-400 hover:text-emerald-300
                transition-colors px-2.5 py-1 rounded-lg border"
              style={{ borderColor: 'rgba(52,211,153,0.25)', background: 'rgba(52,211,153,0.08)' }}>
              <ExternalLink className="w-3 h-3" />
              Open app
            </a>
          )}

          {/* Deploy button */}
          <button
            onClick={deploy}
            disabled={!hasFiles || deploying}
            className="flex items-center gap-1.5 text-xs font-medium px-3.5 py-1.5 rounded-xl
              transition-all disabled:opacity-40 disabled:cursor-not-allowed"
            style={{
              background: 'rgba(99,102,241,0.2)',
              border: '1px solid rgba(99,102,241,0.3)',
              color: '#a5b4fc',
            }}>
            {deploying
              ? <><Loader2 className="w-3.5 h-3.5 animate-spin" />Building…</>
              : <><Rocket className="w-3.5 h-3.5" />{isRunning ? 'Redeploy' : 'Deploy'}</>
            }
          </button>
        </div>
      </div>

      {/* Cost estimate */}
      {showCost && (
        <div className="grid grid-cols-3 gap-2">
          {costOptions.map((opt) => (
            <div key={opt.id}
              className="rounded-xl p-3 border flex flex-col gap-1"
              style={{
                background: opt.recommended ? 'rgba(99,102,241,0.08)' : 'rgba(0,0,0,0.2)',
                borderColor: opt.recommended ? 'rgba(99,102,241,0.25)' : 'var(--border)',
                opacity: opt.available ? 1 : 0.5,
              }}>
              <div className="flex items-center justify-between">
                <span className="text-xs font-medium text-slate-300">{opt.label}</span>
                {opt.recommended && (
                  <span className="text-[10px] text-indigo-400 font-mono">now</span>
                )}
              </div>
              <span className="text-sm font-semibold text-white">{opt.cost_label}</span>
              <span className="text-[11px] text-slate-500 leading-relaxed">{opt.description}</span>
              {!opt.available && opt.available_note && (
                <span className="text-[10px] text-amber-500/70 mt-0.5">{opt.available_note}</span>
              )}
            </div>
          ))}
        </div>
      )}

      {/* Deploy logs */}
      {logs.length > 0 && (
        <div className="rounded-xl border overflow-hidden"
          style={{ borderColor: 'var(--border)', background: 'rgba(0,0,0,0.4)' }}>
          <div className="px-3 py-1.5 border-b flex items-center gap-2"
            style={{ borderColor: 'var(--border)' }}>
            <span className="text-[11px] font-mono text-slate-600">deploy log</span>
            {deploying && <Loader2 className="w-3 h-3 text-slate-600 animate-spin" />}
          </div>
          <div className="max-h-40 overflow-y-auto p-3 space-y-0.5">
            {logs.map((log, i) => (
              <div key={i} className={`flex items-start gap-2 text-[11px] font-mono leading-relaxed
                ${log.type === 'error' ? 'text-rose-400' : log.type === 'done' ? 'text-emerald-400' : 'text-slate-400'}`}>
                <span className="shrink-0 mt-0.5">
                  {log.type === 'error' ? <XCircle className="w-3 h-3" /> :
                   log.type === 'done' ? <CheckCircle2 className="w-3 h-3" /> :
                   <span className="w-3 h-3 block text-slate-600">›</span>}
                </span>
                <span>{log.text ?? log.message ?? JSON.stringify(log)}</span>
              </div>
            ))}
            <div ref={logsEndRef} />
          </div>
        </div>
      )}

      {/* Error */}
      {error && (
        <div className="flex items-center gap-2 text-xs text-rose-400 px-1">
          <XCircle className="w-3.5 h-3.5 shrink-0" />
          {error}
        </div>
      )}

      {!hasFiles && (
        <p className="text-xs text-slate-600 text-center py-1">
          Ask Loomaris to generate code first, then deploy it here.
        </p>
      )}
    </div>
  );
}
