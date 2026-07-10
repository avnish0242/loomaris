const TOKEN_KEY = 'loomaris_token';

export function getToken(): string | null {
  if (typeof window === 'undefined') return null;
  return localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string): void {
  localStorage.setItem(TOKEN_KEY, token);
}

export function clearToken(): void {
  localStorage.removeItem(TOKEN_KEY);
}

export function authHeaders(): HeadersInit {
  const token = getToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

/** Parse token + next destination from the hash fragment after OAuth redirect. */
export function consumeAuthHash(): { token: string; next: string } | null {
  if (typeof window === 'undefined') return null;
  const hash = window.location.hash.slice(1);
  if (!hash) return null;
  const params = new URLSearchParams(hash);
  const token = params.get('token');
  const next = params.get('next') ?? '/chat';
  if (!token) return null;
  // Clear the fragment so the token doesn't stay in the URL bar
  window.history.replaceState(null, '', window.location.pathname + window.location.search);
  return { token, next };
}
