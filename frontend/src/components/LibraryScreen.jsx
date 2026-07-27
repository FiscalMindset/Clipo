import { useState } from 'react';
import StudioHeader from './StudioHeader';

const JOB_HISTORY_KEY = 'clipo_job_history';
const MAX_HISTORY = 20;

function loadJobHistory() {
  try {
    const raw = localStorage.getItem(JOB_HISTORY_KEY);
    return raw ? JSON.parse(raw) : [];
  } catch {
    return [];
  }
}

function saveJobHistory(history) {
  try {
    localStorage.setItem(JOB_HISTORY_KEY, JSON.stringify(history.slice(0, MAX_HISTORY)));
  } catch { /* storage full or unavailable */ }
}

function formatJobTime(iso) {
  try {
    return new Date(iso).toLocaleString(undefined, { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' });
  } catch {
    return '';
  }
}

function formatDuration(seconds) {
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${m}:${s.toString().padStart(2, '0')}`;
}

function JobCard({ job, onVisitJob }) {
  return (
    <div className="job-history-item" onClick={() => onVisitJob?.(job.jobId, job)}>
      <div className="job-history-icon">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" width="18" height="18">
          {job.sourceType === 'youtube'
            ? <path d="M10 13a5 5 0 0 0 7.07.07l2-2a5 5 0 0 0-7.07-7.07l-1.15 1.15M14 11a5 5 0 0 0-7.07-.07l-2 2A5 5 0 0 0 12 20l1.15-1.15" />
            : <path d="M12 16V4m0 0L7.5 8.5M12 4l4.5 4.5M4 16.5v2.25A2.25 2.25 0 0 0 6.25 21h11.5A2.25 2.25 0 0 0 20 18.75V16.5" />
          }
        </svg>
      </div>
      <div className="job-history-info">
        <strong title={job.videoName}>{job.videoName}</strong>
        <span>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" width="12" height="12">
            <circle cx="12" cy="12" r="8" /><path d="M12 8v4l2.5 1.5" />
          </svg>
          {formatJobTime(job.createdAt)}
        </span>
      </div>
      <span className="job-history-id">{job.jobId?.slice(0, 8)}</span>
    </div>
  );
}

export default function LibraryScreen({ onNavigate, onVisitJob }) {
  const [jobHistory, setJobHistory] = useState(loadJobHistory);

  const clearHistory = () => {
    setJobHistory([]);
    saveJobHistory([]);
  };

  return (
    <div className="dashboard-shell">
      <div className="dashboard-aura" />
      <div className="dashboard-frame">
        <StudioHeader activeTab="library" onNavigate={onNavigate} />
        <main>
          <div className="library-shell">
            <div className="library-header">
              <div>
                <div className="eyebrow">Library</div>
                <h1>Your projects</h1>
                <p>All your processed videos and clips in one place.</p>
              </div>
              {jobHistory.length > 0 && (
                <button className="ghost-button" onClick={clearHistory}>Clear all</button>
              )}
            </div>

            {jobHistory.length === 0 ? (
              <div className="empty-jobs">
                <div className="empty-art"><i /><i /><i /><b>
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" width="24" height="24">
                    <path d="m12 3 1.6 5.4L19 10l-5.4 1.6L12 17l-1.6-5.4L5 10l5.4-1.6L12 3Zm6.5 12 .6 2 1.9.5-1.9.6-.6 1.9-.5-1.9-2-.6 2-.5.5-2Z" />
                  </svg>
                </b></div>
                <h3>No projects yet</h3>
                <p>Your recent projects will appear here, ready to preview, revisit and export.</p>
                <button className="generate-button" onClick={() => onNavigate('create')}>Start a new job</button>
              </div>
            ) : (
              <div className="job-history-list">
                {jobHistory.map((job) => (
                  <JobCard key={job.jobId} job={job} onVisitJob={onVisitJob} />
                ))}
              </div>
            )}
          </div>
        </main>
      </div>
    </div>
  );
}
