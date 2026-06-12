'use client';

import { useRouter } from 'next/navigation';
import { useState } from 'react';
import ChatInput from '@/components/ChatInput';
import { createSession } from '@/lib/api';
import { Zap, Globe, Shield, Code2 } from 'lucide-react';

const STARTERS = [
  { icon: Code2, color: 'text-indigo-400', bg: 'rgba(99,102,241,0.08)',
    label: 'FastAPI + PostgreSQL REST API with JWT auth and async SQLAlchemy' },
  { icon: Globe, color: 'text-cyan-400', bg: 'rgba(34,211,238,0.08)',
    label: 'Real-time WebSocket server with rooms, presence, and Redis pub/sub' },
  { icon: Zap, color: 'text-amber-400', bg: 'rgba(251,191,36,0.08)',
    label: 'Next.js app with Stripe subscriptions and a customer portal' },
  { icon: Shield, color: 'text-emerald-400', bg: 'rgba(52,211,153,0.08)',
    label: 'Python CLI tool that watches a directory and syncs files to S3' },
];

export default function ChatHome() {
  const router = useRouter();
  const [loading, setLoading] = useState(false);

  const handleSend = async (text: string) => {
    setLoading(true);
    try {
      const session = await createSession(text.slice(0, 60));
      router.push(`/chat/${session.id}?first=${encodeURIComponent(text)}`);
    } catch {
      setLoading(false);
    }
  };

  return (
    <div className="flex-1 flex flex-col items-center justify-center px-8 py-16 overflow-y-auto">
      <div className="w-full max-w-2xl space-y-8">

        {/* Heading */}
        <div className="text-center">
          <div className="inline-flex items-center justify-center w-14 h-14 rounded-2xl
            bg-gradient-to-br from-indigo-500 to-violet-600 mb-5
            shadow-[0_0_40px_rgba(99,102,241,0.3)]">
            <Zap className="w-6 h-6 text-white" />
          </div>
          <h1 className="text-2xl font-bold text-white mb-2">What are we building?</h1>
          <p className="text-sm text-slate-500">
            Describe your app. Loomaris writes the code, generates the Dockerfile,
            and deploys it — all from a single prompt.
          </p>
        </div>

        {/* Input */}
        <ChatInput onSend={handleSend} disabled={loading}
          placeholder="Describe what you want to build… be as specific or vague as you like" />

        {/* Starter prompts */}
        <div>
          <p className="text-xs text-slate-600 mb-3 text-center">Or try one of these</p>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
            {STARTERS.map((s) => (
              <button key={s.label} onClick={() => handleSend(s.label)} disabled={loading}
                className="group flex items-start gap-3 p-4 rounded-xl text-left transition-all
                  hover:scale-[1.01] hover:-translate-y-0.5 disabled:opacity-40"
                style={{
                  background: s.bg,
                  border: '1px solid rgba(255,255,255,0.05)',
                }}>
                <s.icon className={`w-4 h-4 mt-0.5 shrink-0 ${s.color}`} />
                <span className="text-xs text-slate-400 group-hover:text-slate-300 leading-relaxed transition-colors">
                  {s.label}
                </span>
              </button>
            ))}
          </div>
        </div>

        <p className="text-center text-[11px] text-slate-700">
          ↵ to send · ⇧ + ↵ for new line · Powered by Claude claude-sonnet-4-6
        </p>
      </div>
    </div>
  );
}
