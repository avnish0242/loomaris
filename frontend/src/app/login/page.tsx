import Link from 'next/link';
import { ArrowLeft, Zap } from 'lucide-react';

export default function LoginPage() {
  const apiUrl = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';

  return (
    <div className="min-h-screen mesh-bg dot-grid flex flex-col items-center justify-center px-6">

      <Link href="/"
        className="absolute top-6 left-6 flex items-center gap-2 text-sm text-slate-500
          hover:text-slate-300 transition-colors">
        <ArrowLeft className="w-4 h-4" />
        Back
      </Link>

      <div className="w-full max-w-sm">

        {/* Logo */}
        <div className="text-center mb-8">
          <div className="inline-flex items-center justify-center w-14 h-14 rounded-2xl
            bg-gradient-to-br from-indigo-500 to-violet-600 mb-5
            shadow-[0_0_50px_rgba(99,102,241,0.4)]">
            <span className="text-white text-2xl font-bold">L</span>
          </div>
          <h1 className="text-2xl font-bold text-white mb-2">Welcome to Loomaris</h1>
          <p className="text-sm text-slate-400">Sign in to start building</p>
        </div>

        {/* Auth card */}
        <div className="glass rounded-2xl p-8 flex flex-col gap-3">

          {/* Google */}
          <a href={`${apiUrl}/api/v1/auth/google`}
            className="flex items-center justify-center gap-3 w-full px-4 py-3 rounded-xl
              bg-white text-gray-800 text-sm font-semibold hover:bg-gray-50
              transition-all hover:scale-[1.02] active:scale-[0.98]
              shadow-[0_4px_20px_rgba(0,0,0,0.3)]">
            <svg className="w-5 h-5 shrink-0" viewBox="0 0 24 24">
              <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"/>
              <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/>
              <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"/>
              <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"/>
            </svg>
            Continue with Google
          </a>

          {/* GitHub */}
          <a href={`${apiUrl}/api/v1/auth/github`}
            className="flex items-center justify-center gap-3 w-full px-4 py-3 rounded-xl
              text-white text-sm font-semibold hover:opacity-90
              transition-all hover:scale-[1.02] active:scale-[0.98]"
            style={{ background: '#24292e', boxShadow: '0 4px 20px rgba(0,0,0,0.4)' }}>
            <svg className="w-5 h-5 shrink-0 fill-white" viewBox="0 0 24 24">
              <path d="M12 .297c-6.63 0-12 5.373-12 12 0 5.303 3.438 9.8 8.205 11.385.6.113.82-.258.82-.577 0-.285-.01-1.04-.015-2.04-3.338.724-4.042-1.61-4.042-1.61C4.422 18.07 3.633 17.7 3.633 17.7c-1.087-.744.084-.729.084-.729 1.205.084 1.838 1.236 1.838 1.236 1.07 1.835 2.809 1.305 3.495.998.108-.776.417-1.305.76-1.605-2.665-.3-5.466-1.332-5.466-5.93 0-1.31.465-2.38 1.235-3.22-.135-.303-.54-1.523.105-3.176 0 0 1.005-.322 3.3 1.23.96-.267 1.98-.399 3-.405 1.02.006 2.04.138 3 .405 2.28-1.552 3.285-1.23 3.285-1.23.645 1.653.24 2.873.12 3.176.765.84 1.23 1.91 1.23 3.22 0 4.61-2.805 5.625-5.475 5.92.42.36.81 1.096.81 2.22 0 1.606-.015 2.896-.015 3.286 0 .315.21.69.825.57C20.565 22.092 24 17.592 24 12.297c0-6.627-5.373-12-12-12"/>
            </svg>
            Continue with GitHub
          </a>

          <div className="mt-4 pt-4 border-t border-white/[0.06]">
            <div className="space-y-2.5">
              {[
                'Your code is never stored on our servers',
                'Org API key encrypted at rest (AES-256)',
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
          After signing in, your org admin will add an{' '}
          <span className="text-slate-500 font-mono">sk-ant-…</span> key to enable generation.
        </p>
      </div>

      <div className="mt-12 flex items-center gap-2 text-xs text-slate-600">
        <Zap className="w-3 h-3 text-indigo-400/50" />
        Powered by Claude · Built by Avnish Kumar
      </div>
    </div>
  );
}
