'use client';

import { useState, useEffect, useRef } from 'react';
import {
  Rocket, Loader2, CheckCircle2, XCircle, ExternalLink,
  DollarSign, ChevronDown, ChevronUp, Activity, Cloud,
  RefreshCw, Play, Square, Timer,
} from 'lucide-react';
import {
  getDeployStatus, type DeployStatus,
  startSimulation, getSimulationStatus, stopSimulation, type SimulationSession,
} from '@/lib/api';
import { authHeaders } from '@/lib/auth';

const BASE = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';

interface DeployLog {
  type: 'log' | 'error' | 'done';
  text?: string;
  message?: string;
  url?: string;
}

interface TierCost {
  tier_label: string;
  monthly_cost_usd: string;
  breakdown: Record<string, string>;
  assumptions: string[];
}

interface CostEstimate {
  status: string;
  tier_estimates?: Record<string, Record<string, TierCost>>;
  summary_text?: string;
  recommendations?: string[];
  cap_result?: { warning_at_80_pct: boolean; reason?: string };
}

interface CloudAccount {
  id: string;
  display_name: string;
  provider: string;
  status: string;
}

interface Props {
  appId: string;
  hasFiles: boolean;
}

export default function DeployPanel({ appId, hasFiles }: Props) {
  const [currentStatus, setCurrentStatus] = useState<DeployStatus | null>(null);
  const [deploying, setDeploying] = useState(false);
  const [logs, setLogs] = useState<DeployLog[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [deployUrl, setDeployUrl] = useState<string | null>(null);
  const [deployMode, setDeployMode] = useState<'local' | 'cloud'>('local');
  const [cloudAccounts, setCloudAccounts] = useState<CloudAccount[]>([]);
  const [selectedAccount, setSelectedAccount] = useState<string>('');
  const [costEstimate, setCostEstimate] = useState<CostEstimate | null>(null);
  const [showCost, setShowCost] = useState(false);
  const [costLoading, setCostLoading] = useState(false);
  const [cloudDeployId, setCloudDeployId] = useState<string | null>(null);
  const [cloudStatus, setCloudStatus] = useState<string | null>(null);
  const [simSession, setSimSession] = useState<SimulationSession | null>(null);
  const [simLoading, setSimLoading] = useState(false);
  const [simError, setSimError] = useState<string | null>(null);
  const [simSecondsLeft, setSimSecondsLeft] = useState<number | null>(null);
  const logsEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!appId) return;
    getDeployStatus(appId).then(setCurrentStatus).catch(() => {});
    // Load cloud accounts
    fetch(`${BASE}/api/v1/cloud/accounts`, { headers: authHeaders() as Record<string, string> })
      .then(r => r.ok ? r.json() : [])
      .then((accounts: CloudAccount[]) => {
        setCloudAccounts(accounts.filter(a => a.status === 'verified'));
        if (accounts.length > 0) setSelectedAccount(accounts[0].id);
      })
      .catch(() => {});
  }, [appId]);

  useEffect(() => {
    logsEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [logs]);

  // Poll cloud deployment status
  useEffect(() => {
    if (!cloudDeployId) return;
    const timer = setInterval(async () => {
      const r = await fetch(
        `${BASE}/api/v1/apps/${appId}/cloud-deploy/${cloudDeployId}/status`,
        { headers: authHeaders() as Record<string, string> },
      );
      if (r.ok) {
        const data = await r.json();
        setCloudStatus(data.status);
        if (['success', 'failed'].includes(data.status)) {
          clearInterval(timer);
          if (data.status === 'success' && data.outputs?.alb_url) {
            setDeployUrl(data.outputs.alb_url);
          }
          if (data.status === 'success' && data.outputs?.cdn_url) {
            setDeployUrl(data.outputs.cdn_url);
          }
        }
      }
    }, 3000);
    return () => clearInterval(timer);
  }, [cloudDeployId, appId]);

  const loadCostEstimate = async () => {
    setCostLoading(true);
    try {
      const r = await fetch(`${BASE}/api/v1/apps/${appId}/cost-estimate`, {
        method: 'POST',
        headers: { ...(authHeaders() as Record<string, string>), 'Content-Type': 'application/json' },
        body: JSON.stringify({ cloud_providers: ['aws'] }),
      });
      if (r.ok) {
        const task = await r.json();
        // Poll for result
        await new Promise(resolve => setTimeout(resolve, 2000));
        const result = await fetch(`${BASE}/api/v1/apps/${appId}/cost-estimate/latest`, {
          headers: authHeaders() as Record<string, string>,
        });
        if (result.ok) setCostEstimate(await result.json());
      }
    } catch { /* ignore */ } finally {
      setCostLoading(false);
    }
  };

  // Countdown timer for simulation TTL
  useEffect(() => {
    if (!simSession?.expires_at || simSession.status !== 'running') {
      setSimSecondsLeft(null);
      return;
    }
    const update = () => {
      const diff = Math.max(0, Math.floor((new Date(simSession.expires_at!).getTime() - Date.now()) / 1000));
      setSimSecondsLeft(diff);
    };
    update();
    const interval = setInterval(update, 1000);
    return () => clearInterval(interval);
  }, [simSession?.expires_at, simSession?.status]);

  // Poll simulation status while building/starting
  useEffect(() => {
    if (!simSession || ['running', 'expired', 'failed', 'stopped'].includes(simSession.status)) return;
    const timer = setInterval(async () => {
      try {
        const updated = await getSimulationStatus(appId);
        setSimSession(updated);
      } catch { /* keep polling */ }
    }, 3000);
    return () => clearInterval(timer);
  }, [simSession?.status, appId]);

  const launchSimulation = async () => {
    setSimLoading(true);
    setSimError(null);
    try {
      const session = await startSimulation(appId);
      setSimSession(session);
    } catch (e) {
      setSimError(e instanceof Error ? e.message : 'Failed to start simulation');
    } finally {
      setSimLoading(false);
    }
  };

  const terminateSimulation = async () => {
    try {
      await stopSimulation(appId);
      setSimSession(null);
      setSimSecondsLeft(null);
    } catch { /* ignore */ }
  };

  const deployLocal = async () => {
    setDeploying(true);
    setLogs([]);
    setError(null);
    setDeployUrl(null);

    const headers = authHeaders() as Record<string, string>;
    try {
      const res = await fetch(`${BASE}/api/v1/apps/${appId}/deploy`, { method: 'POST', headers });
      if (!res.ok || !res.body) {
        const err = await res.json().catch(() => ({ detail: 'Deploy failed' }));
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
            setLogs(prev => [...prev, event]);
            if (event.type === 'done' && event.url) setDeployUrl(event.url);
            if (event.type === 'error') setError(event.message ?? 'Deploy failed');
          } catch { /* skip */ }
        }
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Deploy failed');
    } finally {
      setDeploying(false);
    }
  };

  const deployCloud = async () => {
    if (!selectedAccount) return;
    setDeploying(true);
    setError(null);
    setCloudStatus('queued');
    try {
      const r = await fetch(`${BASE}/api/v1/apps/${appId}/cloud-deploy`, {
        method: 'POST',
        headers: { ...(authHeaders() as Record<string, string>), 'Content-Type': 'application/json' },
        body: JSON.stringify({
          cloud_account_id: selectedAccount,
          environment: 'preview',
          confirm_cost: true,
        }),
      });
      if (!r.ok) {
        const err = await r.json().catch(() => ({ detail: 'Cloud deploy failed' }));
        throw new Error(err.detail || 'Cloud deploy failed');
      }
      const data = await r.json();
      setCloudDeployId(data.deployment_id);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Cloud deploy failed');
      setCloudStatus(null);
    } finally {
      setDeploying(false);
    }
  };

  const isRunning = currentStatus?.running || !!deployUrl;
  const liveUrl = deployUrl ?? currentStatus?.url;

  const cloudStatusColor = {
    queued: 'text-amber-400',
    planning: 'text-blue-400',
    applying: 'text-indigo-400',
    preview_ready: 'text-cyan-400',
    success: 'text-emerald-400',
    failed: 'text-rose-400',
  }[cloudStatus ?? ''] ?? 'text-slate-400';

  return (
    <div className="flex flex-col gap-3 px-4 py-4 border-t"
      style={{ borderColor: 'var(--border)', background: 'var(--surface)' }}>

      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Rocket className="w-4 h-4 text-indigo-400" />
          <span className="text-sm font-medium text-slate-200">Deploy</span>
          {isRunning && deployMode === 'local' && (
            <span className="flex items-center gap-1 text-[11px] text-emerald-400 font-mono">
              <Activity className="w-3 h-3" /> running locally
            </span>
          )}
          {cloudStatus && (
            <span className={`text-[11px] font-mono ${cloudStatusColor}`}>{cloudStatus}</span>
          )}
        </div>

        <div className="flex items-center gap-2">
          {/* Cost toggle (cloud mode) */}
          {deployMode === 'cloud' && (
            <button
              onClick={() => { setShowCost(!showCost); if (!costEstimate) loadCostEstimate(); }}
              className="flex items-center gap-1 text-xs text-slate-500 hover:text-slate-300 transition-colors px-2 py-1 rounded-lg hover:bg-white/5">
              <DollarSign className="w-3.5 h-3.5" />
              Cost
              {showCost ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
            </button>
          )}

          {/* Live link */}
          {liveUrl && (
            <a href={liveUrl} target="_blank" rel="noopener noreferrer"
              className="flex items-center gap-1.5 text-xs text-emerald-400 hover:text-emerald-300 transition-colors px-2.5 py-1 rounded-lg border"
              style={{ borderColor: 'rgba(52,211,153,0.25)', background: 'rgba(52,211,153,0.08)' }}>
              <ExternalLink className="w-3 h-3" /> Open app
            </a>
          )}

          {/* Mode toggle */}
          <div className="flex rounded-lg overflow-hidden border" style={{ borderColor: 'var(--border)' }}>
            {(['local', 'cloud'] as const).map(mode => (
              <button key={mode}
                onClick={() => setDeployMode(mode)}
                className="px-2.5 py-1 text-[11px] font-medium transition-colors"
                style={{
                  background: deployMode === mode ? 'rgba(99,102,241,0.2)' : 'transparent',
                  color: deployMode === mode ? '#a5b4fc' : 'var(--muted)',
                }}>
                {mode === 'local' ? '🐳 Local' : '☁️ Cloud'}
              </button>
            ))}
          </div>

          {/* Deploy button */}
          <button
            onClick={deployMode === 'local' ? deployLocal : deployCloud}
            disabled={!hasFiles || deploying || (deployMode === 'cloud' && !selectedAccount)}
            className="flex items-center gap-1.5 text-xs font-medium px-3.5 py-1.5 rounded-xl transition-all disabled:opacity-40 disabled:cursor-not-allowed"
            style={{
              background: 'rgba(99,102,241,0.2)',
              border: '1px solid rgba(99,102,241,0.3)',
              color: '#a5b4fc',
            }}>
            {deploying
              ? <><Loader2 className="w-3.5 h-3.5 animate-spin" />{deployMode === 'cloud' ? 'Queuing…' : 'Building…'}</>
              : <><Rocket className="w-3.5 h-3.5" />{isRunning ? 'Redeploy' : 'Deploy'}</>
            }
          </button>
        </div>
      </div>

      {/* Cloud account selector */}
      {deployMode === 'cloud' && (
        <div className="flex items-center gap-2">
          <Cloud className="w-3.5 h-3.5 text-slate-500 shrink-0" />
          {cloudAccounts.length === 0 ? (
            <span className="text-xs text-amber-500/80">
              No verified cloud accounts. Connect one via the Cloud icon above.
            </span>
          ) : (
            <select
              value={selectedAccount}
              onChange={e => setSelectedAccount(e.target.value)}
              className="text-xs text-slate-300 rounded-lg px-2.5 py-1.5 border outline-none flex-1"
              style={{ background: 'rgba(0,0,0,0.3)', borderColor: 'var(--border)' }}>
              {cloudAccounts.map(a => (
                <option key={a.id} value={a.id}>
                  {a.provider.toUpperCase()} — {a.display_name}
                </option>
              ))}
            </select>
          )}
        </div>
      )}

      {/* Cost estimate panel */}
      {deployMode === 'cloud' && showCost && (
        <div className="rounded-xl border p-3" style={{ borderColor: 'var(--border)', background: 'rgba(0,0,0,0.2)' }}>
          {costLoading ? (
            <div className="flex items-center gap-2 text-xs text-slate-400">
              <Loader2 className="w-3.5 h-3.5 animate-spin" /> Computing estimate…
            </div>
          ) : costEstimate?.tier_estimates ? (
            <>
              {costEstimate.summary_text && (
                <p className="text-[11px] text-slate-400 mb-2 leading-relaxed">{costEstimate.summary_text}</p>
              )}
              <div className="grid grid-cols-2 gap-1.5">
                {Object.entries(costEstimate.tier_estimates).map(([provider, tiers]) =>
                  Object.entries(tiers).map(([key, tier]) => (
                    <div key={`${provider}-${key}`} className="rounded-lg p-2 border text-[11px]"
                      style={{ borderColor: 'var(--border)', background: 'rgba(0,0,0,0.2)' }}>
                      <div className="text-slate-500 font-mono">{tier.tier_label}</div>
                      <div className="text-white font-semibold">${parseFloat(tier.monthly_cost_usd).toFixed(2)}/mo</div>
                    </div>
                  ))
                )}
              </div>
              {costEstimate.cap_result?.warning_at_80_pct && (
                <p className="mt-2 text-[11px] text-amber-400">
                  ⚠ Approaching org spend cap — check settings before deploying at scale.
                </p>
              )}
            </>
          ) : (
            <button onClick={loadCostEstimate} className="text-xs text-indigo-400 hover:text-indigo-300">
              <RefreshCw className="w-3 h-3 inline mr-1" /> Load cost estimate
            </button>
          )}
        </div>
      )}

      {/* Local deploy logs */}
      {deployMode === 'local' && logs.length > 0 && (
        <div className="rounded-xl border overflow-hidden" style={{ borderColor: 'var(--border)', background: 'rgba(0,0,0,0.4)' }}>
          <div className="px-3 py-1.5 border-b flex items-center gap-2" style={{ borderColor: 'var(--border)' }}>
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

      {/* Preview Live / Simulation */}
      <div className="border-t pt-3" style={{ borderColor: 'var(--border)' }}>
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Play className="w-3.5 h-3.5 text-cyan-400" />
            <span className="text-xs font-medium text-slate-300">Preview Live</span>
            {simSession?.status === 'running' && simSecondsLeft !== null && (
              <span className="flex items-center gap-1 text-[11px] text-slate-500 font-mono">
                <Timer className="w-3 h-3" />
                {Math.floor(simSecondsLeft / 60)}:{String(simSecondsLeft % 60).padStart(2, '0')}
              </span>
            )}
            {simSession && !['running', 'expired', 'failed', 'stopped'].includes(simSession.status) && (
              <span className="text-[11px] text-cyan-400 font-mono animate-pulse">{simSession.status}…</span>
            )}
          </div>

          <div className="flex items-center gap-2">
            {simSession?.status === 'running' && simSession.url && (
              <a href={simSession.url} target="_blank" rel="noopener noreferrer"
                className="flex items-center gap-1 text-xs text-cyan-400 hover:text-cyan-300 transition-colors px-2 py-1 rounded-lg border"
                style={{ borderColor: 'rgba(34,211,238,0.25)', background: 'rgba(34,211,238,0.08)' }}>
                <ExternalLink className="w-3 h-3" /> Open
              </a>
            )}
            {simSession?.status === 'running' ? (
              <button onClick={terminateSimulation}
                className="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-xl transition-all"
                style={{ background: 'rgba(244,63,94,0.15)', border: '1px solid rgba(244,63,94,0.3)', color: '#fb7185' }}>
                <Square className="w-3 h-3" /> Stop
              </button>
            ) : (
              <button onClick={launchSimulation}
                disabled={!hasFiles || simLoading || (simSession?.status === 'building')}
                className="flex items-center gap-1.5 text-xs font-medium px-3.5 py-1.5 rounded-xl transition-all disabled:opacity-40 disabled:cursor-not-allowed"
                style={{ background: 'rgba(34,211,238,0.1)', border: '1px solid rgba(34,211,238,0.25)', color: '#22d3ee' }}>
                {simLoading || simSession?.status === 'building'
                  ? <><Loader2 className="w-3.5 h-3.5 animate-spin" />Building…</>
                  : <><Play className="w-3.5 h-3.5" />Preview Live</>
                }
              </button>
            )}
          </div>
        </div>

        {simError && (
          <div className="flex items-center gap-1.5 mt-2 text-xs text-rose-400">
            <XCircle className="w-3.5 h-3.5 shrink-0" />
            {simError}
          </div>
        )}
        {(simSession?.status === 'expired' || simSession?.status === 'failed') && (
          <p className="mt-1.5 text-[11px] text-slate-500">
            Session {simSession.status}. Launch a new one to preview again.
          </p>
        )}
      </div>

      {!hasFiles && (
        <p className="text-xs text-slate-600 text-center py-1">
          Ask Loomaris to generate code first, then deploy it here.
        </p>
      )}
    </div>
  );
}
