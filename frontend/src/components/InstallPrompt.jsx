import { useEffect, useState } from 'react';

/**
 * Floating "Add to Home Screen" prompt that appears when the browser fires
 * the `beforeinstallprompt` event. Hides itself once installed or dismissed.
 */
export default function InstallPrompt() {
  const [deferredPrompt, setDeferredPrompt] = useState(null);
  const [dismissed, setDismissed] = useState(false);
  const [installed, setInstalled] = useState(false);

  useEffect(() => {
    if (window.matchMedia('(display-mode: standalone)').matches) {
      setInstalled(true);
      return;
    }

    const onPrompt = (event) => {
      event.preventDefault();
      setDeferredPrompt(event);
    };
    const onInstalled = () => setInstalled(true);

    window.addEventListener('beforeinstallprompt', onPrompt);
    window.addEventListener('appinstalled', onInstalled);
    return () => {
      window.removeEventListener('beforeinstallprompt', onPrompt);
      window.removeEventListener('appinstalled', onInstalled);
    };
  }, []);

  if (installed || dismissed || !deferredPrompt) return null;

  const handleInstall = async () => {
    deferredPrompt.prompt();
    const { outcome } = await deferredPrompt.userChoice;
    if (outcome === 'accepted') setInstalled(true);
    setDeferredPrompt(null);
    setDismissed(true);
  };

  return (
    <div className="install-prompt" role="status">
      <div className="install-prompt-icon">
        <svg viewBox="0 0 64 64" width="32" height="32" aria-hidden="true">
          <defs>
            <linearGradient id="ip-g" x1="8" y1="6" x2="58" y2="58" gradientUnits="userSpaceOnUse">
              <stop offset="0%" stopColor="#c084fc" />
              <stop offset="100%" stopColor="#5b21b6" />
            </linearGradient>
          </defs>
          <rect x="4" y="4" width="56" height="56" rx="14" fill="url(#ip-g)" />
          <path d="M41 19.5c-7.18 0-13 5.82-13 13s5.82 13 13 13" stroke="white" strokeWidth="6" strokeLinecap="round" fill="none" />
          <path d="M31.5 25.5 41 32l-9.5 6.5v-13Z" fill="white" />
        </svg>
      </div>
      <div className="install-prompt-body">
        <strong>Install Clipo</strong>
        <span>Add to your home screen for one-tap access.</span>
      </div>
      <div className="install-prompt-actions">
        <button className="install-prompt-dismiss" onClick={() => setDismissed(true)} type="button">
          Not now
        </button>
        <button className="install-prompt-install" onClick={handleInstall} type="button">
          Install
        </button>
      </div>
    </div>
  );
}
