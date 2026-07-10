'use client';

import { useEffect, useState } from 'react';
import { X, Check, Loader2, ExternalLink, Copy, ChevronLeft, Shield, AlertCircle, CheckCircle2, XCircle } from 'lucide-react';
import {
  listCloudAccounts,
  CloudAccount,
  triggerCostEstimate,
  getLatestCostEstimate,
  CostEstimate,
  getDeployStatus,
  runPreflight,
  type PreflightResult,
} from '@/lib/api';
import { authHeaders } from '@/lib/auth';
import PermissionTemplateModal from './PermissionTemplateModal';

type Step = 'account' | 'preflight' | 'cost' | 'deploying' | 'success';

interface Props {
  appId: string;
  open: boolean;
  onClose: () => void;
}

const BASE = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';

export default function DeployModal({ appId, open, onClose }: Props) {
  const [step, setStep] = useState<Step>('account');
  const [accounts, setAccounts] = useState<CloudAccount[]>([]);
  const [selectedAccountId, setSelectedAccountId] = useState<string | null>(null);
  const [preflight, setPreflight] = useState<PreflightResult | null>(null);
  const [preflightLoading, setPreflightLoading] = useState(false);
  const [showPermModal, setShowPermModal] = useState(false);
  const [costEstimate, setCostEstimate] = useState<CostEstimate | null>(null);
  const [costLoading, setCostLoading] = useState(false);
  const [costError, setCostError] = useState<string | null>(null);
  const [deployLogs, setDeployLogs] = useState<{ text: string; done?: boolean }[]>([]);
  const [liveUrl, setLiveUrl] = useState<string | null>(null);
  const [deployError, setDeployError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    if (!open) return;
    setStep('account');
    setSelectedAccountId(null);
    setPreflight(null);
    setCostEstimate(null);
    setDeployLogs([]);
    setLiveUrl(null);
    setDeployError(null);
    listCloudAccounts()
      .then((accs) => setAccounts(accs.filter((a) => a.status === 'verified')))
      .catch(() => {});
  }, [open]);

  const selectedAccount = accounts.find((a) => a.id === selectedAccountId) ?? null;

  // ── Preflight ───────────────────────────────────────────────────────────────

  async function runPreflightCheck() {
    if (!selectedAccountId) return;
    setPreflightLoading(true);
    setPreflight(null);
    try {
      const result = await runPreflight(appId, selectedAccountId);
      setPreflight(result);
    } catch (e) {
      // Treat fetch errors as skipped (non-blocking)
      setPreflight({ passed: true, checked: [], missing: [], skipped: true,
        error: e instanceof Error ? e.message : 'Preflight check unavailable' });
    } finally {
      setPreflightLoading(false);
    }
  }

  function goToPreflight() {
    if (!selectedAccountId) return;
    setStep('preflight');
    runPreflightCheck();
  }

  // ── Cost estimate ───────────────────────────────────────────────────────────

  async function loadCostEstimate() {
    setCostLoading(true);
    setCostError(null);
    try {
      await triggerCostEstimate(appId);
      const deadline = Date.now() + 30_000;
      while (Date.now() < deadline) {
        await new Promise((r) => setTimeout(r, 2000));
        const est = await getLatestCostEstimate(appId);
        if (est.status === 'done') { setCostEstimate(est); return; }
        if (est.status === 'failed') { setCostError('Cost estimation failed. You can still deploy.'); return; }
      }
      setCostError('Cost estimate timed out. You can still deploy.');
    } catch (e) {
      setCostError(e instanceof Error ? e.message : 'Cost estimate failed.');
    } finally {
      setCostLoading(false);
    }
  }

  function goToCost() {
    setStep('cost');
    loadCostEstimate();
  }

  // ── Deploy ──────────────────────────────────────────────────────────────────

  async function startDeploy() {
    if (!selectedAccountId) return;
    setStep('deploying');
    setDeployLogs([]);
    setDeployError(null);
    try {
      const res = await fetch(`${BASE}/api/v1/apps/${appId}/cloud-deploy`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...authHeaders() as Record<string, string> },
        body: JSON.stringify({ cloud_account_id: selectedAccountId, environment: 'production', confirm_cost: true }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: res.statusText }));
        setDeployError(err.detail ?? `HTTP ${res.status}`);
        return;
      }
      const depData = await res.json();
      const deploymentId = depData.deployment_id;
      if (deploymentId) {
        const deadline = Date.now() + 300_000;
        while (Date.now() < deadline) {
          await new Promise((r) => setTimeout(r, 3000));
          try {
            const status = await getDeployStatus(appId);
            const dep = status.last_deployment;
            if (dep?.status === 'success' || dep?.status === 'running') {
              setLiveUrl((status as any).url ?? null);
              setStep('success');
              return;
            }
            if (dep?.status === 'failed') { setDeployError('Deployment failed. Check Celery logs.'); return; }
            setDeployLogs((prev) => {
              const msg = `Status: ${dep?.status ?? 'queued'}…`;
              if (prev[prev.length - 1]?.text === msg) return prev;
              return [...prev, { text: msg }];
            });
          } catch { /* keep polling */ }
        }
        setDeployError('Deployment timed out. Check your cloud console.');
      }
    } catch (e) {
      setDeployError(e instanceof Error ? e.message : 'Deploy failed');
    }
  }

  function copyUrl() {
    if (!liveUrl) return;
    navigator.clipboard.writeText(liveUrl);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  if (!open) return null;

  const canProceedFromPreflight = preflight && (preflight.passed || preflight.skipped);

  return (
    <>
      <div className="fixed inset-0 z-50 flex items-center justify-center p-4"
        style={{ background: 'rgba(0,0,0,0.7)' }}
        onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}>

        <div className="w-full max-w-md rounded-2xl shadow-2xl overflow-hidden flex flex-col"
          style={{ background: 'var(--surface)', border: '1px solid var(--border)' }}>

          {/* Header */}
          <div className="flex items-center justify-between px-5 py-4 border-b" style={{ borderColor: 'var(--border)' }}>
            <h2 className="text-sm font-semibold text-slate-200">
              {step === 'account' && 'Deploy to Cloud'}
              {step === 'preflight' && 'Permission Check'}
              {step === 'cost' && 'Cost Estimate'}
              {step === 'deploying' && 'Deploying…'}
              {step === 'success' && 'Live!'}
            </h2>
            <button onClick={onClose}
              className="p-1.5 rounded-lg text-slate-400 hover:text-slate-200 hover:bg-slate-800 transition-all">
              <X className="w-4 h-4" />
            </button>
          </div>

          {/* Step: account */}
          {step === 'account' && (
            <div className="p-5 flex flex-col gap-4">
              {accounts.length === 0 ? (
                <p className="text-sm text-slate-400">
                  No verified cloud accounts. Add one in Settings → Cloud Accounts.
                </p>
              ) : (
                <div className="flex flex-col gap-2">
                  {accounts.map((acc) => (
                    <button key={acc.id} onClick={() => setSelectedAccountId(acc.id)}
                      className={`flex items-center gap-3 px-4 py-3 rounded-xl border text-left transition-all ${
                        selectedAccountId === acc.id
                          ? 'border-indigo-500/60 bg-indigo-500/10 text-slate-200'
                          : 'border-slate-700 text-slate-400 hover:border-slate-500'
                      }`}>
                      <div className={`w-4 h-4 rounded-full border-2 flex items-center justify-center ${
                        selectedAccountId === acc.id ? 'border-indigo-400' : 'border-slate-600'
                      }`}>
                        {selectedAccountId === acc.id && <div className="w-2 h-2 rounded-full bg-indigo-400" />}
                      </div>
                      <div>
                        <div className="text-sm font-medium">{acc.display_name}</div>
                        <div className="text-xs text-slate-500">{acc.provider} · {acc.region}</div>
                      </div>
                    </button>
                  ))}
                </div>
              )}
              {selectedAccountId && (
                <button onClick={() => setShowPermModal(true)}
                  className="flex items-center gap-1.5 text-xs text-indigo-400/70 hover:text-indigo-400 transition-colors w-fit">
                  <Shield className="w-3 h-3" />
                  View required permissions
                </button>
              )}
              <button onClick={goToPreflight} disabled={!selectedAccountId}
                className="mt-1 w-full py-2.5 rounded-xl text-sm font-medium bg-indigo-600 text-white hover:bg-indigo-500 disabled:opacity-40 disabled:cursor-not-allowed transition-colors">
                Next →
              </button>
            </div>
          )}

          {/* Step: preflight */}
          {step === 'preflight' && (
            <div className="p-5 flex flex-col gap-4">
              <button onClick={() => setStep('account')}
                className="flex items-center gap-1 text-xs text-slate-400 hover:text-slate-200 transition-colors w-fit">
                <ChevronLeft className="w-3.5 h-3.5" /> Back
              </button>

              {preflightLoading && (
                <div className="flex items-center gap-2 text-sm text-slate-400">
                  <Loader2 className="w-4 h-4 animate-spin" />
                  Checking IAM permissions…
                </div>
              )}

              {preflight && !preflightLoading && (
                <div className="space-y-3">
                  {preflight.skipped ? (
                    <div className="flex items-start gap-2 px-3 py-2.5 rounded-lg text-xs text-amber-300"
                      style={{ background: 'rgba(245,158,11,0.08)', border: '1px solid rgba(245,158,11,0.2)' }}>
                      <AlertCircle className="w-3.5 h-3.5 shrink-0 mt-0.5 text-amber-400" />
                      <span>Could not verify permissions — <code>iam:SimulatePrincipalPolicy</code> not authorized. Proceeding anyway; deploy may fail if permissions are insufficient.</span>
                    </div>
                  ) : preflight.passed ? (
                    <div className="flex items-center gap-2 px-3 py-2.5 rounded-lg text-xs text-emerald-300"
                      style={{ background: 'rgba(52,211,153,0.08)', border: '1px solid rgba(52,211,153,0.2)' }}>
                      <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" />
                      All required permissions verified
                    </div>
                  ) : (
                    <div className="flex items-start gap-2 px-3 py-2.5 rounded-lg text-xs text-rose-300"
                      style={{ background: 'rgba(251,113,133,0.08)', border: '1px solid rgba(251,113,133,0.2)' }}>
                      <XCircle className="w-3.5 h-3.5 shrink-0 mt-0.5 text-rose-400" />
                      <div>
                        <p className="font-medium mb-1">{preflight.missing.length} permission{preflight.missing.length !== 1 ? 's' : ''} missing</p>
                        <div className="space-y-0.5 font-mono text-[10px] text-rose-400/80 max-h-24 overflow-y-auto">
                          {preflight.missing.map((a) => <div key={a}>✗ {a}</div>)}
                        </div>
                      </div>
                    </div>
                  )}

                  {preflight.checked.length > 0 && !preflight.skipped && (
                    <details className="text-xs">
                      <summary className="text-slate-500 cursor-pointer hover:text-slate-300 transition-colors">
                        View all {preflight.checked.length} checks
                      </summary>
                      <div className="mt-2 max-h-40 overflow-y-auto space-y-0.5 font-mono text-[10px]">
                        {preflight.checked.map((c) => (
                          <div key={c.action} className={`flex items-center gap-1.5 ${c.allowed ? 'text-emerald-400/70' : 'text-rose-400'}`}>
                            {c.allowed ? <CheckCircle2 className="w-2.5 h-2.5 shrink-0" /> : <XCircle className="w-2.5 h-2.5 shrink-0" />}
                            {c.action}
                          </div>
                        ))}
                      </div>
                    </details>
                  )}

                  <div className="flex gap-2">
                    {!preflight.passed && !preflight.skipped && (
                      <button onClick={() => setShowPermModal(true)}
                        className="flex items-center gap-1 px-3 py-2 rounded-lg text-xs text-indigo-300 border border-indigo-500/30 hover:border-indigo-500/60 transition-all">
                        <Shield className="w-3 h-3" /> Fix permissions
                      </button>
                    )}
                    {!preflight.passed && !preflight.skipped && (
                      <button onClick={runPreflightCheck} disabled={preflightLoading}
                        className="flex items-center gap-1 px-3 py-2 rounded-lg text-xs text-slate-400 border border-slate-700 hover:border-slate-500 transition-all">
                        Re-check
                      </button>
                    )}
                  </div>
                </div>
              )}

              <button onClick={goToCost} disabled={!canProceedFromPreflight}
                className="mt-1 w-full py-2.5 rounded-xl text-sm font-medium bg-indigo-600 text-white hover:bg-indigo-500 disabled:opacity-40 disabled:cursor-not-allowed transition-colors">
                {preflight?.passed ? 'Next →' : preflight?.skipped ? 'Proceed anyway →' : 'Next →'}
              </button>
            </div>
          )}

          {/* Step: cost */}
          {step === 'cost' && (
            <div className="p-5 flex flex-col gap-4">
              <button onClick={() => setStep('preflight')}
                className="flex items-center gap-1 text-xs text-slate-400 hover:text-slate-200 transition-colors w-fit">
                <ChevronLeft className="w-3.5 h-3.5" /> Back
              </button>
              {costLoading && (
                <div className="flex items-center gap-2 text-sm text-slate-400">
                  <Loader2 className="w-4 h-4 animate-spin" />
                  Calculating cost estimate…
                </div>
              )}
              {costError && <p className="text-sm text-amber-400">{costError}</p>}
              {costEstimate && Object.keys(costEstimate.tier_matrix).length > 0 && (
                <div className="flex flex-col gap-2">
                  {Object.entries(costEstimate.tier_matrix).map(([tier, info]) => (
                    <div key={tier} className="flex items-center justify-between px-3 py-2.5 rounded-lg"
                      style={{ background: 'rgba(255,255,255,0.04)', border: '1px solid var(--border)' }}>
                      <span className="text-sm capitalize text-slate-300">{tier}</span>
                      <span className="text-sm font-semibold text-indigo-300">${info.monthly_usd}/mo</span>
                    </div>
                  ))}
                  {costEstimate.summary_text && (
                    <p className="text-xs text-slate-400 mt-1">{costEstimate.summary_text}</p>
                  )}
                </div>
              )}
              {!costLoading && !costEstimate && !costError && (
                <p className="text-sm text-slate-400">No estimate available. You can still deploy.</p>
              )}
              <button onClick={startDeploy} disabled={costLoading}
                className="mt-2 w-full py-2.5 rounded-xl text-sm font-medium bg-emerald-600 text-white hover:bg-emerald-500 disabled:opacity-40 disabled:cursor-not-allowed transition-colors">
                Deploy →
              </button>
            </div>
          )}

          {/* Step: deploying */}
          {step === 'deploying' && (
            <div className="p-5 flex flex-col gap-3">
              <div className="flex items-center gap-2 text-sm text-indigo-300">
                <Loader2 className="w-4 h-4 animate-spin" />
                Deploying to cloud…
              </div>
              <div className="rounded-lg p-3 font-mono text-xs text-slate-400 max-h-48 overflow-y-auto"
                style={{ background: 'rgba(0,0,0,0.3)' }}>
                {deployLogs.map((l, i) => <div key={i}>{l.text}</div>)}
                {deployLogs.length === 0 && <div className="text-slate-500">Queued…</div>}
              </div>
              {deployError && <p className="text-xs text-rose-400">{deployError}</p>}
            </div>
          )}

          {/* Step: success */}
          {step === 'success' && (
            <div className="p-5 flex flex-col items-center gap-4 text-center">
              <div className="w-12 h-12 rounded-full bg-emerald-500/10 flex items-center justify-center">
                <Check className="w-6 h-6 text-emerald-400" />
              </div>
              <div>
                <h3 className="text-base font-semibold text-slate-200 mb-1">Your app is live!</h3>
                {liveUrl && <p className="text-xs text-slate-400 font-mono break-all">{liveUrl}</p>}
              </div>
              <div className="flex gap-2">
                {liveUrl && (
                  <>
                    <button onClick={copyUrl}
                      className="flex items-center gap-1.5 px-3 py-2 rounded-lg text-xs font-medium text-slate-300 border border-slate-700 hover:border-slate-500 transition-all">
                      <Copy className="w-3.5 h-3.5" />
                      {copied ? 'Copied!' : 'Copy link'}
                    </button>
                    <a href={liveUrl} target="_blank" rel="noreferrer"
                      className="flex items-center gap-1.5 px-3 py-2 rounded-lg text-xs font-medium text-emerald-300 border border-emerald-500/30 hover:border-emerald-500/60 transition-all">
                      <ExternalLink className="w-3.5 h-3.5" />
                      Open
                    </a>
                  </>
                )}
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Permission template modal (z-index above deploy modal) */}
      <PermissionTemplateModal
        appType="container"
        roleArn={selectedAccount?.role_arn ?? null}
        open={showPermModal}
        onClose={() => setShowPermModal(false)}
      />
    </>
  );
}
