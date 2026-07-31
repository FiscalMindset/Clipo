import { useState, useEffect } from 'react';
import { useAuth } from '../contexts/AuthContext';
import { logout } from '../lib/auth';
import { updateProfile, getUserStats } from '../lib/api';
import StudioHeader from './StudioHeader';

export default function ProfileScreen({ onNavigate }) {
  const { user, setUser } = useAuth();
  const [editing, setEditing] = useState(false);
  const [displayName, setDisplayName] = useState('');
  const [bio, setBio] = useState('');
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [stats, setStats] = useState(null);

  useEffect(() => {
    getUserStats().then(setStats).catch(() => {});
  }, []);

  if (!user) {
    return (
      <div className="dashboard-shell">
        <div className="dashboard-aura" />
        <div className="dashboard-frame">
          <StudioHeader activeTab="profile" onNavigate={onNavigate} />
          <main><div className="profile-shell"><p>Not signed in.</p></div></main>
        </div>
      </div>
    );
  }

  function startEdit() {
    setDisplayName(user.display_name || user.name);
    setBio(user.bio || '');
    setSaved(false);
    setEditing(true);
  }

  async function handleSave() {
    setSaving(true);
    try {
      await updateProfile({ display_name: displayName, bio });
      setUser({ ...user, display_name: displayName, bio });
      setSaved(true);
      setEditing(false);
    } catch { }
    setSaving(false);
  }

  function cancelEdit() {
    setEditing(false);
    setSaved(false);
  }

  const name = user.display_name || user.name;
  const initials = name.split(' ').map(w => w[0]).join('').slice(0, 2).toUpperCase();

  return (
    <div className="dashboard-shell">
      <div className="dashboard-aura" />
      <div className="dashboard-frame">
        <StudioHeader activeTab="profile" onNavigate={onNavigate} />
        <main>
          <div className="profile-shell">
            <div className="profile-card">
              <div className="profile-avatar-wrap">
                <img className="profile-avatar" src={user.picture} alt={name} referrerPolicy="no-referrer" />
              </div>
              <div className="profile-info">
                <h1>{name}</h1>
                <p className="profile-email">{user.email}</p>
                {user.bio && <p className="profile-bio">{user.bio}</p>}
                <p className="profile-joined">Joined {new Date(user.created_at).toLocaleDateString()}</p>
              </div>
            </div>

            <div className="profile-section">
              <div className="profile-section-header">
                <h2>Edit Profile</h2>
                {!editing && (
                  <button className="generate-button" onClick={startEdit}>Edit</button>
                )}
              </div>
              {editing ? (
                <div className="profile-edit-form">
                  <label>
                    Display Name
                    <input
                      type="text"
                      value={displayName}
                      onChange={e => setDisplayName(e.target.value)}
                      maxLength={60}
                    />
                  </label>
                  <label>
                    Bio
                    <textarea
                      value={bio}
                      onChange={e => setBio(e.target.value)}
                      maxLength={300}
                      rows={3}
                      placeholder="Tell us about yourself..."
                    />
                    <span className="profile-counter">{bio.length}/300</span>
                  </label>
                  <div className="profile-edit-actions">
                    <button className="generate-button" onClick={handleSave} disabled={saving}>
                      {saving ? 'Saving…' : 'Save'}
                    </button>
                    <button className="profile-cancel" onClick={cancelEdit}>Cancel</button>
                  </div>
                </div>
              ) : saved ? (
                <p className="profile-saved-note">Profile saved!</p>
              ) : null}
            </div>

            <div className="profile-section">
              <h2>Usage</h2>
              <div className="profile-stats">
                <div className="profile-stat">
                  <span className="profile-stat-value">{stats ? stats.completed_jobs : '—'}</span>
                  <span className="profile-stat-label">Videos processed</span>
                </div>
                <div className="profile-stat">
                  <span className="profile-stat-value">{stats ? stats.total_clips : '—'}</span>
                  <span className="profile-stat-label">Clips generated</span>
                </div>
                <div className="profile-stat">
                  <span className="profile-stat-value">{stats ? stats.total_jobs : '—'}</span>
                  <span className="profile-stat-label">Total jobs</span>
                </div>
                <div className="profile-stat">
                  <span className="profile-stat-value">{stats ? stats.storage_mb + ' MB' : '—'}</span>
                  <span className="profile-stat-label">Storage used</span>
                </div>
              </div>
            </div>

            <div className="profile-section">
              <div className="profile-section-header">
                <h2>Account</h2>
              </div>
              <div className="profile-account-info">
                <div className="profile-account-row">
                  <span>Connected as</span>
                  <span>{user.email}</span>
                </div>
              </div>
              <div className="profile-actions">
                <button className="profile-signout-button" onClick={logout}>Sign out</button>
              </div>
            </div>
          </div>
        </main>
      </div>
    </div>
  );
}