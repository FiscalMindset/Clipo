import { useState, useEffect } from 'react';
import { getConfig } from '../lib/api';
import StudioHeader from './StudioHeader';

export default function SettingsScreen({ onNavigate }) {
  const [config, setConfig] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    getConfig()
      .then((cfg) => { setConfig(cfg); setLoading(false); })
      .catch(() => setLoading(false));
  }, []);

  return (
    <div className="dashboard-shell">
      <div className="dashboard-aura" />
      <div className="dashboard-frame">
        <StudioHeader activeTab="settings" onNavigate={onNavigate} />
        <main>
          <div className="settings-shell">
            <div className="settings-header">
              <div className="eyebrow">Settings</div>
              <h1>Application settings</h1>
              <p>View your system configuration and AI provider status.</p>
            </div>

            {loading ? (
              <div className="settings-loading"><div className="spinner spinner-lg" /><p>Loading settings...</p></div>
            ) : config ? (
              <div className="settings-grid">
                <div className="settings-card">
                  <h2>AI Provider</h2>
                  <dl>
                    <div><dt>Active provider</dt><dd>{config.ai_provider || 'None'}</dd></div>
                    <div><dt>NVIDIA configured</dt><dd>{config.nvidia_configured ? 'Yes' : 'No'}</dd></div>
                    <div><dt>Gemini configured</dt><dd>{config.gemini_configured ? 'Yes' : 'No'}</dd></div>
                  </dl>
                </div>

                <div className="settings-card">
                  <h2>System</h2>
                  <dl>
                    <div><dt>Whisper model</dt><dd>{config.whisper_model || 'base'}</dd></div>
                    <div><dt>Max upload size</dt><dd>{config.max_upload_size_gb ? `${config.max_upload_size_gb} GB` : '5 GB'}</dd></div>
                    <div><dt>Allowed formats</dt><dd>{config.allowed_formats?.join(', ') || 'MP4, MOV, MKV, AVI'}</dd></div>
                  </dl>
                </div>

                <div className="settings-card">
                  <h2>Session</h2>
                  <dl>
                    <div><dt>Processing mode</dt><dd>Local-first</dd></div>
                    <div><dt>Data storage</dt><dd>Browser localStorage</dd></div>
                  </dl>
                </div>
              </div>
            ) : (
              <div className="settings-error">
                <p>Could not load settings. The backend may not be running.</p>
              </div>
            )}
          </div>
        </main>
      </div>
    </div>
  );
}
