'use client';

import { useParams, useSearchParams } from 'next/navigation';
import { useEffect, useRef, useState, useMemo } from 'react';
import ChatInput from '@/components/ChatInput';
import MessageBubble, { type Message } from '@/components/MessageBubble';
import CodePanel from '@/components/CodePanel';
import DeployPanel from '@/components/DeployPanel';
import { getHistory, listSessions, getApp } from '@/lib/api';
import { streamMessage } from '@/lib/stream';
import { AlertTriangle, Code2, MessageSquare } from 'lucide-react';

type PanelView = 'chat' | 'code' | 'split';

export default function ChatPage() {
  const { sessionId } = useParams<{ sessionId: string }>();
  const searchParams = useSearchParams();

  const [messages, setMessages] = useState<Message[]>([]);
  const [streaming, setStreaming] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [view, setView] = useState<PanelView>('split');
  const [appId, setAppId] = useState<string | null>(null);
  const [appSlug, setAppSlug] = useState<string | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const sentFirst = useRef(false);

  const latestAssistantContent = useMemo(() => {
    const assistantMsgs = messages.filter((m) => m.role === 'assistant' && m.content.length > 0);
    return assistantMsgs[assistantMsgs.length - 1]?.content ?? '';
  }, [messages]);

  const hasCode = latestAssistantContent.includes('```file:');

  // Load history + session metadata (for app linkage)
  useEffect(() => {
    sentFirst.current = false;
    setMessages([]);
    setError(null);
    setAppId(null);
    setAppSlug(null);

    if (searchParams.get('first')) return;

    getHistory(sessionId)
      .then((turns) => setMessages(turns.map((t) => ({ id: t.id, role: t.role, content: t.content }))))
      .catch(() => setError('Could not load history.'));
  }, [sessionId, searchParams]);

  // Resolve appId + appSlug from session list
  useEffect(() => {
    listSessions()
      .then(async (sessions) => {
        const s = sessions.find((s) => s.id === sessionId);
        if (s?.app_id) {
          setAppId(s.app_id);
          const app = await getApp(s.app_id).catch(() => null);
          if (app) setAppSlug(app.slug);
        }
      })
      .catch(() => {});
  }, [sessionId]);

  // Auto-send first message from home page
  useEffect(() => {
    const first = searchParams.get('first');
    if (!first || sentFirst.current || streaming) return;
    sentFirst.current = true;
    const url = new URL(window.location.href);
    url.searchParams.delete('first');
    window.history.replaceState(null, '', url.toString());
    send(first);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sessionId, searchParams]);

  // Scroll to bottom
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  // Auto-switch to split view when code appears
  useEffect(() => {
    if (hasCode && view === 'chat') setView('split');
  }, [hasCode, view]);

  const send = async (text: string) => {
    setStreaming(true);
    setError(null);
    setMessages((prev) => [...prev, { role: 'user', content: text }]);
    setMessages((prev) => [...prev, { role: 'assistant', content: '', streaming: true }]);

    try {
      for await (const event of streamMessage(sessionId, text)) {
        if (event.type === 'text') {
          setMessages((prev) => {
            const msgs = [...prev];
            const last = msgs[msgs.length - 1];
            if (!last || last.role !== 'assistant') return msgs;
            msgs[msgs.length - 1] = { ...last, content: last.content + event.text };
            return msgs;
          });
        } else if (event.type === 'done') {
          setMessages((prev) => {
            const msgs = [...prev];
            const last = msgs[msgs.length - 1];
            if (!last) return msgs;
            msgs[msgs.length - 1] = { ...last, streaming: false };
            return msgs;
          });
        } else if (event.type === 'error') {
          setError(event.message);
          setMessages((prev) => prev.slice(0, -1));
        }
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Stream failed');
      setMessages((prev) => prev.slice(0, -1));
    } finally {
      setStreaming(false);
    }
  };

  return (
    <div className="flex flex-col h-full overflow-hidden">

      {/* Top bar */}
      <div className="flex items-center justify-between px-5 py-2.5 border-b shrink-0"
        style={{ borderColor: 'var(--border)', background: 'var(--surface)' }}>

        {/* View toggle */}
        <div className="flex items-center gap-1 p-1 rounded-lg"
          style={{ background: 'rgba(0,0,0,0.3)', border: '1px solid var(--border)' }}>
          {([
            { id: 'chat', icon: MessageSquare, label: 'Chat' },
            { id: 'split', icon: null, label: 'Split' },
            { id: 'code', icon: Code2, label: 'Code' },
          ] as const).map((tab) => (
            <button key={tab.id} onClick={() => setView(tab.id)}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium transition-all
                ${view === tab.id
                  ? 'bg-indigo-500/20 text-indigo-300 border border-indigo-500/25'
                  : 'text-slate-500 hover:text-slate-300'
                }`}>
              {tab.id === 'split' ? (
                <span className="flex gap-0.5">
                  <span className="w-1.5 h-3 rounded-sm bg-current opacity-60" />
                  <span className="w-1.5 h-3 rounded-sm bg-current" />
                </span>
              ) : (
                tab.icon && <tab.icon className="w-3.5 h-3.5" />
              )}
              {tab.label}
            </button>
          ))}
        </div>

        {/* Status */}
        <div className="flex items-center gap-2">
          {streaming && (
            <span className="flex items-center gap-1.5 text-xs text-indigo-400">
              <span className="w-1.5 h-1.5 rounded-full bg-indigo-400 animate-pulse" />
              Generating
            </span>
          )}
          {hasCode && !streaming && (
            <span className="text-xs text-emerald-400/70 font-mono">
              {latestAssistantContent.match(/```file:/g)?.length ?? 0} file(s) generated
            </span>
          )}
        </div>
      </div>

      {/* Main content */}
      <div className="flex-1 flex overflow-hidden">

        {/* Chat pane */}
        <div className={`flex flex-col overflow-hidden transition-all duration-300
          ${view === 'code' ? 'w-0 opacity-0' : view === 'split' ? 'w-[45%]' : 'flex-1'}`}
          style={{ borderRight: view === 'split' ? '1px solid var(--border)' : undefined }}>

          {/* Messages */}
          <div className="flex-1 overflow-y-auto px-5 py-5">
            <div className="max-w-[640px] mx-auto">
              {messages.length === 0 && !streaming && !error && (
                <div className="flex flex-col items-center justify-center h-full py-16 text-center">
                  <p className="text-sm text-slate-600">Send a message to start building</p>
                </div>
              )}

              {messages.map((msg, i) => (
                <MessageBubble key={msg.id ?? i} message={msg} />
              ))}

              {error && (
                <div className="mb-5 flex items-start gap-3 px-4 py-3 rounded-xl text-sm"
                  style={{ background: 'rgba(251,113,133,0.08)', border: '1px solid rgba(251,113,133,0.2)' }}>
                  <AlertTriangle className="w-4 h-4 text-rose-400 shrink-0 mt-0.5" />
                  <span className="text-rose-300">{error}</span>
                </div>
              )}

              <div ref={bottomRef} />
            </div>
          </div>

          {/* Input */}
          <div className="px-4 pb-4 pt-2 shrink-0">
            <div className="max-w-[640px] mx-auto">
              <ChatInput onSend={send} disabled={streaming}
                placeholder={streaming ? 'Loomaris is generating…' : 'Continue the conversation…'} />
            </div>
          </div>
        </div>

        {/* Code + Deploy pane */}
        <div className={`flex flex-col overflow-hidden transition-all duration-300
          ${view === 'chat' ? 'w-0 opacity-0' : view === 'split' ? 'flex-1' : 'flex-1'}`}>
          <div className="flex-1 overflow-hidden">
            <CodePanel
              latestContent={latestAssistantContent}
              streaming={streaming}
              appId={appId ?? undefined}
              appSlug={appSlug ?? undefined}
            />
          </div>
          {appId && (
            <DeployPanel appId={appId} hasFiles={hasCode} />
          )}
        </div>
      </div>
    </div>
  );
}
