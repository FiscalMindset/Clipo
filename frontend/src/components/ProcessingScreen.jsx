import { useEffect, useState, useMemo, useRef } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { getStatus } from '../lib/api';
import { showCompletionNotification, requestNotificationPermission, getNotificationPermission, showTestNotification } from '../lib/notifications';
import ClipoMark from './ClipoMark';

const POLL_INTERVAL = 2000;

const STEP_META = {
  'Downloading Video':   { tone: 'cyan',   icon: 'arrow',  detail: 'Pulling the source from your upload or YouTube link.',           duration: 30,   capabilities: ['HTTP resume', 'YouTube'] },
  'Extracting Audio':    { tone: 'violet', icon: 'wave',   detail: 'Separating the audio track from the video file at full quality.', duration: 20,   capabilities: ['FFmpeg'] },
  'Transcribing Video':  { tone: 'violet', icon: 'wave',   detail: 'Converting speech to text with word-level timestamps using Whisper.', duration: 180, capabilities: ['Whisper', 'GPU'] },
  'Finding Best Moments':{ tone: 'pink',   icon: 'spark',  detail: 'Identifying the most engaging clips with AI prompts.',          duration: 45,   capabilities: ['AI prompts', 'Ranking'] },
  'Generating Clips':    { tone: 'amber',  icon: 'clip',   detail: 'Cutting and exporting each moment as a standalone clip.',      duration: 90,   capabilities: ['FFmpeg', 'Captions'] },
};

const FALLBACK_META = { tone: 'violet', icon: 'spark', detail: 'Processing this step of your video pipeline.', duration: 60, capabilities: [] };

function getStepMeta(name) {
  return STEP_META[name] || FALLBACK_META;
}

const ICON_PATHS = {
  check: <path d="m5 12 4.2 4.2L19 6.5" />,
  play: <path d="m9 7 7 5-7 5V7Z" />,
  clock: <><circle cx="12" cy="12" r="8" /><path d="M12 8v4l2.5 1.5" /></>,
  arrow: <path d="M5 12h14m-5-5 5 5-5 5" />,
  wave: <path d="M4 12h2l2-6 4 12 2-7 2 3h4" />,
  spark: <path d="m12 3 1.7 5.3L19 10l-5.3 1.7L12 17l-1.7-5.3L5 10l5.3-1.7L12 3Z" />,
  cpu: <><rect x="4" y="4" width="16" height="16" rx="2" /><rect x="9" y="9" width="6" height="6" /><path d="M15 2v2m-6-2v2m6 16v2m-6-2v2m11-10h2M2 15h2m16-6h2M2 9h2" /></>,
  token: <path d="M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20Zm0 14a4 4 0 1 1 0-8 4 4 0 0 1 0 8Z" />,
  clip: <path d="M7 4v16m10-16v16M7 8h10M7 16h10" />,
  video: <><rect x="3" y="6" width="12" height="12" rx="2" /><path d="m15 10 5-3v10l-5-3" /></>,
  bell: <><path d="M18 9a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9" /><path d="M10 21h4" /></>,
  copy: <><rect x="9" y="9" width="13" height="13" rx="2" /><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" /></>,
  sparkles: <><path d="m12 3 1.5 4.5L18 8l-4.5 1.5L12 14l-1.5-4.5L6 8l4.5-1.5z" /><path d="M19 14l.8 2.2L22 17l-2.2.8L19 20l-.8-2.2L16 17l2.2-.8z" /></>,
  x: <><line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" /></>,
};

function Icon({ type, className }) {
  return <svg className={className} width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{ICON_PATHS[type] || ICON_PATHS.clock}</svg>;
}

function formatElapsed(seconds) {
  if (seconds < 60) return `${seconds}s`;
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  if (m < 60) return `${m}m ${s.toString().padStart(2, '0')}s`;
  const h = Math.floor(m / 60);
  return `${h}h ${(m % 60).toString().padStart(2, '0')}m`;
}

function AiUsageBadge({ aiUsage }) {
  if (!aiUsage) return null;
  const provider = aiUsage.provider || 'Unknown';
  const model = aiUsage.model || '';
  const tokens = aiUsage.total_tokens_est;
  return (
    <div className="processing-ai-badge tone-violet">
      <span className="processing-ai-provider">
        <Icon type="cpu" />
        <span>{provider}{model ? ` · ${model}` : ''}</span>
      </span>
      {tokens != null && (
        <span className="processing-ai-tokens">
          <Icon type="token" />
          <span>~{tokens.toLocaleString()} tokens</span>
        </span>
      )}
    </div>
  );
}

function ProgressRing({ progress, size = 152, stroke = 8 }) {
  const radius = (size - stroke) / 2;
  const circumference = 2 * Math.PI * radius;
  const offset = circumference * (1 - progress / 100);
  return (
    <div className="processing-ring-wrap" style={{ width: size, height: size }}>
      <svg width={size} height={size} className="processing-ring-svg" aria-hidden="true">
        <defs>
          <linearGradient id="processing-ring-gradient" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stopColor="#7c3aed" />
            <stop offset="100%" stopColor="#c084fc" />
          </linearGradient>
        </defs>
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke="rgba(255, 255, 255, 0.07)"
          strokeWidth={stroke}
        />
        <motion.circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke="url(#processing-ring-gradient)"
          strokeWidth={stroke}
          strokeLinecap="round"
          strokeDasharray={circumference}
          initial={{ strokeDashoffset: circumference }}
          animate={{ strokeDashoffset: offset }}
          transition={{ duration: 0.6, ease: [0.22, 1, 0.36, 1] }}
          transform={`rotate(-90 ${size / 2} ${size / 2})`}
        />
      </svg>
      <div className="processing-ring-text">
        <motion.strong
          key={progress}
          initial={{ opacity: 0, y: 6 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.3 }}
        >
          {progress}%
        </motion.strong>
        <small>complete</small>
      </div>
    </div>
  );
}

function TimelineStep({ step, index, totalSteps, stepStartedAt }) {
  const meta = getStepMeta(step.name);
  const status = step.status;
  const isRunning = status === 'running';
  const isComplete = status === 'completed';
  const isFailed = status === 'failed';
  const hasMessage = Boolean(step.message);
  const [elapsedForStep, setElapsedForStep] = useState(0);

  useEffect(() => {
    if (!isRunning || !stepStartedAt) return undefined;
    const start = stepStartedAt[index] || Date.now();
    setElapsedForStep(Math.floor((Date.now() - start) / 1000));
    const t = setInterval(() => setElapsedForStep(Math.floor((Date.now() - start) / 1000)), 1000);
    return () => clearInterval(t);
  }, [isRunning, index, stepStartedAt]);

  const durationLabel = useMemo(() => {
    const secs = meta.duration;
    if (secs < 60) return `~${secs}s`;
    return `~${Math.round(secs / 60)} min`;
  }, [meta.duration]);

  const elapsedLabel = useMemo(() => {
    if (elapsedForStep < 60) return `${elapsedForStep}s`;
    const m = Math.floor(elapsedForStep / 60);
    const s = elapsedForStep % 60;
    return `${m}m ${s.toString().padStart(2, '0')}s`;
  }, [elapsedForStep]);

  const progressPct = useMemo(() => {
    if (isComplete) return 100;
    if (isFailed) return 0;
    if (isRunning) return Math.min(95, Math.round((elapsedForStep / meta.duration) * 100));
    return 0;
  }, [isComplete, isFailed, isRunning, elapsedForStep, meta.duration]);

  const caps = meta.capabilities || [];

  const statusBadge = isRunning ? (
    <span className="processing-timeline-status is-running"><span className="processing-timeline-dot" />Running</span>
  ) : isComplete ? (
    <span className="processing-timeline-status is-complete"><Icon type="check" />Done</span>
  ) : isFailed ? (
    <span className="processing-timeline-status is-failed">Failed</span>
  ) : (
    <span className="processing-timeline-status is-pending">Queued</span>
  );

  const timePill = isRunning
    ? `${elapsedLabel} / ${durationLabel}`
    : isComplete
    ? `Took ${durationLabel.replace('~', '')}`
    : isFailed
    ? 'failed'
    : `~${durationLabel.replace('~', '')}`;

  return (
    <motion.li
      className={`processing-pipeline-card tone-${meta.tone} ${status}`}
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: index * 0.05, duration: 0.35, ease: [0.22, 1, 0.36, 1] }}
      layout
    >
      <div className="processing-pipeline-card-edge" aria-hidden="true" />
      <div className="processing-pipeline-card-inner">
        <div className="processing-pipeline-head">
          <div className="processing-pipeline-icon">
            <span className={`processing-step-icon ${isComplete ? 'is-complete' : ''} ${isRunning ? 'is-running' : ''} ${isFailed ? 'is-failed' : ''}`}>
              <AnimatePresence mode="wait" initial={false}>
                <motion.span
                  key={isComplete ? 'check' : isFailed ? 'fail' : meta.icon}
                  initial={{ scale: 0.5, opacity: 0 }}
                  animate={{ scale: 1, opacity: 1 }}
                  exit={{ scale: 0.5, opacity: 0 }}
                  transition={{ duration: 0.2 }}
                  className="processing-step-icon-inner"
                >
                  <Icon type={isComplete ? 'check' : isFailed ? 'x' : meta.icon} />
                </motion.span>
              </AnimatePresence>
            </span>
          </div>
          <div className="processing-pipeline-meta">
            <div className="processing-pipeline-title">
              <span className="processing-pipeline-num">{String(index + 1).padStart(2, '0')}</span>
              <h3>{step.name}</h3>
              {index < totalSteps - 1 && <span className="processing-pipeline-arrow" aria-hidden="true">→</span>}
            </div>
            <p className="processing-pipeline-message">{hasMessage ? step.message : meta.detail}</p>
          </div>
          <div className="processing-pipeline-side">
            {statusBadge}
            <span className="processing-pipeline-time">{timePill}</span>
          </div>
        </div>

        {(isRunning || isComplete || isFailed) && (
          <div className="processing-pipeline-progress">
            <div className="processing-pipeline-progress-track">
              <motion.span
                initial={{ width: 0 }}
                animate={{ width: `${progressPct}%` }}
                transition={{ duration: 0.5, ease: [0.22, 1, 0.36, 1] }}
              />
            </div>
            <span className="processing-pipeline-progress-pct">
              {isComplete ? '100%' : isFailed ? '0%' : `${progressPct}%`}
            </span>
          </div>
        )}

        {caps.length > 0 && (
          <div className="processing-pipeline-caps">
            {caps.map((c) => (
              <span key={c} className="processing-pipeline-cap">{c}</span>
            ))}
          </div>
        )}
      </div>
    </motion.li>
  );
}

export default function ProcessingScreen({ jobId, jobDetails, notifyWhenComplete, onNotificationChange, onLeave, onComplete, onError, onConnectionChange, onNavigate }) {
  const [steps, setSteps] = useState([]);
  const [error, setError] = useState(null);
  const [currentStep, setCurrentStep] = useState('Preparing your workspace');
  const [elapsed, setElapsed] = useState(0);
  const [aiUsage, setAiUsage] = useState(null);
  const [clipCount, setClipCount] = useState(0);
  const [notifyStatus, setNotifyStatus] = useState(() => {
    const browserPerm = getNotificationPermission();
    if (browserPerm === 'granted' && notifyWhenComplete) return 'granted';
    if (browserPerm === 'granted') return 'granted';
    if (browserPerm === 'denied') return 'denied';
    if (browserPerm === 'unsupported') return 'unsupported';
    return notifyWhenComplete ? 'granted' : 'off';
  });
  const [testResult, setTestResult] = useState(null);
  const [copied, setCopied] = useState(false);
  const stepStartedAtRef = useRef({});
  const notifyWantedRef = useRef(notifyWhenComplete);

  useEffect(() => { notifyWantedRef.current = notifyWhenComplete; }, [notifyWhenComplete]);

  // Re-sync with browser permission state when the tab regains focus
  useEffect(() => {
    const onFocus = () => {
      const browserPerm = getNotificationPermission();
      if (browserPerm === 'granted') setNotifyStatus('granted');
      else if (browserPerm === 'denied') setNotifyStatus('denied');
      else if (browserPerm === 'unsupported') setNotifyStatus('unsupported');
    };
    window.addEventListener('focus', onFocus);
    return () => window.removeEventListener('focus', onFocus);
  }, []);

  useEffect(() => {
    const started = Date.now();
    const timer = setInterval(() => setElapsed(Math.floor((Date.now() - started) / 1000)), 1000);
    return () => clearInterval(timer);
  }, []);

  useEffect(() => {
    if (!jobId) return;
    let active = true;
    let timeoutId;
    async function poll() {
      try {
        const data = await getStatus(jobId);
        if (!active) return;
        onConnectionChange?.(false);
        const incoming = data.steps || [];
        const now = Date.now();
        const map = stepStartedAtRef.current;
        incoming.forEach((s, i) => {
          if (s.status === 'running' && !map[i]) map[i] = now;
        });
        setSteps(incoming);
        setCurrentStep(data.current_step || 'Working');
        if (data.ai_usage) setAiUsage(data.ai_usage);
        if (data.clips_generated != null) setClipCount(data.clips_generated);
        if (data.status === 'completed') {
          // Use the ref so a toggle-during-processing is honored
          if (notifyWantedRef.current && getNotificationPermission() === 'granted') {
            showCompletionNotification(jobId, jobDetails?.videoName);
          }
          onComplete();
          return;
        }
        if (data.status === 'failed') {
          const message = data.error || 'Processing failed';
          setError(message);
          onError?.(message);
          return;
        }
        timeoutId = setTimeout(poll, POLL_INTERVAL);
      } catch {
        if (active) {
          // A status request can fail even before the browser emits `offline`
          // (for example, when a connection drops mid-request).
          onConnectionChange?.(true);
          timeoutId = setTimeout(poll, POLL_INTERVAL * 2);
        }
      }
    }
    poll();
    return () => { active = false; clearTimeout(timeoutId); };
  }, [jobId, notifyWhenComplete, jobDetails, onComplete, onError, onConnectionChange]);

  const handleNotifyToggle = async () => {
    setTestResult(null);
    if (notifyStatus === 'granted') {
      setNotifyStatus('off');
      notifyWantedRef.current = false;
      onNotificationChange?.(false);
      return;
    }
    if (notifyStatus === 'unsupported') return;
    const result = await requestNotificationPermission();
    if (result === 'granted') {
      setNotifyStatus('granted');
      notifyWantedRef.current = true;
      onNotificationChange?.(true);
    } else if (result === 'denied') {
      setNotifyStatus('denied');
    } else {
      setNotifyStatus('off');
    }
  };

  const handleTestNotification = () => {
    setTestResult(null);
    const res = showTestNotification();
    setTestResult(res);
    setTimeout(() => setTestResult(null), 4000);
  };

  function copyJobId() {
    if (!jobId) return;
    navigator.clipboard?.writeText(jobId).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    }).catch(() => {});
  }

  const completedSteps = steps.filter((s) => s.status === 'completed').length;
  const totalSteps = Math.max(steps.length, 1);
  const progress = error ? 0 : Math.min(100, Math.round((completedSteps / totalSteps) * 100));
  const runningStep = steps.find((s) => s.status === 'running');
  const stageTitle = error ? 'Processing stopped' : (runningStep?.name || currentStep);
  const stageMessage = error ? error : (runningStep?.message || getStepMeta(runningStep?.name || currentStep).detail);
  const stageMeta = getStepMeta(runningStep?.name || currentStep);

  const notifyTone = notifyStatus === 'granted' ? 'green'
    : notifyStatus === 'denied' ? 'red'
    : notifyStatus === 'unsupported' ? 'amber'
    : 'violet';

  const notifyHelpText = notifyStatus === 'granted'
    ? 'You will be notified when exports are ready.'
    : notifyStatus === 'denied'
    ? 'Blocked by your browser. Enable in site settings.'
    : notifyStatus === 'unsupported'
    ? 'Not available in this browser.'
    : 'Get a desktop ping when exports are ready.';

  // Estimated time remaining (rough heuristic: 60s per non-complete step)
  const remainingSteps = totalSteps - completedSteps - (runningStep ? 1 : 0);
  const estRemaining = remainingSteps > 0 ? remainingSteps * 60 + 30 : (runningStep ? 60 : 0);

  const elapsedSubtitle = useMemo(() => {
    if (elapsed === 0) return 'just started';
    if (elapsed < 60) return `${elapsed}s in`;
    return `${formatElapsed(elapsed)} elapsed`;
  }, [elapsed]);

  return (
    <div className="processing-shell">
      <div className="processing-aura" />
      <div className="processing-frame">
        <header className="processing-topbar">
          <button className="processing-back" onClick={onLeave} type="button">
            <Icon type="arrow" className="processing-back-icon" /> Back
          </button>
          <div className="processing-brand"><span><ClipoMark /></span> Clipo</div>
          {onNavigate && (
            <button className="processing-back processing-nav" onClick={() => onNavigate('library')} type="button">
              Library
            </button>
          )}
        </header>

        <main>
          <motion.section
            className="processing-intro"
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.4 }}
          >
            <div className="processing-intro-eyebrow">
              <span className="processing-intro-dot" />
              <span>AI video processing</span>
            </div>
            <h1>Processing your video</h1>
            <p>Our AI is analyzing your upload and finding the moments that deserve to be shared.</p>
          </motion.section>

          <div className="processing-grid">
            <motion.section
              className="processing-hero"
              initial={{ opacity: 0, y: 14 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.45, delay: 0.05 }}
            >
              <div className="processing-hero-top">
                <span className="processing-live"><i /> Live processing</span>
                <span className="processing-step-count">
                  <span>{completedSteps}</span>
                  <span className="processing-step-count-sep">of</span>
                  <span>{totalSteps}</span>
                  <span className="processing-step-count-label">steps</span>
                </span>
              </div>

              <div className="processing-focus">
                <ProgressRing progress={progress} />
                <div className="processing-stage">
                  <p className="processing-stage-eyebrow">Current stage</p>
                  <AnimatePresence mode="wait">
                    <motion.h2
                      key={stageTitle}
                      initial={{ opacity: 0, y: 6 }}
                      animate={{ opacity: 1, y: 0 }}
                      exit={{ opacity: 0, y: -4 }}
                      transition={{ duration: 0.3 }}
                    >
                      {stageTitle}
                    </motion.h2>
                  </AnimatePresence>
                  <AnimatePresence mode="wait">
                    <motion.span
                      key={stageMessage}
                      className="processing-stage-message"
                      initial={{ opacity: 0 }}
                      animate={{ opacity: 1 }}
                      exit={{ opacity: 0 }}
                      transition={{ duration: 0.25 }}
                    >
                      {stageMessage}
                    </motion.span>
                  </AnimatePresence>
                  {stageMeta && !error && (
                    <span className={`processing-stage-tag tone-${stageMeta.tone}`}>
                      <Icon type={stageMeta.icon} />
                      <span>Stage {String(steps.findIndex((s) => s.status === 'running') + 1 || steps.length).padStart(2, '0')}</span>
                    </span>
                  )}
                </div>
              </div>

              {(aiUsage || clipCount > 0) && (
                <div className="processing-stats-row">
                  <AiUsageBadge aiUsage={aiUsage} />
                  <AnimatePresence>
                    {clipCount > 0 && (
                      <motion.span
                        className="processing-clip-count"
                        initial={{ opacity: 0, scale: 0.9 }}
                        animate={{ opacity: 1, scale: 1 }}
                        exit={{ opacity: 0 }}
                      >
                        <Icon type="clip" />
                        <span>{clipCount} clip{clipCount !== 1 ? 's' : ''} found</span>
                      </motion.span>
                    )}
                  </AnimatePresence>
                </div>
              )}

              <div className="processing-progress">
                <div className="processing-progress-row">
                  <span>Overall progress</span>
                  <b>{progress}%</b>
                </div>
                <div className="processing-track">
                  <motion.span
                    initial={{ width: 0 }}
                    animate={{ width: `${progress}%` }}
                    transition={{ duration: 0.6, ease: [0.22, 1, 0.36, 1] }}
                  />
                </div>
              </div>

              <div className="processing-times">
                <div>
                  <Icon type="clock" />
                  <span>Elapsed time<strong>{formatElapsed(elapsed)}</strong></span>
                </div>
                <div>
                  <Icon type="sparkles" />
                  <span>Estimated remaining<strong>{estRemaining > 0 ? `~${formatElapsed(estRemaining)}` : 'Wrapping up'}</strong></span>
                </div>
                <div>
                  <Icon type="video" />
                  <span>Status<strong>{error ? 'Failed' : clipCount > 0 ? `${clipCount} ready` : 'Active'}</strong></span>
                </div>
              </div>
            </motion.section>

            <motion.aside
              className="processing-details"
              initial={{ opacity: 0, y: 14 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.45, delay: 0.1 }}
            >
              <div className="processing-details-heading">
                <div>
                  <span className="processing-details-eyebrow">Job details</span>
                  <h2>Video metadata</h2>
                </div>
                <span className={`processing-status-chip ${error ? 'is-failed' : 'is-active'}`}>
                  <span className="processing-status-dot" />
                  {error ? 'Failed' : 'Processing'}
                </span>
              </div>

              <dl className="processing-meta">
                <div>
                  <dt><Icon type="video" />Video name</dt>
                  <dd title={jobDetails?.videoName}>{jobDetails?.videoName || 'Not available'}</dd>
                </div>
                <div>
                  <dt><Icon type={jobDetails?.sourceType === 'youtube' ? 'play' : 'arrow'} />Source</dt>
                  <dd>{jobDetails?.sourceType === 'youtube' ? 'YouTube URL' : 'File upload'}</dd>
                </div>
                <div>
                  <dt><Icon type="clock" />Elapsed</dt>
                  <dd>{elapsedSubtitle}</dd>
                </div>
                <div>
                  <dt><Icon type="copy" />Job ID</dt>
                  <dd>
                    <button
                      type="button"
                      className={`processing-jobid ${copied ? 'is-copied' : ''}`}
                      onClick={copyJobId}
                      aria-label="Copy job ID"
                      title="Copy job ID"
                    >
                      <span className="processing-jobid-text">{jobId || 'Not available'}</span>
                      <Icon type={copied ? 'check' : 'copy'} />
                    </button>
                  </dd>
                </div>
              </dl>

              <div className={`processing-notify-card tone-${notifyTone}`}>
                <div className="processing-notify-head">
                  <span className="processing-notify-icon">
                    <Icon type="bell" />
                  </span>
                  <div className="processing-notify-meta">
                    <strong>Completion alerts</strong>
                    <span>{notifyHelpText}</span>
                  </div>
                  {notifyStatus !== 'unsupported' && (
                    <button
                      type="button"
                      className={`processing-toggle-btn ${notifyStatus === 'granted' ? 'is-on' : ''} ${notifyStatus === 'denied' ? 'is-blocked' : ''}`}
                      onClick={handleNotifyToggle}
                      aria-pressed={notifyStatus === 'granted'}
                      role="switch"
                      aria-label="Toggle completion notifications"
                    >
                      <span className="processing-toggle-pill">
                        <span />
                      </span>
                    </button>
                  )}
                </div>
                {notifyStatus === 'granted' && (
                  <div className="processing-notify-actions">
                    <button type="button" className="processing-test-btn" onClick={handleTestNotification}>
                      <Icon type="bell" />
                      <span>Send test</span>
                    </button>
                    <AnimatePresence>
                      {testResult && (
                        <motion.span
                          key={testResult.ok ? 'ok' : 'fail'}
                          className={`processing-test-result ${testResult.ok ? 'is-ok' : 'is-fail'}`}
                          initial={{ opacity: 0, y: 4 }}
                          animate={{ opacity: 1, y: 0 }}
                          exit={{ opacity: 0 }}
                        >
                          {testResult.ok
                            ? 'Test notification sent'
                            : testResult.reason === 'denied'
                            ? 'Browser is blocking notifications'
                            : testResult.reason === 'unsupported'
                            ? 'Not supported in this browser'
                            : 'Could not send test'}
                        </motion.span>
                      )}
                    </AnimatePresence>
                  </div>
                )}
                {notifyStatus === 'denied' && (
                  <p className="processing-notify-help">
                    Notifications are blocked by your browser. Open site settings to allow them.
                  </p>
                )}
                {notifyStatus === 'unsupported' && (
                  <p className="processing-notify-help">
                    Browser notifications are not supported in this environment.
                  </p>
                )}
              </div>
            </motion.aside>
          </div>

          <motion.section
            className="processing-timeline-section"
            initial={{ opacity: 0, y: 14 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.45, delay: 0.15 }}
          >
            <div className="processing-timeline-heading">
              <div>
                <p>Pipeline</p>
                <h2>What your AI is working through</h2>
              </div>
              <span className="processing-timeline-count">
                {completedSteps}/{totalSteps} complete
              </span>
            </div>
            <ul className="processing-timeline">
              <AnimatePresence initial={false}>
                {steps.length ? steps.map((step, index) => (
                  <TimelineStep
                    key={`${step.name}-${index}`}
                    step={step}
                    index={index}
                    totalSteps={steps.length}
                    stepStartedAt={stepStartedAtRef.current}
                  />
                )) : (
                  <motion.li
                    className="processing-timeline-step tone-violet running"
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    exit={{ opacity: 0 }}
                  >
                    <div className="processing-timeline-rail" aria-hidden="true">
                      <span className="processing-step-icon is-running"><Icon type="spark" /></span>
                    </div>
                    <div className="processing-timeline-body">
                      <div className="processing-timeline-head">
                        <span className="processing-timeline-num">--</span>
                        <h3>Preparing processing pipeline</h3>
                      </div>
                      <p className="processing-timeline-message">Connecting your video to the AI workflow.</p>
                    </div>
                  </motion.li>
                )}
              </AnimatePresence>
            </ul>
            {error && <p className="processing-error">{error}</p>}
          </motion.section>

          <motion.div
            className="processing-banner"
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.45, delay: 0.2 }}
          >
            <span><Icon type="spark" /></span>
            <div>
              <strong>Hang tight.</strong>
              <p>AI is finding your best moments.</p>
            </div>
            <span className="processing-banner-pulse" aria-hidden="true">
              <span /><span /><span />
            </span>
          </motion.div>
        </main>
      </div>
    </div>
  );
}