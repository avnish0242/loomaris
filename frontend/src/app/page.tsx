'use client';

import Link from 'next/link';
import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { getToken, setToken } from '@/lib/auth';
import {
  Zap, Shield, Globe, ArrowRight, Terminal, Code2,
  Sparkles, GitBranch, Mail, ExternalLink, ChevronRight
} from 'lucide-react';

// ── Animated typewriter demo ─────────────────────────────────────────────────
const PROMPTS = [
  'Build a FastAPI service with PostgreSQL and JWT auth',
  'Create a real-time dashboard with WebSockets',
  'Write a Python scraper with rate limiting and retry logic',
  'Deploy a Next.js app to AWS with auto-scaling',
  'Build a Stripe payment integration with webhooks',
];

function Typewriter() {
  const [idx, setIdx] = useState(0);
  const [displayed, setDisplayed] = useState('');
  const [deleting, setDeleting] = useState(false);

  useEffect(() => {
    const target = PROMPTS[idx];
    let timeout: ReturnType<typeof setTimeout>;

    if (!deleting && displayed.length < target.length) {
      timeout = setTimeout(() => setDisplayed(target.slice(0, displayed.length + 1)), 38);
    } else if (!deleting && displayed.length === target.length) {
      timeout = setTimeout(() => setDeleting(true), 2200);
    } else if (deleting && displayed.length > 0) {
      timeout = setTimeout(() => setDisplayed(displayed.slice(0, -1)), 18);
    } else if (deleting && displayed.length === 0) {
      setDeleting(false);
      setIdx((i) => (i + 1) % PROMPTS.length);
    }

    return () => clearTimeout(timeout);
  }, [displayed, deleting, idx]);

  return (
    <div className="flex items-start gap-3 font-mono text-sm">
      <span className="text-indigo-400 shrink-0 mt-0.5">❯</span>
      <span className="text-slate-300">
        {displayed}
        <span className="inline-block w-0.5 h-4 bg-indigo-400 ml-0.5 animate-cursor-blink align-text-bottom" />
      </span>
    </div>
  );
}

// ── Feature cards ────────────────────────────────────────────────────────────
const FEATURES = [
  {
    icon: Sparkles,
    title: 'Natural Language to Production',
    desc: 'Describe what you want. Get code that actually runs — not demo code, not prototypes, real deployable software with proper error handling and tests.',
    color: 'text-violet-400',
    bg: 'rgba(139,92,246,0.08)',
    border: 'rgba(139,92,246,0.2)',
  },
  {
    icon: Globe,
    title: 'Your Cloud, Your Rules',
    desc: "Deploy to your own AWS, Azure, or GCP account. No vendor lock-in, no surprise bills, no wondering what's running and why. It's your infrastructure.",
    color: 'text-cyan-400',
    bg: 'rgba(34,211,238,0.08)',
    border: 'rgba(34,211,238,0.2)',
  },
  {
    icon: Shield,
    title: 'Cost Guardrails Built In',
    desc: 'Set hard caps before anything deploys. Preview estimated costs before you commit. Loomaris will tell you when something is about to get expensive.',
    color: 'text-emerald-400',
    bg: 'rgba(52,211,153,0.08)',
    border: 'rgba(52,211,153,0.2)',
  },
  {
    icon: GitBranch,
    title: 'Full Git Lineage',
    desc: 'Every generation is a commit. Every deploy is traceable. Roll back with a single command. Your codebase, properly versioned, always.',
    color: 'text-rose-400',
    bg: 'rgba(251,113,133,0.08)',
    border: 'rgba(251,113,133,0.2)',
  },
  {
    icon: Zap,
    title: 'Streaming, Not Waiting',
    desc: 'Watch your app materialise token by token. No 30-second loading spinners. No staring at a blank screen hoping something happens.',
    color: 'text-amber-400',
    bg: 'rgba(251,191,36,0.08)',
    border: 'rgba(251,191,36,0.2)',
  },
  {
    icon: Code2,
    title: 'Powered by Claude',
    desc: "Built on Anthropic's Claude — the model that actually understands context, writes idiomatic code, and explains its decisions without being asked.",
    color: 'text-indigo-400',
    bg: 'rgba(129,140,248,0.08)',
    border: 'rgba(129,140,248,0.2)',
  },
];

// ── Steps ────────────────────────────────────────────────────────────────────
const STEPS = [
  { n: '01', title: 'Describe', body: 'Tell Loomaris what you want to build in plain English. Be vague, be specific — it handles both.' },
  { n: '02', title: 'Generate', body: 'Claude produces the full codebase — backend, frontend, Dockerfile, IaC. You watch it happen in real time.' },
  { n: '03', title: 'Ship', body: 'Connect your cloud account and deploy. Loomaris handles provisioning, configuration, and keeps a full audit trail.' },
];

// ── Main ─────────────────────────────────────────────────────────────────────
export default function LandingPage() {
  const router = useRouter();
  const [isAuthed, setIsAuthed] = useState(false);

  useEffect(() => {
    // Handle OAuth token from hash redirect
    const hash = window.location.hash.slice(1);
    const params = new URLSearchParams(hash);
    const token = params.get('token');
    if (token) {
      setToken(token);
      window.history.replaceState(null, '', '/');
    }
    setIsAuthed(!!getToken());
  }, []);

  return (
    <div className="min-h-screen mesh-bg dot-grid">

      {/* ── Nav ── */}
      <header className="fixed top-0 inset-x-0 z-50 border-b border-white/[0.04] bg-void/80 backdrop-blur-md">
        <div className="max-w-6xl mx-auto px-6 h-14 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div className="w-6 h-6 rounded-md bg-gradient-to-br from-indigo-500 to-violet-600 flex items-center justify-center">
              <span className="text-white text-xs font-bold">L</span>
            </div>
            <span className="text-sm font-semibold text-white">Loomaris</span>
            <span className="text-[10px] font-mono text-indigo-400/70 bg-indigo-400/10 px-1.5 py-0.5 rounded-full border border-indigo-400/20">
              Labs
            </span>
          </div>

          <nav className="hidden md:flex items-center gap-6 text-sm text-slate-400">
            <a href="#how-it-works" className="hover:text-white transition-colors">How it works</a>
            <a href="#features" className="hover:text-white transition-colors">Features</a>
            <a href="#about" className="hover:text-white transition-colors">About</a>
          </nav>

          <div>
            {isAuthed ? (
              <Link href="/chat"
                className="flex items-center gap-1.5 text-sm font-medium text-indigo-300
                  hover:text-white transition-colors bg-indigo-500/10 hover:bg-indigo-500/20
                  border border-indigo-500/20 px-4 py-1.5 rounded-lg">
                Open App <ArrowRight className="w-3.5 h-3.5" />
              </Link>
            ) : (
              <Link href="/login"
                className="text-sm font-medium text-slate-300 hover:text-white transition-colors
                  bg-white/5 hover:bg-white/10 border border-white/10 px-4 py-1.5 rounded-lg">
                Sign in
              </Link>
            )}
          </div>
        </div>
      </header>

      {/* ── Hero ── */}
      <section className="pt-40 pb-28 px-6">
        <div className="max-w-4xl mx-auto text-center">

          <div className="inline-flex items-center gap-2 bg-indigo-500/10 border border-indigo-500/20
            rounded-full px-4 py-1.5 text-xs text-indigo-300 font-medium mb-8
            opacity-0-init animate-fade-up">
            <Sparkles className="w-3 h-3" />
            Powered by Claude · Built for engineers who ship
          </div>

          <h1 className="text-5xl md:text-7xl font-bold leading-[1.08] tracking-tight mb-6
            opacity-0-init animate-fade-up animate-delay-100">
            <span className="text-white">Build anything.</span>
            <br />
            <span className="gradient-text">Ship everywhere.</span>
          </h1>

          <p className="text-lg md:text-xl text-slate-400 max-w-2xl mx-auto leading-relaxed mb-10
            opacity-0-init animate-fade-up animate-delay-200">
            Describe your app in plain English. Get production-ready code, deployed to{' '}
            <em className="text-slate-300 not-italic font-medium">your own cloud account</em> —
            no vendor lock-in, no hidden costs, no compromises.
          </p>

          <div className="flex items-center justify-center gap-4 mb-16
            opacity-0-init animate-fade-up animate-delay-300">
            <Link href={isAuthed ? '/chat' : '/login'}
              className="inline-flex items-center gap-2 px-6 py-3 rounded-xl font-semibold
                text-sm bg-gradient-to-r from-indigo-500 to-violet-600
                hover:from-indigo-400 hover:to-violet-500 text-white transition-all
                shadow-[0_0_40px_rgba(99,102,241,0.35)] hover:shadow-[0_0_60px_rgba(99,102,241,0.5)]
                hover:scale-[1.02] active:scale-[0.98]">
              {isAuthed ? 'Open Loomaris' : 'Start building — it\'s free'}
              <ArrowRight className="w-4 h-4" />
            </Link>
            <a href="#how-it-works"
              className="inline-flex items-center gap-2 px-6 py-3 rounded-xl font-medium
                text-sm text-slate-300 hover:text-white border border-white/10 hover:border-white/20
                bg-white/[0.03] hover:bg-white/[0.06] transition-all">
              See how it works
            </a>
          </div>

          {/* Terminal demo */}
          <div className="opacity-0-init animate-fade-up animate-delay-400
            max-w-2xl mx-auto glass rounded-2xl overflow-hidden
            shadow-[0_0_80px_rgba(99,102,241,0.15)]">
            <div className="flex items-center gap-2 px-4 py-3 border-b border-white/[0.06] bg-white/[0.02]">
              <div className="w-3 h-3 rounded-full bg-rose-500/70" />
              <div className="w-3 h-3 rounded-full bg-amber-500/70" />
              <div className="w-3 h-3 rounded-full bg-emerald-500/70" />
              <span className="ml-2 text-xs text-slate-500 font-mono">loomaris — chat</span>
            </div>
            <div className="px-6 py-5 bg-[#07070f]/80 min-h-[72px] flex items-center">
              <Typewriter />
            </div>
          </div>
        </div>
      </section>

      {/* ── How it works ── */}
      <section id="how-it-works" className="py-24 px-6 border-t border-white/[0.04]">
        <div className="max-w-5xl mx-auto">
          <div className="text-center mb-16">
            <p className="text-xs font-mono text-indigo-400 tracking-widest uppercase mb-3">How it works</p>
            <h2 className="text-3xl md:text-4xl font-bold text-white">Three steps. Actual software.</h2>
          </div>

          <div className="grid md:grid-cols-3 gap-6 relative">
            {/* Connecting line */}
            <div className="hidden md:block absolute top-8 left-[17%] right-[17%] h-px
              bg-gradient-to-r from-transparent via-indigo-500/30 to-transparent" />

            {STEPS.map((step) => (
              <div key={step.n} className="relative text-center group">
                <div className="inline-flex items-center justify-center w-16 h-16 rounded-2xl
                  bg-gradient-to-br from-indigo-500/20 to-violet-600/20 border border-indigo-500/20
                  font-mono font-bold text-xl text-indigo-400 mb-5
                  group-hover:border-indigo-500/40 group-hover:shadow-glow-sm transition-all">
                  {step.n}
                </div>
                <h3 className="text-lg font-semibold text-white mb-2">{step.title}</h3>
                <p className="text-sm text-slate-400 leading-relaxed">{step.body}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── Features ── */}
      <section id="features" className="py-24 px-6 border-t border-white/[0.04]">
        <div className="max-w-6xl mx-auto">
          <div className="text-center mb-16">
            <p className="text-xs font-mono text-indigo-400 tracking-widest uppercase mb-3">Features</p>
            <h2 className="text-3xl md:text-4xl font-bold text-white mb-4">
              Not a chatbot. A build system.
            </h2>
            <p className="text-slate-400 max-w-xl mx-auto">
              Everything you need to go from idea to deployed application — without the infrastructure trauma.
            </p>
          </div>

          <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-4">
            {FEATURES.map((f) => (
              <div key={f.title}
                className="group rounded-2xl p-6 border transition-all duration-300 cursor-default
                  hover:scale-[1.02] hover:-translate-y-1"
                style={{
                  background: f.bg,
                  borderColor: 'rgba(255,255,255,0.06)',
                }}>
                <div className="w-10 h-10 rounded-xl flex items-center justify-center mb-4"
                  style={{ background: f.bg, border: `1px solid ${f.border}` }}>
                  <f.icon className={`w-5 h-5 ${f.color}`} />
                </div>
                <h3 className="font-semibold text-white mb-2">{f.title}</h3>
                <p className="text-sm text-slate-400 leading-relaxed">{f.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── About ── */}
      <section id="about" className="py-24 px-6 border-t border-white/[0.04]">
        <div className="max-w-3xl mx-auto">
          <div className="text-center mb-12">
            <p className="text-xs font-mono text-indigo-400 tracking-widest uppercase mb-3">Origin story</p>
            <h2 className="text-3xl md:text-4xl font-bold text-white">
              Built by someone who got tired<br />of writing boilerplate at 2am.
            </h2>
          </div>

          <div className="glass rounded-3xl p-8 md:p-10">
            <div className="flex items-start gap-6 mb-8">
              <div className="shrink-0 w-16 h-16 rounded-2xl bg-gradient-to-br from-indigo-500
                to-violet-600 flex items-center justify-center text-2xl font-bold text-white
                shadow-[0_0_30px_rgba(99,102,241,0.4)]">
                AK
              </div>
              <div>
                <h3 className="text-xl font-bold text-white mb-1">Avnish Kumar</h3>
                <p className="text-sm text-indigo-400 font-mono">Software Engineer · Cloud Architect · Chronic Over-engineer</p>
              </div>
            </div>

            <div className="space-y-4 text-slate-300 leading-relaxed text-[15px]">
              <p>
                Loomaris started as a weekend experiment to answer a very specific question:{' '}
                <em className="text-white italic">
                  &ldquo;What if I could just describe what I want and have it actually deployed?&rdquo;
                </em>
              </p>
              <p>
                The answer, it turns out, involves a lot of Pulumi, a love-hate relationship with
                Docker, and a deep appreciation for the Anthropic API. Loomaris is the result of
                that experiment refusing to stay in a weekend.
              </p>
              <p>
                The name is made up. The mission is not: give every developer — from solo founders
                to enterprise teams — the ability to ship software as fast as they can think about it,
                without handing their infrastructure over to someone else&apos;s SaaS.
              </p>
              <p className="text-slate-400 text-sm italic">
                P.S. Yes, this platform was partially built using itself. The recursion is intentional.
              </p>
            </div>

            <div className="mt-8 pt-8 border-t border-white/[0.06] flex flex-wrap gap-4">
              <a href="mailto:avnish.dbg@gmail.com"
                className="inline-flex items-center gap-2.5 px-5 py-2.5 rounded-xl text-sm
                  font-medium text-white bg-indigo-500/15 hover:bg-indigo-500/25
                  border border-indigo-500/25 hover:border-indigo-500/40 transition-all group">
                <Mail className="w-4 h-4 text-indigo-400" />
                avnish.dbg@gmail.com
                <ExternalLink className="w-3 h-3 text-indigo-400/50 group-hover:text-indigo-400 transition-colors" />
              </a>
              <div className="inline-flex items-center gap-2.5 px-5 py-2.5 rounded-xl text-sm
                text-slate-400 bg-white/[0.03] border border-white/[0.06]">
                <Terminal className="w-4 h-4 text-slate-500" />
                <span className="font-mono">Loomaris Labs · 2026</span>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* ── CTA Banner ── */}
      <section className="py-20 px-6 border-t border-white/[0.04]">
        <div className="max-w-2xl mx-auto text-center">
          <h2 className="text-3xl font-bold text-white mb-4">
            Ready to ship something?
          </h2>
          <p className="text-slate-400 mb-8">
            Your first app is one conversation away.
          </p>
          <Link href={isAuthed ? '/chat' : '/login'}
            className="inline-flex items-center gap-2 px-8 py-4 rounded-xl font-semibold
              text-base bg-gradient-to-r from-indigo-500 to-violet-600
              hover:from-indigo-400 hover:to-violet-500 text-white transition-all
              shadow-[0_0_50px_rgba(99,102,241,0.3)] hover:shadow-[0_0_70px_rgba(99,102,241,0.5)]">
            {isAuthed ? 'Go to Loomaris' : 'Get started — free'}
            <ChevronRight className="w-5 h-5" />
          </Link>
        </div>
      </section>

      {/* ── Footer ── */}
      <footer className="border-t border-white/[0.04] py-8 px-6">
        <div className="max-w-6xl mx-auto flex flex-col md:flex-row items-center justify-between gap-4">
          <div className="flex items-center gap-2">
            <div className="w-5 h-5 rounded-md bg-gradient-to-br from-indigo-500 to-violet-600
              flex items-center justify-center">
              <span className="text-white text-[10px] font-bold">L</span>
            </div>
            <span className="text-sm text-slate-500">Loomaris Labs</span>
          </div>
          <p className="text-xs text-slate-600">
            Built with Claude API · Deployed with Pulumi · Fueled by coffee
          </p>
          <a href="mailto:avnish.dbg@gmail.com"
            className="text-xs text-slate-500 hover:text-slate-300 transition-colors">
            avnish.dbg@gmail.com
          </a>
        </div>
      </footer>
    </div>
  );
}
