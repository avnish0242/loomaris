import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import type { Components } from 'react-markdown';
import { Copy, Check, FileCode } from 'lucide-react';
import { useState } from 'react';

export interface Message {
  id?: string;
  role: 'user' | 'assistant';
  content: string;
  streaming?: boolean;
}

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);

  const copy = () => {
    navigator.clipboard.writeText(text).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  };

  return (
    <button onClick={copy}
      className="flex items-center gap-1 text-[10px] text-slate-600 hover:text-slate-300
        transition-colors px-2 py-1 rounded hover:bg-white/[0.05]">
      {copied ? <Check className="w-3 h-3 text-emerald-400" /> : <Copy className="w-3 h-3" />}
      {copied ? 'Copied' : 'Copy'}
    </button>
  );
}

const mdComponents: Components = {
  code({ className, children }) {
    const fileMatch = /language-file:(.+)/.exec(className ?? '');
    const filePath = fileMatch?.[1];
    const isBlock = !!className;
    const content = String(children).replace(/\n$/, '');

    // File blocks are hidden from chat — shown in the Code drawer
    if (filePath) {
      return (
        <div className="inline-flex items-center gap-1.5 my-1 px-2.5 py-1 rounded-lg text-xs font-mono
          text-indigo-300/70 border border-indigo-500/15"
          style={{ background: 'rgba(99,102,241,0.06)' }}>
          <FileCode className="w-3 h-3 shrink-0" />
          {filePath}
        </div>
      );
    }

    if (isBlock) {
      return (
        <div className="my-4 rounded-xl overflow-hidden"
          style={{ border: '1px solid rgba(255,255,255,0.07)', background: '#07070f' }}>
          <div className="flex items-center justify-between px-4 py-2.5"
            style={{ borderBottom: '1px solid rgba(255,255,255,0.06)', background: 'rgba(255,255,255,0.02)' }}>
            <div className="flex items-center gap-2">
              <div className="w-2 h-2 rounded-sm bg-indigo-400/50" />
              <span className="text-xs font-mono text-slate-400">
                {className?.replace('language-', '') || 'code'}
              </span>
            </div>
            <CopyButton text={content} />
          </div>
          <pre className="overflow-x-auto">
            <code className="block p-4 text-xs font-mono text-slate-300 leading-relaxed">
              {content}
            </code>
          </pre>
        </div>
      );
    }

    return (
      <code className="font-mono text-[0.8em] bg-indigo-500/10 text-indigo-300
        px-1.5 py-0.5 rounded border border-indigo-500/15">
        {children}
      </code>
    );
  },
};

// Typing dots for empty streaming state
function TypingDots() {
  return (
    <span className="inline-flex gap-1 items-center h-4">
      {[0, 1, 2].map((i) => (
        <span key={i}
          className="w-1.5 h-1.5 rounded-full bg-indigo-400/60"
          style={{
            animation: 'bounce 1.2s ease-in-out infinite',
            animationDelay: `${i * 0.2}s`,
          }}
        />
      ))}
    </span>
  );
}

export default function MessageBubble({ message }: { message: Message }) {
  const isUser = message.role === 'user';

  if (isUser) {
    return (
      <div className="flex justify-end mb-5 animate-fade-in">
        <div className="max-w-[75%] px-4 py-3 rounded-2xl rounded-tr-md text-sm
          text-slate-100 leading-relaxed whitespace-pre-wrap"
          style={{
            background: 'rgba(99,102,241,0.15)',
            border: '1px solid rgba(129,140,248,0.2)',
          }}>
          {message.content}
        </div>
      </div>
    );
  }

  return (
    <div className="flex items-start gap-3 mb-6 animate-fade-in">
      {/* Avatar */}
      <div className="shrink-0 w-7 h-7 rounded-lg bg-gradient-to-br from-indigo-500 to-violet-600
        flex items-center justify-center mt-0.5 shadow-[0_0_12px_rgba(99,102,241,0.3)]">
        <span className="text-white text-[10px] font-bold">L</span>
      </div>

      {/* Content */}
      <div className="flex-1 min-w-0 pt-0.5">
        <div className="text-[11px] text-indigo-400/80 font-medium mb-1.5 tracking-wide">
          Loomaris
        </div>

        {message.streaming && message.content === '' ? (
          <TypingDots />
        ) : (
          <div className="prose-loomaris">
            <ReactMarkdown remarkPlugins={[remarkGfm]} components={mdComponents}>
              {message.content}
            </ReactMarkdown>
            {message.streaming && message.content.length > 0 && (
              <span className="inline-block w-0.5 h-4 bg-indigo-400 ml-0.5
                animate-cursor-blink align-text-bottom" />
            )}
          </div>
        )}
      </div>
    </div>
  );
}
