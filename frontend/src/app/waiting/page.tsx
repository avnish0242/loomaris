'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { Clock, RefreshCw, LogOut, ArrowLeft } from 'lucide-react';
import { clearToken, consumeAuthHash, getToken, setToken } from '@/lib/auth';
import { getMe } from '@/lib/api';

export default function WaitingPage() {
  const router = useRouter();
  const [checking, setChecking] = useState(false);
  const [orgName, setOrgName] = useState<string | null>(null);

  useEffect(() => {
    const auth = consumeAuthHash();
    if (auth) setToken(auth.token);
    if (!getToken()) { router.replace('/login'); return; }

    getMe()
      .then(me => {
        if (me.membership_status === 'active') {
          router.replace('/chat');
        }
        // Show which org they're waiting on (org will be null when pending)
      })
      .catch(() => router.replace('/login'));
  }, [router]);

  const handleCheck = async () => {
    setChecking(true);
    try {
      const me = await getMe();
      if (me.membership_status === 'active') {
        router.replace('/chat');
      }
    } catch {
      router.replace('/login');
    } finally {
      setChecking(false);
    }
  };

  return (
    <div className="min-h-screen mesh-bg dot-grid flex flex-col items-center justify-center px-6">
      <div className="w-full max-w-sm text-center">

        {/* Icon */}
        <div className="inline-flex items-center justify-center w-16 h-16 rounded-2xl
          bg-amber-500/10 border border-amber-500/20 mb-6
          shadow-[0_0_40px_rgba(245,158,11,0.1)]">
          <Clock className="w-8 h-8 text-amber-400" />
        </div>

        <h1 className="text-xl font-bold text-white mb-2">Awaiting approval</h1>
        <p className="text-sm text-slate-400 leading-relaxed mb-2">
          Your join request is pending review.
        </p>
        <p className="text-xs text-slate-500 leading-relaxed mb-8">
          The org admin will be notified and can approve or reject your request.
          You&apos;ll have full access as soon as they approve.
        </p>

        {/* Status indicator */}
        <div className="flex items-center justify-center gap-2 mb-8">
          <span className="w-2 h-2 rounded-full bg-amber-400 animate-pulse" />
          <span className="text-xs text-amber-400/80 font-mono">pending approval</span>
        </div>

        <div className="flex flex-col gap-3">
          <button
            onClick={handleCheck}
            disabled={checking}
            className="flex items-center justify-center gap-2 w-full py-2.5 px-4 rounded-xl
              text-sm font-medium transition-all disabled:opacity-50"
            style={{
              background: 'rgba(99,102,241,0.15)',
              border: '1px solid rgba(99,102,241,0.3)',
              color: '#a5b4fc',
            }}>
            {checking
              ? <><RefreshCw className="w-3.5 h-3.5 animate-spin" />Checking…</>
              : <><RefreshCw className="w-3.5 h-3.5" />Check approval status</>}
          </button>

          <button
            onClick={() => router.push('/onboarding')}
            className="flex items-center justify-center gap-2 w-full py-2.5 px-4 rounded-xl
              text-sm text-slate-500 hover:text-slate-300 transition-colors"
            style={{ border: '1px solid transparent' }}>
            <ArrowLeft className="w-3.5 h-3.5" />
            Create my own org instead
          </button>

          <button
            onClick={() => { clearToken(); router.replace('/login'); }}
            className="flex items-center justify-center gap-2 w-full py-2 text-xs
              text-slate-600 hover:text-slate-400 transition-colors">
            <LogOut className="w-3 h-3" />
            Sign out
          </button>
        </div>
      </div>
    </div>
  );
}
