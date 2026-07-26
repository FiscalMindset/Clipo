/**
 * Browser notification helpers for completion alerts.
 *
 * Permission is only requested on a user gesture (toggle change or button click).
 * Returns the resulting permission state as a string.
 */

export function supportsNotifications() {
  return typeof window !== 'undefined' && 'Notification' in window;
}

/**
 * Request notification permission. Must be called from a user gesture
 * (click handler) for browsers to show the permission prompt.
 * Returns 'granted', 'denied', or 'unsupported'.
 */
export async function requestNotificationPermission() {
  if (!supportsNotifications()) return 'unsupported';
  // Already granted or denied — just return it.
  if (Notification.permission !== 'default') return Notification.permission;
  // requestPermission() must be called from a user gesture.
  return Notification.requestPermission();
}

/**
 * Check whether notifications are currently enabled (no permission prompt).
 */
export function notificationsEnabled() {
  return supportsNotifications() && Notification.permission === 'granted';
}

/**
 * Show a desktop notification that a job has completed.
 * Does NOT request permission — only shows if already granted.
 */
export function showCompletionNotification(jobId, jobName) {
  if (!supportsNotifications() || Notification.permission !== 'granted') return false;
  const title = 'Clipo AI — Export Ready';
  const body = jobName
    ? `"${jobName}" is ready to review and download.`
    : 'Your clip generation is complete. Open the results to review and download.';
  try {
    new Notification(title, { body, tag: `clipo-complete-${jobId}` });
    return true;
  } catch {
    // Swallowed — e.g. service worker context.
    return false;
  }
}
