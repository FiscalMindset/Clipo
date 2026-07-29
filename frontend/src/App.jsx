import { useState, useCallback } from 'react';
import { AnimatePresence } from 'framer-motion';
import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { AuthProvider } from './contexts/AuthContext';
import ProtectedRoute from './components/ProtectedRoute';
import { startProcessing, getStatus } from './lib/api';
import UploadScreen from './components/UploadScreen';
import ProcessingScreen from './components/ProcessingScreen';
import ResultsScreen from './components/ResultsScreen';
import ProfileScreen from './components/ProfileScreen';
import LibraryScreen from './components/LibraryScreen';
import SettingsScreen from './components/SettingsScreen';
import AuthCallback from './components/AuthCallback';
import InstallPrompt from './components/InstallPrompt';

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

  const handleVisitJob = useCallback(async (jobId, jobDetails) => {
    try {
      await getStatus(jobId);
    } catch {
      const key = 'clipo_job_history';
      try {
        const raw = localStorage.getItem(key);
        if (raw) {
          const history = JSON.parse(raw);
          const updated = history.filter((j) => j.jobId !== jobId);
          localStorage.setItem(key, JSON.stringify(updated));
        }
      } catch { /* ignore */ }
      setStartupError('This job is no longer available and has been removed from your history.');
      return;
    }
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

  return (
    <>
      <InstallPrompt />
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
      <AnimatePresence mode="wait">
        {screen === SCREEN.UPLOAD && (
          <motion.div
            key={SCREEN.UPLOAD}
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -4 }}
            transition={{ type: 'spring', damping: 28, stiffness: 280, mass: 0.7 }}
          >
            <UploadScreen onProcessingStart={handleProcessingStart} onNavigate={handleNavigate} onVisitJob={handleVisitJob} />
          </motion.div>
        )}
        {screen === SCREEN.PROCESSING && (
          <motion.div
            key={SCREEN.PROCESSING}
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -4 }}
            transition={{ type: 'spring', damping: 28, stiffness: 280, mass: 0.7 }}
          >
            <ProcessingScreen
              jobId={jobId}
              jobDetails={jobDetails}
              notifyWhenComplete={notifyWhenComplete}
              onNotificationChange={setNotifyWhenComplete}
              onLeave={handleLeaveProcessing}
              onComplete={handleComplete}
              onError={handleError}
            />
          </motion.div>
        )}
        {screen === SCREEN.RESULTS && (
          <motion.div
            key={SCREEN.RESULTS}
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -4 }}
            transition={{ type: 'spring', damping: 28, stiffness: 280, mass: 0.7 }}
          >
            <ResultsScreen jobId={jobId} onReset={handleReset} onNavigate={handleNavigate} />
          </motion.div>
        )}
        {screen === SCREEN.PROFILE && (
          <motion.div
            key={SCREEN.PROFILE}
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -4 }}
            transition={{ type: 'spring', damping: 28, stiffness: 280, mass: 0.7 }}
          >
            <ProfileScreen onNavigate={handleNavigate} />
          </motion.div>
        )}
        {screen === SCREEN.LIBRARY && (
          <motion.div
            key={SCREEN.LIBRARY}
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -4 }}
            transition={{ type: 'spring', damping: 28, stiffness: 280, mass: 0.7 }}
          >
            <LibraryScreen onNavigate={handleNavigate} onVisitJob={handleVisitJob} />
          </motion.div>
        )}
        {screen === SCREEN.SETTINGS && (
          <motion.div
            key={SCREEN.SETTINGS}
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -4 }}
            transition={{ type: 'spring', damping: 28, stiffness: 280, mass: 0.7 }}
          >
            <SettingsScreen onNavigate={handleNavigate} />
          </motion.div>
        )}
      </AnimatePresence>
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