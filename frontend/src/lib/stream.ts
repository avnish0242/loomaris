import { authHeaders } from './auth';

const BASE = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';

export type StreamEvent =
  | { type: 'text'; text: string }
  | { type: 'done'; turn_id: string; input_tokens: number; output_tokens: number; commit_sha: string | null; files_saved: number }
  | { type: 'files_committed'; app_id: string | null; app_slug: string; commit_sha: string; file_count: number }
  | { type: 'tool_call_pending'; turn_id: string; tool_use_id: string; tool_name: string; input: Record<string, unknown>; summary: string }
  | { type: 'tool_result'; tool_use_id: string; tool_name: string; status: 'ok' | 'error'; detail: Record<string, unknown> }
  | { type: 'error'; message: string };

async function* consumeSSE(res: Response): AsyncGenerator<StreamEvent> {
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    const message = typeof err.detail === 'string' ? err.detail : err.detail?.message ?? `HTTP ${res.status}`;
    yield { type: 'error', message };
    return;
  }

  const reader = res.body!.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split('\n');
    buffer = lines.pop() ?? ''; // keep any incomplete line

    for (const line of lines) {
      if (!line.startsWith('data: ')) continue;
      try {
        yield JSON.parse(line.slice(6)) as StreamEvent;
      } catch {
        // skip malformed events
      }
    }
  }
}

/**
 * Streams a chat message via SSE using fetch + ReadableStream.
 * EventSource only supports GET — we use fetch so we can POST.
 * Tokens appear as they're generated, eliminating perceived latency.
 */
export async function* streamMessage(
  sessionId: string,
  message: string,
): AsyncGenerator<StreamEvent> {
  const res = await fetch(
    `${BASE}/api/v1/chat/sessions/${sessionId}/message`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...authHeaders() },
      body: JSON.stringify({ message }),
    },
  );
  yield* consumeSSE(res);
}

/**
 * Approves or denies a pending simulate_app/deploy_app tool call from chat, and
 * streams Claude's grounded follow-up response the same way streamMessage does.
 */
export async function* confirmToolCall(
  sessionId: string,
  turnId: string,
  toolUseId: string,
  decision: 'approve' | 'deny',
  extra?: { cloud_account_id?: string; deploy_without_preview?: boolean },
): AsyncGenerator<StreamEvent> {
  const res = await fetch(
    `${BASE}/api/v1/chat/sessions/${sessionId}/tool-confirmations`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...authHeaders() },
      body: JSON.stringify({ turn_id: turnId, tool_use_id: toolUseId, decision, ...extra }),
    },
  );
  yield* consumeSSE(res);
}
