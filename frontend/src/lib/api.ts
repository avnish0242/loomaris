import { clearToken, authHeaders } from './auth';

const BASE = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...authHeaders(), ...init?.headers },
  });
  if (res.status === 401) {
    clearToken();
    if (typeof window !== 'undefined') window.location.href = '/login';
    throw new Error('Session expired. Please log in again.');
  }
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail ?? `Request failed: ${res.status}`);
  }
  return res.json() as Promise<T>;
}

// ─── Types ────────────────────────────────────────────────────────────────────

export interface App {
  id: string;
  name: string;
  slug: string;
  app_type: string;
  created_at: string;
}

export interface Session {
  id: string;
  app_id: string | null;
  title: string;
  created_at: string;
  last_active_at: string;
}

export interface Turn {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  turn_index: number;
  token_count: number | null;
  created_at: string;
}

export interface Me {
  user: {
    id: string;
    email: string;
    name: string;
    picture: string;
    has_claude_key: boolean;
    has_cloud_account: boolean;
  };
  org: { id: string; name: string; slug: string; plan: string } | null;
}

export interface CloudAccount {
  id: string;
  display_name: string;
  provider: string;
  external_id: string;
  arn: string | null;
  region: string | null;
  status: string;
  last_verified_at: string | null;
  created_at: string;
}

export interface AppFile {
  path: string;
  content: string;
}

export interface AppFiles {
  app_slug: string;
  files: AppFile[];
  recent_commits: { sha: string; message: string; date: string }[];
}

export interface DeployStatus {
  running: boolean;
  status: string;
  url: string | null;
  container_id: string | null;
  last_deployment: {
    id: string;
    status: string;
    created_at: string;
    deployed_at: string | null;
  } | null;
}

export interface CostOption {
  id: string;
  label: string;
  cost_monthly: number;
  cost_label: string;
  description: string;
  recommended: boolean;
  available: boolean;
  available_note?: string;
}

export interface CostEstimate {
  options: CostOption[];
}

// ─── Auth ─────────────────────────────────────────────────────────────────────

export const getMe = () => request<Me>('/api/v1/auth/me');
export const saveClaudeKey = (api_key: string) =>
  request<{ message: string }>('/api/v1/auth/claude-key', {
    method: 'POST',
    body: JSON.stringify({ api_key }),
  });

// ─── Cloud accounts ───────────────────────────────────────────────────────────

export const listCloudAccounts = () =>
  request<CloudAccount[]>('/api/v1/cloud/accounts');

export const connectCloudAccount = (body: {
  display_name: string;
  access_key_id: string;
  secret_access_key: string;
  region: string;
}) => request<CloudAccount>('/api/v1/cloud/accounts', { method: 'POST', body: JSON.stringify(body) });

export const deleteCloudAccount = (id: string) =>
  request<{ ok: boolean }>(`/api/v1/cloud/accounts/${id}`, { method: 'DELETE' });

export const verifyCloudAccount = (id: string) =>
  request<CloudAccount>(`/api/v1/cloud/accounts/${id}/verify`, { method: 'POST' });

// ─── Apps ─────────────────────────────────────────────────────────────────────

export const listApps = () => request<App[]>('/api/v1/apps');
export const getApp = (appId: string) => request<App>(`/api/v1/apps/${appId}`);
export const createApp = (name: string, app_type = 'web') =>
  request<App>('/api/v1/apps', { method: 'POST', body: JSON.stringify({ name, app_type }) });
export const getAppFiles = (appId: string) =>
  request<AppFiles>(`/api/v1/apps/${appId}/files`);
export const getDeployStatus = (appId: string) =>
  request<DeployStatus>(`/api/v1/apps/${appId}/deploy/status`);
export const getCostEstimate = (appId: string) =>
  request<CostEstimate>(`/api/v1/apps/${appId}/cost-estimate`);

export const downloadArchive = (appId: string, slug: string) => {
  const headers = authHeaders() as Record<string, string>;
  fetch(`${BASE}/api/v1/apps/${appId}/archive`, { headers })
    .then((r) => r.blob())
    .then((blob) => {
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `${slug}.zip`;
      a.click();
      URL.revokeObjectURL(url);
    });
};

// ─── Sessions ─────────────────────────────────────────────────────────────────

export const listSessions = () => request<Session[]>('/api/v1/chat/sessions');
export const createSession = (title?: string) =>
  request<Session>('/api/v1/chat/sessions', {
    method: 'POST',
    body: JSON.stringify({ title: title ?? 'New conversation' }),
  });
export const listAppSessions = (appId: string) =>
  request<Session[]>(`/api/v1/apps/${appId}/sessions`);
export const createAppSession = (appId: string, title?: string) =>
  request<Session>(`/api/v1/apps/${appId}/sessions`, {
    method: 'POST',
    body: JSON.stringify({ title }),
  });

// ─── Chat history ─────────────────────────────────────────────────────────────

export const getHistory = (sessionId: string) =>
  request<Turn[]>(`/api/v1/chat/sessions/${sessionId}/history`);
