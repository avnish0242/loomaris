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
    is_superadmin: boolean;
    has_claude_key: boolean;
    has_cloud_account: boolean;
  };
  org: {
    id: string;
    name: string;
    slug: string;
    plan: string;
    description: string | null;
    join_policy: string;
  } | null;
  role: 'owner' | 'admin' | 'member' | null;
  membership_status: 'active' | 'pending' | 'none';
}

export interface OrgPublic {
  id: string;
  name: string;
  slug: string;
  description: string | null;
  join_policy: string;
  member_count: number;
}

export interface JoinRequest {
  user_id: string;
  email: string;
  name: string | null;
  picture: string | null;
  requested_at: string;
}

export interface OrgMember {
  user_id: string;
  email: string;
  name: string | null;
  picture: string | null;
  role: string;
  status: string;
  joined_at: string;
}

export interface CloudAccount {
  id: string;
  display_name: string;
  provider: string;
  external_id: string;   // AWS account ID
  arn: string | null;
  region: string | null;
  status: string;        // 'verified' | 'reconnect_required' | 'pending_verification'
  connection_type: string; // 'role' | 'keys'
  role_arn: string | null;
  sts_external_id: string | null;
  last_verified_at: string | null;
  created_at: string;
}

export interface CloudSetupInfo {
  loomaris_deployer_arn: string;
  sts_external_id: string;
  trust_policy: Record<string, unknown>;
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

export interface CostTier {
  monthly_usd: number;
  breakdown: string;
}

export interface CostEstimate {
  estimate_id: string;
  status: 'pending' | 'done' | 'failed';
  cloud_provider: string | null;
  tier_matrix: Record<string, CostTier>;
  summary_text: string | null;
  created_at: string;
}

// ─── Auth ─────────────────────────────────────────────────────────────────────

export const getMe = () => request<Me>('/api/v1/auth/me');
export const saveClaudeKey = (api_key: string) =>
  request<void>('/api/v1/auth/claude-key', {
    method: 'POST',
    body: JSON.stringify({ api_key }),
  });

// ─── Orgs ─────────────────────────────────────────────────────────────────────

export const listOrgs = () => request<OrgPublic[]>('/api/v1/orgs');
export const createOrg = (body: {
  name: string; slug?: string; description?: string; join_policy?: string;
}) => request<OrgPublic>('/api/v1/orgs', { method: 'POST', body: JSON.stringify(body) });

export const requestToJoin = (org_id: string) =>
  request<{ status: string; message: string }>('/api/v1/orgs/join-request', {
    method: 'POST',
    body: JSON.stringify({ org_id }),
  });

export const listJoinRequests = (org_id: string) =>
  request<JoinRequest[]>(`/api/v1/orgs/${org_id}/join-requests`);
export const approveJoinRequest = (org_id: string, user_id: string) =>
  request<{ ok: boolean }>(`/api/v1/orgs/${org_id}/join-requests/${user_id}/approve`, { method: 'POST' });
export const rejectJoinRequest = (org_id: string, user_id: string) =>
  request<{ ok: boolean }>(`/api/v1/orgs/${org_id}/join-requests/${user_id}/reject`, { method: 'POST' });

export const inviteMember = (org_id: string, email: string, role = 'member') =>
  request<{ invite_url: string }>(`/api/v1/orgs/${org_id}/invite`, {
    method: 'POST',
    body: JSON.stringify({ email, role }),
  });
export const listMembers = (org_id: string) =>
  request<OrgMember[]>(`/api/v1/orgs/${org_id}/members`);
export const removeMember = (org_id: string, user_id: string) =>
  request<{ ok: boolean }>(`/api/v1/orgs/${org_id}/members/${user_id}`, { method: 'DELETE' });

// ─── Admin ────────────────────────────────────────────────────────────────────

export const adminListOrgs = () => request<any[]>('/api/v1/admin/orgs');
export const adminSuspendOrg = (org_id: string) =>
  request<{ ok: boolean }>(`/api/v1/admin/orgs/${org_id}/suspend`, { method: 'POST' });
export const adminUnsuspendOrg = (org_id: string) =>
  request<{ ok: boolean }>(`/api/v1/admin/orgs/${org_id}/unsuspend`, { method: 'POST' });

// ─── Cloud accounts ───────────────────────────────────────────────────────────

export const listCloudAccounts = () =>
  request<CloudAccount[]>('/api/v1/cloud/accounts');

export const getCloudSetupInfo = () =>
  request<CloudSetupInfo>('/api/v1/cloud/setup-info');

export const connectCloudRoleAccount = (body: {
  display_name: string;
  role_arn: string;
  region: string;
}) => request<CloudAccount>('/api/v1/cloud/accounts', {
  method: 'POST',
  body: JSON.stringify({ provider: 'aws', ...body }),
});

export const deleteCloudAccount = (id: string) =>
  request<{ ok: boolean }>(`/api/v1/cloud/accounts/${id}`, { method: 'DELETE' });

export const verifyCloudAccount = (id: string) =>
  request<CloudAccount>(`/api/v1/cloud/accounts/${id}/verify`, { method: 'POST' });

export interface CloudDeployResponse {
  deployment_id: string;
  task_id: string;
  status: string;
}

export interface CloudDeployStatusResponse {
  status: string;
  outputs: { alb_url?: string; cdn_url?: string; api_url?: string } | null;
}

export const cloudDeploy = (appId: string, body: {
  cloud_account_id: string;
  environment?: string;
  confirm_cost?: boolean;
}) => request<CloudDeployResponse>(`/api/v1/apps/${appId}/cloud-deploy`, {
  method: 'POST',
  body: JSON.stringify({ environment: 'preview', confirm_cost: true, ...body }),
});

export const getDeploymentStatus = (appId: string, deploymentId: string) =>
  request<CloudDeployStatusResponse>(
    `/api/v1/apps/${appId}/cloud-deploy/${deploymentId}/status`
  );

export const destroyCloudDeploy = (appId: string, deploymentId: string) =>
  request<{ deployment_id: string; task_id: string; status: string }>(
    `/api/v1/apps/${appId}/cloud-deploy/${deploymentId}`, { method: 'DELETE' }
  );

// ─── Apps ─────────────────────────────────────────────────────────────────────

export const listApps = () => request<App[]>('/api/v1/apps');
export const getApp = (appId: string) => request<App>(`/api/v1/apps/${appId}`);
export const createApp = (name: string, app_type = 'web') =>
  request<App>('/api/v1/apps', { method: 'POST', body: JSON.stringify({ name, app_type }) });
export const getAppFiles = (appId: string) =>
  request<AppFiles>(`/api/v1/apps/${appId}/files`);
export const getDeployStatus = (appId: string) =>
  request<DeployStatus>(`/api/v1/apps/${appId}/deploy/status`);
export const stopPreview = (appId: string) =>
  request<{ ok: boolean }>(`/api/v1/apps/${appId}/preview`, { method: 'DELETE' });
export const triggerCostEstimate = (appId: string) =>
  request<{ estimate_id: string }>(`/api/v1/apps/${appId}/cost-estimate`, { method: 'POST' });
export const getLatestCostEstimate = (appId: string) =>
  request<CostEstimate>(`/api/v1/apps/${appId}/cost-estimate/latest`);

export interface PreflightCheck {
  action: string;
  allowed: boolean;
}

export interface PreflightResult {
  passed: boolean;
  checked: PreflightCheck[];
  missing: string[];
  skipped: boolean;
  error?: string;
}

export const runPreflight = (appId: string, cloudAccountId: string) =>
  request<PreflightResult>(`/api/v1/apps/${appId}/preflight`, {
    method: 'POST',
    body: JSON.stringify({ cloud_account_id: cloudAccountId }),
  });

export interface SimulationSession {
  session_id: string;
  status: 'building' | 'running' | 'expired' | 'failed' | 'stopped';
  url: string | null;
  expires_at: string | null;
  ttl_seconds: number;
}

export const startSimulation = (appId: string) =>
  request<SimulationSession>(`/api/v1/apps/${appId}/simulate`, { method: 'POST' });
export const getSimulationStatus = (appId: string) =>
  request<SimulationSession>(`/api/v1/apps/${appId}/simulate/status`);
export const stopSimulation = (appId: string) =>
  request<{ ok: boolean }>(`/api/v1/apps/${appId}/simulate`, { method: 'DELETE' });

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
export const getSession = (sessionId: string) => request<Session>(`/api/v1/chat/sessions/${sessionId}`);
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
