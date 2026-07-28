/**
 * Auth API helpers for Clipo AI.
 */

const API_BASE = 'http://localhost:8001';

/**
 * Get the current authenticated user. Returns null if not logged in.
 */
export async function getCurrentUser() {
  try {
    const res = await fetch(`${API_BASE}/auth/me`, {
      credentials: 'include',
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
  window.location.href = `${API_BASE}/auth/google`;
}

/**
 * Log out and clear the session cookie.
 */
export async function logout() {
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
