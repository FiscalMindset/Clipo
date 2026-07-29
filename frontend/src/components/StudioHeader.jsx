import { useState } from 'react';
import UserMenu from './UserMenu';
import ClipoMark from './ClipoMark';

export default function StudioHeader({ activeTab = 'create', onNavigate, rightSlot = null }) {
  const [menuOpen, setMenuOpen] = useState(false);

  const handleNav = (tab) => {
    setMenuOpen(false);
    if (onNavigate) onNavigate(tab);
  };

  return (
    <header className="app-header">
      <a className="app-logo" href="/" onClick={(e) => { e.preventDefault(); handleNav('create'); }}><span><ClipoMark /></span>Clipo</a>
      <nav className={menuOpen ? 'nav-open' : ''}>
        <a className={activeTab === 'create' ? 'active' : ''} href="#create" onClick={(e) => { e.preventDefault(); handleNav('create'); }}>Create</a>
        <a className={activeTab === 'library' ? 'active' : ''} href="#library" onClick={(e) => { e.preventDefault(); handleNav('library'); }}>Library</a>
        <a className={activeTab === 'settings' ? 'active' : ''} href="#settings" onClick={(e) => { e.preventDefault(); handleNav('settings'); }}>Settings</a>
      </nav>
      <div className="header-actions">
        <span className="local-badge"><i />Local-first</span>
        <UserMenu onNavigate={onNavigate} />
        <button className="mobile-menu-toggle" onClick={() => setMenuOpen(!menuOpen)} aria-label="Toggle menu">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" width="18" height="18">
            {menuOpen ? (
              <>
                <line x1="18" y1="6" x2="6" y2="18" />
                <line x1="6" y1="6" x2="18" y2="18" />
              </>
            ) : (
              <>
                <line x1="3" y1="6" x2="21" y2="6" />
                <line x1="3" y1="12" x2="21" y2="12" />
                <line x1="3" y1="18" x2="21" y2="18" />
              </>
            )}
          </svg>
        </button>
        {rightSlot}
      </div>
    </header>
  );
}
