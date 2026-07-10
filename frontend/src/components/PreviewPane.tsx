'use client';

import { useEffect, useRef, useState } from 'react';
import { ExternalLink, RefreshCw, Square, AlertTriangle, Loader2, Zap, Clock } from 'lucide-react';
import { stopPreview, getSimulationStatus, stopSimulation, type SimulationSession } from '@/lib/api';
import { authHeaders } from '@/lib/auth';

type PreviewState = 'idle' | 'building' | 'running' | 'error' | 'simulating' | 'sim_ready' | 'sim_ended';

interface Props {
  appId: string;
  autoTrigger?: boolean;
  simulationMode?: boolean;   // true = use ECS simulation flow instead of local Docker
  onStopped?: () => void;
}

const BASE = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';

function formatCountdown(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return `${m}:${s.toString().padStart(2, '0')}`;
}

export default function PreviewPane({ appId, autoTrigger = false, simulationMode = false, onStopped }: Props) {
  const [state, setState] = useState<PreviewState>('idle');
  const [logs, setLogs] = useState<string[]>([]);
  const [url, setUrl] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [simSession, setSimSession] = useState<SimulationSession | null>(null);
  const [secondsLeft, setSecondsLeft] = useState<number>(0);
  const logsEndRef = useRef<HTMLDivElement>(null);
  const buildingRef = useRef(false);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const countdownRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    if (autoTrigger) {
      if (simulationMode) startSimulation();
      else startBuild();
    }
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
      if (countdownRef.current) clearInterval(countdownRef.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [autoTrigger, simulationMode]);

  useEffect(() => {
    logsEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [logs]);

  // ── Local Docker build ──────────────────────────────────────────────────────

  async function startBuild() {
    if (buildingRef.current) return;
    buildingRef.current = true;
    setState('building');
    setLogs([]);
    setError(null);
    setUrl(null);

    try {
      const res = await fetch(`${BASE}/api/v1/apps/${appId}/deploy`, {
        method: 'POST',
        headers: { ...authHeaders() as Record<string, string> },
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: res.statusText }));
        throw new Error(err.detail ?? `HTTP ${res.status}`);
      }

      const reader = res.body!.getReader();
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
            const event = JSON.parse(line.slice(6));
            if (event.type === 'log' && event.text?.trim()) setLogs((p) => [...p, event.text]);
            else if (event.type === 'done') { setUrl(event.url); setState('running'); }
            else if (event.type === 'error') { setError(event.message); setState('error'); }
          } catch { /* skip malformed */ }
        }
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Build failed');
      setState('error');
    } finally {
      buildingRef.current = false;
    }
  }

  async function handleStop() {
    if (pollRef.current) clearInterval(pollRef.current);
    if (countdownRef.current) clearInterval(countdownRef.current);
    try { await stopPreview(appId); } catch { /* container may already be gone */ }
    setUrl(null); setState('idle'); setLogs([]);
    onStopped?.();
  }

  // ── ECS Simulation ──────────────────────────────────────────────────────────

  async function startSimulation() {
    if (buildingRef.current) return;
    buildingRef.current = true;
    setState('simulating');
    setLogs(['Starting ECS Fargate simulation…', 'Building Docker image…']);
    setError(null);
    setUrl(null);
    setSimSession(null);

    // POST already done by page.tsx (startSimulation in api.ts) before rendering this pane.
    // Here we just poll status.
    pollRef.current = setInterval(async () => {
      try {
        const status = await getSimulationStatus(appId);
        setSimSession(status);
        if (status.status === 'running' && status.url) {
          if (pollRef.current) clearInterval(pollRef.current);
          setUrl(status.url);
          setState('sim_ready');
          buildingRef.current = false;
          // Start countdown
          if (status.expires_at) {
            const expiresAt = new Date(status.expires_at).getTime();
            const tick = () => {
              const left = Math.max(0, Math.floor((expiresAt - Date.now()) / 1000));
              setSecondsLeft(left);
              if (left === 0) {
                if (countdownRef.current) clearInterval(countdownRef.current);
                setState('sim_ended');
              }
            };
            tick();
            countdownRef.current = setInterval(tick, 1000);
          }
        } else if (status.status === 'failed') {
          if (pollRef.current) clearInterval(pollRef.current);
          setError('Simulation failed to start. Check that SIM_* env vars are configured.');
          setState('error');
          buildingRef.current = false;
        } else {
          // Still building — update log
          setLogs((prev) => {
            const msg = `Waiting for Fargate task to get a public IP…`;
            if (prev.includes(msg)) return prev;
            return [...prev, msg];
          });
        }
      } catch {
        /* keep polling */
      }
    }, 3000);
  }

  async function handleStopSim() {
    if (pollRef.current) clearInterval(pollRef.current);
    if (countdownRef.current) clearInterval(countdownRef.current);
    try { await stopSimulation(appId); } catch { /* already stopped */ }
    setState('idle'); setUrl(null); setSimSession(null);
    onStopped?.();
  }

  // ── Render ──────────────────────────────────────────────────────────────────

  const isSim = simulationMode || ['simulating', 'sim_ready', 'sim_ended'].includes(state);

  return (
    <div className="flex flex-col h-full" style={{ background: 'var(--surface)' }}>
      {/* Toolbar */}
      <div className="flex items-center gap-2 px-3 py-2 shrink-0 border-b"
        style={{ borderColor: 'var(--border)' }}>
        <span className="flex-1 text-xs font-mono truncate text-slate-400">
          {state === 'sim_ready' && url
            ? url
            : state === 'simulating'
            ? 'Starting simulation…'
            : state === 'sim_ended'
            ? 'Simulation ended'
            : url ?? (state === 'building' ? 'Building…' : 'No preview')}
        </span>

        {/* Countdown badge */}
        {state === 'sim_ready' && secondsLeft > 0 && (
          <span className="flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-mono text-amber-400"
            style={{ background: 'rgba(245,158,11,0.1)', border: '1px solid rgba(245,158,11,0.2)' }}>
            <Clock className="w-2.5 h-2.5" />
            {formatCountdown(secondsLeft)}
          </span>
        )}

        {(state === 'sim_ready' || state === 'running') && url && (
          <a href={url} target="_blank" rel="noreferrer"
            className="flex items-center gap-1 px-2 py-1 rounded text-xs text-slate-400 hover:text-slate-200 transition-colors">
            <ExternalLink className="w-3.5 h-3.5" />
          </a>
        )}

        {state === 'running' && (
          <button onClick={startBuild}
            className="flex items-center gap-1 px-2 py-1 rounded text-xs text-slate-400 hover:text-slate-200 transition-colors"
            title="Rebuild">
            <RefreshCw className="w-3.5 h-3.5" />
          </button>
        )}

        {(state === 'running' || state === 'building') && (
          <button onClick={handleStop}
            className="flex items-center gap-1 px-2 py-1 rounded text-xs text-rose-400 hover:text-rose-300 transition-colors"
            title="Stop preview">
            <Square className="w-3.5 h-3.5" />
          </button>
        )}

        {(state === 'simulating' || state === 'sim_ready') && (
          <button onClick={handleStopSim}
            className="flex items-center gap-1 px-2 py-1 rounded text-xs text-rose-400 hover:text-rose-300 transition-colors"
            title="Stop simulation">
            <Square className="w-3.5 h-3.5" />
          </button>
        )}

        {(state === 'idle' || state === 'error') && (
          <button onClick={isSim ? startSimulation : startBuild}
            className="flex items-center gap-1.5 px-3 py-1 rounded text-xs font-medium text-indigo-300 hover:text-indigo-200 border border-indigo-500/30 hover:border-indigo-500/60 transition-all">
            {state === 'error' ? 'Retry' : isSim ? 'Simulate' : 'Build Preview'}
          </button>
        )}

        {state === 'sim_ended' && (
          <button onClick={startSimulation}
            className="flex items-center gap-1.5 px-3 py-1 rounded text-xs font-medium text-indigo-300 border border-indigo-500/30 hover:border-indigo-500/60 transition-all">
            New simulation
          </button>
        )}
      </div>

      {/* Content */}
      <div className="flex-1 overflow-hidden relative">
        {state === 'idle' && (
          <div className="flex flex-col items-center justify-center h-full gap-3 text-center px-6">
            <div className="w-12 h-12 rounded-xl bg-indigo-500/10 flex items-center justify-center">
              <ExternalLink className="w-6 h-6 text-indigo-400/60" />
            </div>
            <p className="text-sm text-slate-500">
              Your app preview will appear here after generation
            </p>
          </div>
        )}

        {(state === 'building' || state === 'simulating') && (
          <div className="flex flex-col h-full">
            <div className="flex items-center gap-2 px-4 py-3 border-b text-xs"
              style={{ borderColor: 'var(--border)', color: state === 'simulating' ? '#a78bfa' : '#a5b4fc' }}>
              <Loader2 className="w-3.5 h-3.5 animate-spin" />
              {state === 'simulating' ? 'Starting Fargate simulation…' : 'Building your app…'}
            </div>
            <div className="flex-1 overflow-y-auto px-4 py-3 font-mono text-xs text-slate-400 leading-relaxed">
              {logs.map((line, i) => <div key={i}>{line}</div>)}
              <div ref={logsEndRef} />
            </div>
          </div>
        )}

        {state === 'error' && (
          <div className="flex flex-col h-full">
            <div className="flex items-center gap-2 px-4 py-3 border-b text-xs text-rose-400"
              style={{ borderColor: 'var(--border)' }}>
              <AlertTriangle className="w-3.5 h-3.5" />
              {isSim ? 'Simulation failed' : 'Build failed'}
            </div>
            <div className="flex-1 overflow-y-auto px-4 py-3">
              {logs.length > 0 && (
                <div className="font-mono text-xs text-slate-400 leading-relaxed mb-4">
                  {logs.map((line, i) => <div key={i}>{line}</div>)}
                </div>
              )}
              {error && (
                <div className="px-3 py-2 rounded-lg text-xs text-rose-300"
                  style={{ background: 'rgba(251,113,133,0.08)', border: '1px solid rgba(251,113,133,0.2)' }}>
                  {error}
                </div>
              )}
            </div>
          </div>
        )}

        {state === 'running' && url && (
          <iframe src={url} title="App Preview" className="w-full h-full border-0"
            sandbox="allow-scripts allow-same-origin allow-forms allow-popups" />
        )}

        {state === 'sim_ready' && url && (
          <iframe src={url} title="Live Simulation" className="w-full h-full border-0"
            sandbox="allow-scripts allow-same-origin allow-forms allow-popups" />
        )}

        {state === 'sim_ended' && (
          <div className="flex flex-col items-center justify-center h-full gap-4 text-center px-6">
            <div className="w-12 h-12 rounded-xl flex items-center justify-center"
              style={{ background: 'rgba(99,102,241,0.1)', border: '1px solid rgba(99,102,241,0.2)' }}>
              <Zap className="w-6 h-6 text-indigo-400/60" />
            </div>
            <div>
              <h3 className="text-sm font-medium text-slate-300 mb-1">Simulation ended</h3>
              <p className="text-xs text-slate-500">The Fargate task has been stopped and all resources cleaned up.</p>
            </div>
            <button onClick={startSimulation}
              className="flex items-center gap-1.5 px-4 py-2 rounded-xl text-xs font-medium text-indigo-300 border border-indigo-500/30 hover:border-indigo-500/50 hover:bg-indigo-500/10 transition-all">
              <Zap className="w-3.5 h-3.5" />
              Start new simulation
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
