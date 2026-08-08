/**
 * Auth API helpers for Clipo AI.
 */

const API_BASE = import.meta.env.VITE_API_BASE || 'http://localhost:8001';

const TOKEN_KEY = 'clipo_token';

/**
 * Store the session JWT from the OAuth callback fragment.
 */
export function setSessionToken(token) {
  try {
    localStorage.setItem(TOKEN_KEY, token);
  } catch {
    // ignore
  }
}

/**
 * Get the stored session JWT, or null.
 */
export function getSessionToken() {
  try {
    return localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

/**
 * Clear the stored session JWT.
 */
export function clearSessionToken() {
  try {
    localStorage.removeItem(TOKEN_KEY);
  } catch {
    // ignore
  }
}

function authHeaders() {
  const token = getSessionToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

async function authRequest(path, body) {
  const res = await fetch(`${API_BASE}${path}`, {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || 'Could not complete that request.');
  return data;
}

export async function signUp({ name, email, password }) {
  const data = await authRequest('/auth/signup', { name, email, password });
  setSessionToken(data.token);
  return data.user;
}

export async function loginWithPassword({ email, password }) {
  const data = await authRequest('/auth/login', { email, password });
  setSessionToken(data.token);
  return data.user;
}

export function requestPasswordReset(email) {
  return authRequest('/auth/forgot-password', { email });
}

export function resetPassword(token, password) {
  return authRequest('/auth/reset-password', { token, password });
}

/**
 * Get the current authenticated user. Returns null if not logged in.
 */
export async function getCurrentUser() {
  try {
    const res = await fetch(`${API_BASE}/auth/me`, {
      credentials: 'include',
      headers: authHeaders(),
    });
    if (!res.ok) return null;
    return await res.json();
  } catch {
    return null;
  }
}

/**
 * Redirect to Google OAuth login.
 */
export function loginWithGoogle() {
  const state = window.location.origin;
  const sep = API_BASE.includes('?') ? '&' : '?';
  window.location.href = `${API_BASE}/auth/google${sep}state=${encodeURIComponent(state)}`;
}

/**
 * Log out and clear the session.
 */
export async function logout() {
  clearSessionToken();
  try {
    await fetch(`${API_BASE}/auth/logout`, {
      method: 'POST',
      credentials: 'include',
    });
  } catch {
    // ignore
  }
  window.location.href = '/';
}
