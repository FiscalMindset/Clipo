import { useState, useCallback } from 'react';
import { startProcessing } from './lib/api';
import { getCurrentUser, signIn, signOut, signUp } from './lib/auth';
import AuthScreen from './components/AuthScreen';
import UploadScreen from './components/UploadScreen';
import ProcessingScreen from './components/ProcessingScreen';
import ResultsScreen from './components/ResultsScreen';

// Screen states
const SCREEN = {
  UPLOAD: 'upload',
  PROCESSING: 'processing',
  RESULTS: 'results',
};

export default function App() {
  const [user, setUser] = useState(() => getCurrentUser());
  const [screen, setScreen] = useState(SCREEN.UPLOAD);
  const [jobId, setJobId] = useState(null);
  const [jobDetails, setJobDetails] = useState(null);
  const [notifyWhenComplete, setNotifyWhenComplete] = useState(false);

  const handleAuth = useCallback(async ({ mode, name, email, password }) => {
    const nextUser = mode === 'signup'
      ? signUp({ name, email, password })
      : signIn({ email, password });
    setUser(nextUser);
    return nextUser;
  }, []);

  const handleLogout = useCallback(() => {
    signOut();
    setUser(null);
    setScreen(SCREEN.UPLOAD);
    setJobId(null);
    setJobDetails(null);
    setNotifyWhenComplete(false);
  }, []);

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
      alert(err.message || 'Failed to start processing');
    }
  }, []);

  const handleComplete = useCallback(() => {
    setScreen(SCREEN.RESULTS);
  }, []);

  const handleError = useCallback((errorMsg) => {
    // Stay on processing screen — it shows the error
    console.error('Pipeline error:', errorMsg);
  }, []);

  const handleReset = useCallback(() => {
    setScreen(SCREEN.UPLOAD);
    setJobId(null);
    setJobDetails(null);
    setNotifyWhenComplete(false);
  }, []);

  const handleLeaveProcessing = useCallback(() => {
    setScreen(SCREEN.UPLOAD);
  }, []);

  if (!user) {
    return <AuthScreen onAuth={handleAuth} />;
  }

  return (
    <>
      {screen === SCREEN.UPLOAD && (
        <UploadScreen onProcessingStart={handleProcessingStart} onLogout={handleLogout} user={user} />
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
        <ResultsScreen jobId={jobId} onReset={handleReset} />
      )}
    </>
  );
}
