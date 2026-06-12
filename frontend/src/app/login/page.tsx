import Link from 'next/link';
import { ArrowLeft, Zap } from 'lucide-react';

export default function LoginPage() {
  const apiUrl = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';

  return (
    <div className="min-h-screen mesh-bg dot-grid flex flex-col items-center justify-center px-6">

      {/* Back to home */}
      <Link href="/"
        className="absolute top-6 left-6 flex items-center gap-2 text-sm text-slate-500
          hover:text-slate-300 transition-colors">
        <ArrowLeft className="w-4 h-4" />
        Back
      </Link>

      {/* Card */}
      <div className="w-full max-w-sm">

        {/* Logo */}
        <div className="text-center mb-8">
          <div className="inline-flex items-center justify-center w-14 h-14 rounded-2xl
            bg-gradient-to-br from-indigo-500 to-violet-600 mb-5
            shadow-[0_0_50px_rgba(99,102,241,0.4)]">
            <span className="text-white text-2xl font-bold">L</span>
          </div>
          <h1 className="text-2xl font-bold text-white mb-2">Welcome back</h1>
          <p className="text-sm text-slate-400">Sign in to start building</p>
        </div>

        {/* Auth card */}
        <div className="glass rounded-2xl p-8">

          <a href={`${apiUrl}/api/v1/auth/google`}
            className="flex items-center justify-center gap-3 w-full px-4 py-3 rounded-xl
              bg-white text-gray-800 text-sm font-semibold hover:bg-gray-50
              transition-all hover:scale-[1.02] active:scale-[0.98]
              shadow-[0_4px_20px_rgba(0,0,0,0.3)]">
            {/* Google G */}
            <svg className="w-5 h-5 shrink-0" viewBox="0 0 24 24">
              <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"/>
              <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/>
              <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"/>
              <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"/>
            </svg>
            Continue with Google
          </a>

          <div className="mt-6 pt-6 border-t border-white/[0.06]">
            <div className="space-y-2.5">
              {[
                'Your code is never stored on our servers',
                'Anthropic API key encrypted at rest (AES-256)',
                'Deploys to your own cloud account',
              ].map((item) => (
                <div key={item} className="flex items-start gap-2.5 text-xs text-slate-500">
                  <div className="w-3.5 h-3.5 rounded-full bg-emerald-500/20 border border-emerald-500/30
                    flex items-center justify-center shrink-0 mt-0.5">
                    <div className="w-1.5 h-1.5 rounded-full bg-emerald-400" />
                  </div>
                  {item}
                </div>
              ))}
            </div>
          </div>
        </div>

        <p className="text-center text-xs text-slate-600 mt-5">
          After signing in, you&apos;ll be prompted to add your{' '}
          <span className="text-slate-500 font-mono">sk-ant-…</span> key to enable generation.
        </p>
      </div>

      {/* Bottom badge */}
      <div className="mt-12 flex items-center gap-2 text-xs text-slate-600">
        <Zap className="w-3 h-3 text-indigo-400/50" />
        Powered by Claude · Built by Avnish Kumar
      </div>
    </div>
  );
}
