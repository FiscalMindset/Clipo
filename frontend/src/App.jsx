import { useState, useCallback } from 'react';
import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { startProcessing } from './lib/api';
import { AuthProvider } from './contexts/AuthContext';
import ProtectedRoute from './components/ProtectedRoute';
import UploadScreen from './components/UploadScreen';
import ProcessingScreen from './components/ProcessingScreen';
import ResultsScreen from './components/ResultsScreen';
import ProfileScreen from './components/ProfileScreen';
import LibraryScreen from './components/LibraryScreen';
import SettingsScreen from './components/SettingsScreen';
import AuthCallback from './components/AuthCallback';

const SCREEN = {
  UPLOAD: 'upload',
  PROCESSING: 'processing',
  RESULTS: 'results',
  PROFILE: 'profile',
  LIBRARY: 'library',
  SETTINGS: 'settings',
};

function Studio() {
  const [screen, setScreen] = useState(SCREEN.UPLOAD);
  const [jobId, setJobId] = useState(null);
  const [jobDetails, setJobDetails] = useState(null);
  const [notifyWhenComplete, setNotifyWhenComplete] = useState(false);
  const [startupError, setStartupError] = useState(null);

  const handleProcessingStart = useCallback(async (newJobId, options = {}) => {
    setJobId(newJobId);
    setNotifyWhenComplete(Boolean(options.notifyWhenComplete));
    setJobDetails({
      videoName: options.videoName || 'Untitled video',
      sourceType: options.sourceType || 'file',
      createdAt: options.createdAt || new Date().toISOString(),
    });
    try {
      await startProcessing(newJobId);
      setScreen(SCREEN.PROCESSING);
    } catch (err) {
      setStartupError(err.message || 'Failed to start processing');
    }
  }, []);

  const handleComplete = useCallback(() => {
    setScreen(SCREEN.RESULTS);
  }, []);

  const handleError = useCallback((errorMsg) => {
    console.error('Pipeline error:', errorMsg);
  }, []);

  const handleReset = useCallback(() => {
    setScreen(SCREEN.UPLOAD);
    setJobId(null);
    setJobDetails(null);
    setNotifyWhenComplete(false);
  }, []);

  const handleVisitJob = useCallback((jobId, jobDetails) => {
    setJobId(jobId);
    setJobDetails(jobDetails || {});
    setScreen(SCREEN.RESULTS);
  }, []);

  const handleLeaveProcessing = useCallback(() => {
    setScreen(SCREEN.UPLOAD);
  }, []);

  const handleNavigate = useCallback((tab) => {
    switch (tab) {
      case 'create': setScreen(SCREEN.UPLOAD); break;
      case 'library': setScreen(SCREEN.LIBRARY); break;
      case 'settings': setScreen(SCREEN.SETTINGS); break;
      case 'profile': setScreen(SCREEN.PROFILE); break;
      default: setScreen(SCREEN.UPLOAD);
    }
  }, []);

  const tabMap = {
    [SCREEN.UPLOAD]: 'create',
    [SCREEN.PROCESSING]: 'create',
    [SCREEN.RESULTS]: 'create',
    [SCREEN.PROFILE]: 'profile',
    [SCREEN.LIBRARY]: 'library',
    [SCREEN.SETTINGS]: 'settings',
  };

  return (
    <>
      {startupError && (
        <div style={{
          position: 'fixed', top: 0, left: 0, right: 0, zIndex: 9999,
          background: '#dc2626', color: '#fff', padding: '12px 20px',
          display: 'flex', justifyContent: 'space-between', alignItems: 'center',
          fontFamily: 'system-ui, sans-serif',
        }}>
          <span>{startupError}</span>
          <button
            onClick={() => setStartupError(null)}
            style={{
              background: 'transparent', color: '#fff', border: 'none',
              cursor: 'pointer', fontSize: '18px', padding: '0 8px',
            }}
          >
            ✕
          </button>
        </div>
      )}
      {screen === SCREEN.UPLOAD && (
        <UploadScreen onProcessingStart={handleProcessingStart} onNavigate={handleNavigate} onVisitJob={handleVisitJob} />
      )}
      {screen === SCREEN.PROCESSING && (
        <ProcessingScreen
          jobId={jobId}
          jobDetails={jobDetails}
          notifyWhenComplete={notifyWhenComplete}
          onNotificationChange={setNotifyWhenComplete}
          onLeave={handleLeaveProcessing}
          onComplete={handleComplete}
          onError={handleError}
        />
      )}
      {screen === SCREEN.RESULTS && (
        <ResultsScreen jobId={jobId} onReset={handleReset} onNavigate={handleNavigate} />
      )}
      {screen === SCREEN.PROFILE && (
        <ProfileScreen onNavigate={handleNavigate} />
      )}
      {screen === SCREEN.LIBRARY && (
        <LibraryScreen onNavigate={handleNavigate} onVisitJob={handleVisitJob} />
      )}
      {screen === SCREEN.SETTINGS && (
        <SettingsScreen onNavigate={handleNavigate} />
      )}
    </>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <Routes>
          <Route path="/auth/callback" element={<AuthCallback />} />
          <Route
            path="*"
            element={
              <ProtectedRoute>
                <Studio />
              </ProtectedRoute>
            }
          />
        </Routes>
      </AuthProvider>
    </BrowserRouter>
  );
}
