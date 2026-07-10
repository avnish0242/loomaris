'use client';

import { useParams, useSearchParams } from 'next/navigation';
import { useEffect, useRef, useState } from 'react';
import ChatInput from '@/components/ChatInput';
import MessageBubble, { type Message } from '@/components/MessageBubble';
import PreviewPane from '@/components/PreviewPane';
import ActionBar from '@/components/ActionBar';
import CodeDrawer from '@/components/CodeDrawer';
import DeployModal from '@/components/DeployModal';
import { getHistory, getSession, getApp, startSimulation } from '@/lib/api';
import { streamMessage } from '@/lib/stream';
import { AlertTriangle } from 'lucide-react';

export default function ChatPage() {
  const { sessionId } = useParams<{ sessionId: string }>();
  const searchParams = useSearchParams();

  const [messages, setMessages] = useState<Message[]>([]);
  const [streaming, setStreaming] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [appId, setAppId] = useState<string | null>(null);
  const [appSlug, setAppSlug] = useState<string | null>(null);

  // UI state
  const [hasFiles, setHasFiles] = useState(false);
  const [autoPreview, setAutoPreview] = useState(false);
  const [simulationMode, setSimulationMode] = useState(false);
  const [previewKey, setPreviewKey] = useState(0);  // bump to force PreviewPane remount/rebuild
  const [codeDrawerOpen, setCodeDrawerOpen] = useState(false);
  const [deployModalOpen, setDeployModalOpen] = useState(false);

  const bottomRef = useRef<HTMLDivElement>(null);
  const sentFirst = useRef(false);

  // Load history
  useEffect(() => {
    sentFirst.current = false;
    setMessages([]);
    setError(null);
    setAppId(null);
    setAppSlug(null);
    setHasFiles(false);
    setAutoPreview(false);

    if (searchParams.get('first')) return;

    getHistory(sessionId)
      .then((turns) => setMessages(turns.map((t) => ({ id: t.id, role: t.role, content: t.content }))))
      .catch(() => setError('Could not load history.'));
  }, [sessionId, searchParams]);

  // Resolve appId + appSlug using the single-session endpoint
  useEffect(() => {
    getSession(sessionId)
      .then(async (s) => {
        if (s.app_id) {
          setAppId(s.app_id);
          const app = await getApp(s.app_id).catch(() => null);
          if (app) setAppSlug(app.slug);
        }
      })
      .catch(() => {});
  }, [sessionId]);

  // Check if existing session already has files (so action bar/preview show on reload)
  useEffect(() => {
    if (!appId) return;
    import('@/lib/api').then(({ getAppFiles }) => {
      getAppFiles(appId)
        .then((data) => { if (data.files.length > 0) setHasFiles(true); })
        .catch(() => {});
    });
  }, [appId]);

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

  const send = async (text: string) => {
    setStreaming(true);
    setError(null);
    setAutoPreview(false);
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
        } else if (event.type === 'files_committed') {
          // Files are ready — update appId/slug if the backend resolved them
          if (event.app_id && !appId) setAppId(event.app_id);
          if (event.app_slug && !appSlug) setAppSlug(event.app_slug);
          setHasFiles(true);
          // Auto-trigger preview on first generation
          setAutoPreview(true);
          setPreviewKey((k) => k + 1);
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

  const handleRebuildPreview = () => {
    setSimulationMode(false);
    setAutoPreview(false);
    setTimeout(() => {
      setAutoPreview(true);
      setPreviewKey((k) => k + 1);
    }, 50);
  };

  const handleSimulate = async () => {
    if (!appId) return;
    try {
      await startSimulation(appId);
      setSimulationMode(true);
      setAutoPreview(true);
      setPreviewKey((k) => k + 1);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to start simulation');
    }
  };

  return (
    <div className="flex flex-col h-full overflow-hidden">
      {/* Main content: chat left, preview right */}
      <div className="flex-1 flex overflow-hidden">

        {/* Chat pane */}
        <div className={`flex flex-col overflow-hidden border-r transition-all duration-300 ${
          hasFiles ? 'w-[42%]' : 'flex-1'
        }`} style={{ borderColor: 'var(--border)' }}>

          {/* Status strip */}
          {streaming && (
            <div className="flex items-center gap-1.5 px-4 py-2 text-xs text-indigo-400 border-b shrink-0"
              style={{ borderColor: 'var(--border)', background: 'rgba(99,102,241,0.06)' }}>
              <span className="w-1.5 h-1.5 rounded-full bg-indigo-400 animate-pulse" />
              Loomaris is generating…
            </div>
          )}

          {/* Messages */}
          <div className="flex-1 overflow-y-auto px-5 py-5">
            <div className="max-w-[620px] mx-auto">
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

          {/* Action bar — shown once files exist */}
          {hasFiles && appId && appSlug && (
            <ActionBar
              appId={appId}
              appSlug={appSlug}
              onSimulate={handleSimulate}
              onViewCode={() => setCodeDrawerOpen(true)}
              onDeploy={() => setDeployModalOpen(true)}
            />
          )}

          {/* Input */}
          <div className="px-4 pb-4 pt-2 shrink-0">
            <div className="max-w-[620px] mx-auto">
              <ChatInput
                onSend={send}
                disabled={streaming}
                placeholder={streaming ? 'Loomaris is generating…' : 'Continue the conversation…'}
              />
            </div>
          </div>
        </div>

        {/* Preview pane — shown only when files exist */}
        {hasFiles && appId && (
          <div className="flex-1 overflow-hidden">
            <PreviewPane
              key={previewKey}
              appId={appId}
              autoTrigger={autoPreview}
              simulationMode={simulationMode}
              onStopped={() => { setAutoPreview(false); setSimulationMode(false); }}
            />
          </div>
        )}
      </div>

      {/* Drawers & modals */}
      {appId && (
        <CodeDrawer
          appId={appId}
          open={codeDrawerOpen}
          onClose={() => setCodeDrawerOpen(false)}
        />
      )}
      {appId && (
        <DeployModal
          appId={appId}
          open={deployModalOpen}
          onClose={() => setDeployModalOpen(false)}
        />
      )}
    </div>
  );
}
