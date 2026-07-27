import { useEffect, useState } from 'react';
import { getStatus } from '../lib/api';
import { showCompletionNotification, requestNotificationPermission } from '../lib/notifications';
import ClipoMark from './ClipoMark';

const POLL_INTERVAL = 2000;

function Icon({ type }) {
  const paths = {
    check: <path d="m5 12 4.2 4.2L19 6.5" />,
    play: <path d="m9 7 7 5-7 5V7Z" />,
    clock: <><circle cx="12" cy="12" r="8" /><path d="M12 8v4l2.5 1.5" /></>,
    video: <><rect x="3" y="6" width="12" height="12" rx="2" /><path d="m15 10 5-3v10l-5-3" /></>,
    bell: <><path d="M18 9a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9" /><path d="M10 21h4" /></>,
    spark: <path d="m12 3 1.7 5.3L19 10l-5.3 1.7L12 17l-1.7-5.3L5 10l5.3-1.7L12 3Z" />,
    cpu: <><rect x="4" y="4" width="16" height="16" rx="2" /><rect x="9" y="9" width="6" height="6" /><path d="M15 2v2m-6-2v2m6 16v2m-6-2v2m11-10h2M2 15h2m16-6h2M2 9h2" /></>,
    token: <path d="M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20Zm0 14a4 4 0 1 1 0-8 4 4 0 0 1 0 8Z" />,
    clip: <path d="M7 4v16m10-16v16M7 8h10M7 16h10" />,
  };
  return <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{paths[type] || paths.clock}</svg>;
}

function StepIcon({ status }) {
  const type = status === 'completed' ? 'check' : status === 'running' ? 'spark' : 'clock';
  return <span className={`processing-step-icon ${status === 'running' ? 'is-running' : ''} ${status === 'completed' ? 'is-complete' : ''}`}><Icon type={type} /></span>;
}

function formatElapsed(seconds) {
  if (seconds < 60) return `${seconds}s`;
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return `${m}m ${s}s`;
}

function AiUsageBadge({ aiUsage }) {
  if (!aiUsage) return null;
  const provider = aiUsage.provider || 'Unknown';
  const model = aiUsage.model || '';
  const tokens = aiUsage.total_tokens_est;
  return (
    <div className="ai-usage-badge">
      <span className="ai-usage-provider"><Icon type="cpu" />{provider}{model ? ` · ${model}` : ''}</span>
      {tokens != null && <span className="ai-usage-tokens"><Icon type="token" />~{tokens.toLocaleString()} tokens</span>}
    </div>
  );
}

export default function ProcessingScreen({ jobId, jobDetails, notifyWhenComplete, onNotificationChange, onLeave, onComplete, onError, onNavigate }) {
  const [steps, setSteps] = useState([]);
  const [error, setError] = useState(null);
  const [currentStep, setCurrentStep] = useState('Preparing your workspace');
  const [elapsed, setElapsed] = useState(0);
  const [aiUsage, setAiUsage] = useState(null);
  const [clipCount, setClipCount] = useState(0);
  const [notifyStatus, setNotifyStatus] = useState(notifyWhenComplete ? 'granted' : 'off');

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
        setSteps(data.steps || []);
        setCurrentStep(data.current_step || 'Working');
        if (data.ai_usage) setAiUsage(data.ai_usage);
        if (data.clips_generated != null) setClipCount(data.clips_generated);
        if (data.status === 'completed') {
          if (notifyWhenComplete) showCompletionNotification(jobId, jobDetails?.videoName);
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
        if (active) timeoutId = setTimeout(poll, POLL_INTERVAL * 2);
      }
    }
    poll();
    return () => { active = false; clearTimeout(timeoutId); };
  }, [jobId, notifyWhenComplete, jobDetails, onComplete, onError]);

  const handleNotifyToggle = async () => {
    if (notifyStatus === 'granted') {
      setNotifyStatus('off');
      onNotificationChange?.(false);
      return;
    }
    const result = await requestNotificationPermission();
    if (result === 'granted') {
      setNotifyStatus('granted');
      onNotificationChange?.(true);
    } else {
      setNotifyStatus('denied');
    }
  };

  const completedSteps = steps.filter((s) => s.status === 'completed').length;
  const totalSteps = Math.max(steps.length, 1);
  const progress = error ? 0 : Math.min(100, Math.round((completedSteps / totalSteps) * 100));
  const runningStep = steps.find((s) => s.status === 'running');
  const stageTitle = error ? 'Processing stopped' : (runningStep?.name || currentStep);
  const stageMessage = error ? error : (runningStep?.message || 'The pipeline is preparing the next task.');

  return (
    <div className="processing-shell">
      <div className="processing-aura" />
      <div className="processing-frame">
        <header className="processing-topbar">
          <button className="processing-back" onClick={onLeave} type="button"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="m15 18-6-6 6-6" /></svg> Back</button>
          <div className="processing-brand"><span><ClipoMark /></span> Clipo</div>
        </header>

        <main>
          <div className="processing-intro">
            <p>AI video processing</p>
            <h1>Processing your video</h1>
            <div>Our AI is analyzing your upload and finding the moments that deserve to be shared.</div>
          </div>

          <div className="processing-grid">
            <section className="processing-hero">
              <div className="processing-hero-top"><span className="processing-live"><i /> Live processing</span><span>{completedSteps} of {totalSteps} steps</span></div>
              <div className="processing-focus">
                <div className="processing-ring" style={{ '--progress': `${progress * 3.6}deg` }}><div><strong>{progress}%</strong><small>complete</small></div></div>
                <div className="processing-stage"><p>Current stage</p><h2>{stageTitle}</h2><span className="processing-stage-message">{stageMessage}</span></div>
              </div>

              {(aiUsage || clipCount > 0) && (
                <div className="processing-stats-row">
                  <AiUsageBadge aiUsage={aiUsage} />
                  {clipCount > 0 && <span className="processing-clip-count"><Icon type="clip" />{clipCount} clip{clipCount !== 1 ? 's' : ''} found</span>}
                </div>
              )}

              <div className="processing-progress"><div><span>Overall progress</span><b>{progress}%</b></div><div className="processing-track"><i style={{ width: `${progress}%` }} /></div></div>
              <div className="processing-times"><div><Icon type="clock" /><span>Elapsed time<strong>{formatElapsed(elapsed)}</strong></span></div></div>
            </section>

            <aside className="processing-details">
              <div className="processing-details-heading"><h2>Job details</h2><span className={error ? 'failed' : 'active'}>{error ? 'Failed' : 'Processing'}</span></div>
              <dl>
                <div><dt>Video name</dt><dd title={jobDetails?.videoName}>{jobDetails?.videoName || 'Not available'}</dd></div>
                <div><dt>Source</dt><dd>{jobDetails?.sourceType === 'youtube' ? 'YouTube URL' : 'File upload'}</dd></div>
                <div><dt>Job ID</dt><dd className="job-id">{jobId || 'Not available'}</dd></div>
              </dl>

              <button className="processing-toggle-btn" onClick={handleNotifyToggle} type="button">
                <Icon type="bell" />
                <span>
                  {notifyStatus === 'granted' ? 'Notifications enabled' : notifyStatus === 'denied' ? 'Notifications blocked by browser' : 'Notify me when ready'}
                </span>
              </button>
            </aside>
          </div>

          <section className="processing-timeline-section">
            <div><p>Pipeline</p><h2>What your AI is working through</h2></div>
            <div className="processing-timeline">
              {steps.length ? steps.map((step, index) => (
                <article className={`processing-timeline-step ${step.status}`} key={`${step.name}-${index}`}>
                  <StepIcon status={step.status} />
                  <div>
                    <h3>{step.name}</h3>
                    <p className="processing-step-message">{step.message || (step.status === 'pending' ? 'Queued — this step will begin once the previous step completes.' : 'Processing this step of your video pipeline.')}</p>
                  </div>
                  <em>{step.status}</em>
                </article>
              )) : (
                <article className="processing-timeline-step running">
                  <StepIcon status="running" />
                  <div><h3>Preparing processing pipeline</h3><p>Connecting your video to the AI workflow.</p></div>
                  <em>running</em>
                </article>
              )}
            </div>
            {error && <p className="processing-error">{error}</p>}
          </section>
          <div className="processing-banner"><span><Icon type="spark" /></span><div><strong>Hang tight.</strong><p>AI is finding your best moments.</p></div></div>
        </main>
      </div>
    </div>
  );
}
