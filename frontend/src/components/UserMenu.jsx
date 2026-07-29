import { useEffect, useRef, useState } from 'react';
import { useAuth } from '../contexts/AuthContext';
import { logout } from '../lib/auth';
import ClipoMark from './ClipoMark';

/**
 * Touch-friendly user menu — single tap opens, tap outside closes, tap a
 * menu item to navigate. No mouseenter/mouseleave (hover-only dropdowns are
 * a usability disaster on phones).
 */
export default function UserMenu({ onNavigate }) {
  const { user } = useAuth();
  const [open, setOpen] = useState(false);
  const ref = useRef(null);

  useEffect(() => {
    if (!open) return;
    const handler = (e) => {
      if (ref.current && !ref.current.contains(e.target)) setOpen(false);
    };
    document.addEventListener('pointerdown', handler);
    return () => document.removeEventListener('pointerdown', handler);
  }, [open]);

  if (!user) return null;

  const handleAction = (tab) => {
    setOpen(false);
    if (tab === 'logout') {
      logout();
    } else if (onNavigate) {
      onNavigate(tab);
    }
  };

  return (
    <div className="user-menu" ref={ref}>
      <button
        className="user-avatar-button"
        onClick={() => setOpen((v) => !v)}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label="Open user menu"
      >
        <img
          className="user-avatar"
          src={user.picture}
          alt={user.name}
          referrerPolicy="no-referrer"
        />
      </button>
      {open && (
        <div className="user-dropdown" role="menu">
          <div className="user-dropdown-header">
            <img src={user.picture} alt="" referrerPolicy="no-referrer" />
            <div>
              <strong>{user.name}</strong>
              <span>{user.email}</span>
            </div>
          </div>
          <div className="user-dropdown-divider" />
          <button role="menuitem" onClick={() => handleAction('profile')}>Profile</button>
          <button role="menuitem" onClick={() => handleAction('settings')}>Settings</button>
          <div className="user-dropdown-divider" />
          <button role="menuitem" className="danger" onClick={() => handleAction('logout')}>Sign out</button>
        </div>
      )}
    </div>
  );
}
