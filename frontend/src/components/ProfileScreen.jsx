import { useAuth } from '../contexts/AuthContext';
import { logout } from '../lib/auth';
import StudioHeader from './StudioHeader';

export default function ProfileScreen({ onNavigate }) {
  const { user } = useAuth();

  if (!user) {
    return (
      <div className="dashboard-shell">
        <div className="dashboard-aura" />
        <div className="dashboard-frame">
          <StudioHeader activeTab="profile" onNavigate={onNavigate} />
          <main>
            <div className="profile-shell">
              <p>Not signed in.</p>
            </div>
          </main>
        </div>
      </div>
    );
  }

  return (
    <div className="dashboard-shell">
      <div className="dashboard-aura" />
      <div className="dashboard-frame">
        <StudioHeader activeTab="profile" onNavigate={onNavigate} />
        <main>
          <div className="profile-shell">
            <div className="profile-card">
              <img className="profile-avatar" src={user.picture} alt={user.name} referrerPolicy="no-referrer" />
              <div className="profile-info">
                <h1>{user.name}</h1>
                <p>{user.email}</p>
              </div>
              <div className="profile-actions">
                <button className="generate-button" onClick={logout}>Sign out</button>
              </div>
            </div>
          </div>
        </main>
      </div>
    </div>
  );
}
