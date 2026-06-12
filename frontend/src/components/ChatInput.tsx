'use client';

import { useRef, useEffect, type KeyboardEvent } from 'react';
import { SendHorizontal, Loader2 } from 'lucide-react';

interface Props {
  onSend: (text: string) => void;
  disabled?: boolean;
  placeholder?: string;
}

export default function ChatInput({ onSend, disabled, placeholder }: Props) {
  const ref = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.style.height = 'auto';
    el.style.height = `${Math.min(el.scrollHeight, 180)}px`;
  });

  const handleKey = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      submit();
    }
  };

  const submit = () => {
    const el = ref.current;
    if (!el) return;
    const text = el.value.trim();
    if (!text || disabled) return;
    el.value = '';
    el.style.height = 'auto';
    onSend(text);
  };

  return (
    <>
      <style>{`
        .chat-wrap:focus-within {
          border-color: rgba(129,140,248,0.35) !important;
          box-shadow: 0 0 30px rgba(129,140,248,0.08) !important;
        }
      `}</style>

      <div className="chat-wrap rounded-2xl transition-all duration-200"
        style={{ border: '1px solid var(--border)', background: 'rgba(21,21,35,0.8)' }}>

        <textarea
          ref={ref}
          rows={1}
          disabled={disabled}
          onKeyDown={handleKey}
          placeholder={placeholder ?? 'Describe what you want to build… (↵ send · ⇧↵ newline)'}
          className="w-full resize-none bg-transparent text-sm text-slate-100
            placeholder-slate-600 outline-none leading-relaxed px-5 pt-4 pb-3
            min-h-[52px] max-h-[180px] disabled:opacity-40 disabled:cursor-not-allowed"
        />

        <div className="flex items-center justify-between px-4 pb-3">
          <span className="text-[11px] text-slate-700 font-mono">
            {disabled ? 'Generating…' : '↵ to send'}
          </span>

          <button onClick={submit} disabled={disabled}
            className="flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg text-xs font-medium
              transition-all duration-200 disabled:opacity-40 disabled:cursor-not-allowed
              bg-indigo-500/20 hover:bg-indigo-500/30 text-indigo-300
              border border-indigo-500/25 hover:border-indigo-500/40
              hover:shadow-[0_0_15px_rgba(99,102,241,0.2)]"
            aria-label="Send">
            {disabled
              ? <Loader2 className="w-3.5 h-3.5 animate-spin" />
              : <SendHorizontal className="w-3.5 h-3.5" />
            }
          </button>
        </div>
      </div>
    </>
  );
}
